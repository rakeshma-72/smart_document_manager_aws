import json
import pytest
from unittest.mock import MagicMock, patch

from backend.pipeline.summarize.app import (
    ALLOWED_DOC_TYPES,
    contains_pii,
    clean_json_response,
    lambda_handler as summarize_handler,
)
from backend.search.app import (
    cosine_similarity,
    lambda_handler as search_handler,
    DAILY_SEARCH_LIMIT,
    SIMILARITY_THRESHOLD,
)
from backend.pipeline.notify_failure.app import lambda_handler as notify_failure_handler


# 1. Document Classification & Allow-list Validation
def test_doc_type_allowlist_validation():
    valid_types = ["invoice", "resume", "report", "contract", "notes", "letter", "other"]
    assert set(valid_types) == ALLOWED_DOC_TYPES

    # Simulate extraction with valid type
    raw_json = json.dumps({
        "summary": "This is an invoice summary.",
        "tags": ["billing", "finance"],
        "docType": "invoice",
        "keyFields": [{"label": "Total Amount", "value": "$1,200.00"}]
    })
    parsed = clean_json_response(raw_json)
    assert parsed["docType"] in ALLOWED_DOC_TYPES
    assert parsed["docType"] == "invoice"


def test_doc_type_defaults_to_other_on_invalid_or_missing():
    raw_invalid = json.dumps({
        "summary": "Some text",
        "tags": ["misc"],
        "docType": "SECRET_CLASSIFICATION",
        "keyFields": []
    })
    parsed = clean_json_response(raw_invalid)
    assert parsed.get("docType") == "other"


# 2. KeyFields PII Exclusion & Truncation
def test_key_fields_pii_exclusion():
    # contains_pii helper should detect emails, phones, SSNs, credit cards
    assert contains_pii("Contact user@example.com for payment") is True
    assert contains_pii("Call 555-123-4567") is True
    assert contains_pii("SSN: 123-45-6789") is True
    assert contains_pii("Card 4111-2222-3333-4444") is True
    assert contains_pii("Invoice 98765 issued to ACME Corp") is False


def test_key_fields_truncation():
    long_label = "A" * 60
    long_val = "B" * 120

    truncated_label = long_label[:40]
    truncated_val = long_val[:80]

    assert len(truncated_label) == 40
    assert len(truncated_val) == 80


# 3. Safe Failure Step Recording (No Raw Error Message Text)
@patch("backend.pipeline.notify_failure.app.dynamodb")
@patch("backend.pipeline.notify_failure.app.sqs")
def test_notify_failure_records_safe_error_code_only(mock_sqs, mock_dynamodb):
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    event = {
        "ExecutionInput": {"userId": "user-abc-123", "docId": "doc-xyz-789"},
        "FailingStep": "extract",
        "Error": {
            "Error": "ValidationException",
            "Cause": "Sensitive secret stack trace or user payload that must never be recorded"
        }
    }

    resp = notify_failure_handler(event, None)

    assert resp["status"] == "FAILED"
    assert resp["failedStep"] == "extract"
    assert resp["errorCode"] == "ValidationException"
    assert "Sensitive secret stack trace" not in resp.values()

    # Verify update_item values
    update_calls = mock_table.update_item.call_args[1]
    expr_vals = update_calls["ExpressionAttributeValues"]
    assert expr_vals[":status"] == "FAILED"
    assert expr_vals[":errorCode"] == "ValidationException"
    assert expr_vals[":failedStep"] == "extract"
    # Confirm error cause text was not stored
    assert "Sensitive secret" not in str(expr_vals)


# 4. Semantic Search Tenant Isolation & Cosine Similarity
def test_cosine_similarity_math():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    vec_c = [0.0, 1.0, 0.0]

    assert pytest.approx(cosine_similarity(vec_a, vec_b), 0.001) == 1.0
    assert pytest.approx(cosine_similarity(vec_a, vec_c), 0.001) == 0.0


@patch("backend.search.app.dynamodb")
@patch("backend.search.app.s3_client")
@patch("backend.search.app.bedrock_runtime")
def test_semantic_search_user_isolation(mock_bedrock, mock_s3, mock_dynamodb):
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Mock DynamoDB returning documents owned by user-1
    mock_table.query.return_value = {
        "Items": [
            {
                "userId": "user-1",
                "docId": "doc-1",
                "fileName": "Contract.pdf",
                "docType": "contract",
                "summary": "NDA agreement between parties."
            }
        ]
    }
    # Mock usage quota check
    mock_table.get_item.return_value = {"Item": {"searchCount": 5}}

    # Mock S3 embeddings lookup
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "embeddings/user-1/doc-1/embeddings.json"}
            ]
        }
    ]

    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps([
            {
                "chunkIndex": 0,
                "text": "This NDA agreement is confidential between parties.",
                "vector": [0.5, 0.5, 0.5, 0.5]
            }
        ]).encode("utf-8"))
    }

    # Mock Bedrock Titan V2 query embedding
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({
            "embedding": [0.5, 0.5, 0.5, 0.5]
        }).encode("utf-8"))
    }

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "user-1"}
                }
            }
        },
        "queryStringParameters": {
            "q": "confidential agreement",
            "mode": "semantic"
        }
    }

    resp = search_handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])

    assert body["mode"] == "semantic"
    assert body["count"] == 1
    assert body["results"][0]["docId"] == "doc-1"
    assert body["results"][0]["matchPercentage"] == 100
    assert body["results"][0]["similarityScore"] >= SIMILARITY_THRESHOLD

    # Verify S3 prefix was strictly scoped to caller's userId
    mock_paginator.paginate.assert_called_with(
        Bucket=mock_s3.get_paginator.return_value.paginate.call_args[1].get("Bucket"),
        Prefix="embeddings/user-1/"
    )


# 5. Semantic Search Daily Limit 429
@patch("backend.search.app.dynamodb")
def test_semantic_search_daily_limit_429(mock_dynamodb):
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.query.return_value = {"Items": []}
    # User has reached DAILY_SEARCH_LIMIT (100)
    mock_table.get_item.return_value = {"Item": {"searchCount": DAILY_SEARCH_LIMIT}}

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "user-exhausted"}
                }
            }
        },
        "queryStringParameters": {
            "q": "financial reports",
            "mode": "semantic"
        }
    }

    resp = search_handler(event, None)
    assert resp["statusCode"] == 429
    body = json.loads(resp["body"])
    assert "limit" in body["error"].lower()


# 6. Fallback from Semantic to Keyword when no embeddings exist
@patch("backend.search.app.dynamodb")
@patch("backend.search.app.s3_client")
def test_semantic_search_fallback_to_keyword_when_no_embeddings(mock_s3, mock_dynamodb):
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {"Item": {"searchCount": 0}}

    mock_table.query.return_value = {
        "Items": [
            {
                "userId": "user-1",
                "docId": "legacy-doc",
                "fileName": "legacy_receipt.pdf",
                "summary": "Monthly server subscription receipt.",
                "preview": "Total: $50",
                "tags": ["finance"],
                "docType": "invoice"
            }
        ]
    }

    # Empty embeddings
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Contents": []}]

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "user-1"}
                }
            }
        },
        "queryStringParameters": {
            "q": "receipt",
            "mode": "semantic"
        }
    }

    resp = search_handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])

    assert body["fallback"] is True
    assert body["mode"] == "keyword"
    assert body["count"] == 1
    assert body["results"][0]["docId"] == "legacy-doc"
