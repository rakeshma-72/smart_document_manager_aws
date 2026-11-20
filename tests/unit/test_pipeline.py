import json
import os
import pytest
from unittest.mock import MagicMock, patch

from backend.pipeline.trigger import app as trigger_app
from backend.pipeline.validate import app as validate_app
from backend.pipeline.extract import app as extract_app
from backend.pipeline.summarize import app as summarize_app
from backend.pipeline.detect_pii import app as detect_pii_app
from backend.pipeline.save_results import app as save_results_app
from backend.pipeline.notify_failure import app as notify_failure_app
from botocore.exceptions import ClientError


# -----------------------------------------------------------------------------
# Trigger Tests
# -----------------------------------------------------------------------------

@patch.object(trigger_app.sfn_client, "start_execution")
def test_trigger_success(mock_start):
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "uploads/user-123/doc-456/invoice.pdf"},
                }
            }
        ]
    }
    res = trigger_app.lambda_handler(event, None)
    assert res["statusCode"] == 200
    mock_start.assert_called_once()
    call_kwargs = mock_start.call_args[1]
    assert call_kwargs["name"] == "doc-456"
    payload = json.loads(call_kwargs["input"])
    assert payload["docId"] == "doc-456"
    assert payload["userId"] == "user-123"


@patch.object(trigger_app.sfn_client, "start_execution")
def test_trigger_idempotent_duplicate_ignored(mock_start):
    mock_start.side_effect = ClientError(
        {"Error": {"Code": "ExecutionAlreadyExists", "Message": "Execution already exists"}},
        "StartExecution"
    )
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "uploads/user-123/doc-456/invoice.pdf"},
                }
            }
        ]
    }
    res = trigger_app.lambda_handler(event, None)
    assert res["statusCode"] == 200


# -----------------------------------------------------------------------------
# Validate Tests
# -----------------------------------------------------------------------------

@patch.object(validate_app.dynamodb, "Table")
@patch.object(validate_app.s3_client, "head_object")
def test_validate_success(mock_head, mock_table):
    mock_head.return_value = {"ContentLength": 1024}
    event = {
        "bucket": "test-bucket",
        "key": "uploads/user-123/doc-456/report.pdf",
        "userId": "user-123",
        "docId": "doc-456",
        "fileName": "report.pdf",
        "fileExt": ".pdf",
    }
    res = validate_app.lambda_handler(event, None)
    assert res["docId"] == "doc-456"
    assert res["contentLength"] == 1024
    assert mock_table.return_value.update_item.call_count >= 1


def test_validate_unsupported_extension():
    event = {
        "bucket": "test-bucket",
        "key": "uploads/user-123/doc-456/script.exe",
        "userId": "user-123",
        "docId": "doc-456",
        "fileExt": ".exe",
    }
    with pytest.raises(validate_app.ValidationError):
        validate_app.lambda_handler(event, None)


@patch.object(validate_app.s3_client, "head_object")
def test_validate_size_exceeded(mock_head):
    mock_head.return_value = {"ContentLength": 5 * 1024 * 1024}
    event = {
        "bucket": "test-bucket",
        "key": "uploads/user-123/doc-456/huge.pdf",
        "userId": "user-123",
        "docId": "doc-456",
        "fileExt": ".pdf",
    }
    with pytest.raises(validate_app.ValidationError):
        validate_app.lambda_handler(event, None)


# -----------------------------------------------------------------------------
# Extract Tests
# -----------------------------------------------------------------------------

@patch.object(extract_app.s3_client, "put_object")
@patch.object(extract_app.s3_client, "get_object")
@patch.object(extract_app.bedrock_runtime, "converse")
def test_extract_pdf_success(mock_converse, mock_get_s3, mock_put_s3):
    mock_get_s3.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"%PDF-1.4 test")),
    }
    mock_converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Extracted invoice content: $500 total."}]
            }
        }
    }
    event = {
        "bucket": "test-bucket",
        "key": "uploads/user-123/doc-456/invoice.pdf",
        "userId": "user-123",
        "docId": "doc-456",
        "fileExt": ".pdf",
    }
    res = extract_app.lambda_handler(event, None)
    assert res["extractedTextKey"] == "extracted-text/user-123/doc-456/extracted.txt"
    assert res["wordCount"] > 0
    assert "text" not in res  # Ensure text is NOT in output state payload
    mock_put_s3.assert_called_once()


# -----------------------------------------------------------------------------
# Summarize Tests (Groq with Bedrock Nova Micro fallback)
# -----------------------------------------------------------------------------

def test_mask_pii_for_groq():
    raw = "Contact alice@example.com at 555-123-4567 or SSN 000-11-2222."
    masked = summarize_app.mask_pii_for_groq(raw)
    assert "alice@example.com" not in masked
    assert "555-123-4567" not in masked
    assert "000-11-2222" not in masked
    assert "[EMAIL_MASKED]" in masked
    assert "[PHONE_MASKED]" in masked
    assert "[SSN_MASKED]" in masked


def test_clean_json_response_with_think_block():
    raw_llm = "<think>Here is my reasoning about the cloud</think>{\"summary\": \"Cloud guide.\", \"tags\": [\"cloud\", \"aws\"]}"
    parsed = summarize_app.clean_json_response(raw_llm)
    assert parsed["summary"] == "Cloud guide."
    assert "cloud" in parsed["tags"]


@patch.object(summarize_app, "summarize_with_groq")
@patch.object(summarize_app.s3_client, "get_object")
def test_summarize_groq_success(mock_get_s3, mock_groq):
    mock_get_s3.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"Extracted text content.")),
    }
    mock_groq.return_value = {
        "summary": "Concise executive summary.",
        "tags": ["finance", "report"],
    }
    event = {
        "bucket": "test-bucket",
        "extractedTextKey": "extracted-text/u/d/extracted.txt",
        "docId": "doc-123",
    }
    res = summarize_app.lambda_handler(event, None)
    assert res["summary"] == "Concise executive summary."
    assert "finance" in res["tags"]
    assert res["summaryProvider"] == "groq"


@patch.object(summarize_app, "summarize_with_bedrock")
@patch.object(summarize_app, "summarize_with_groq")
@patch.object(summarize_app.s3_client, "get_object")
def test_summarize_groq_failure_bedrock_fallback(mock_get_s3, mock_groq, mock_bedrock):
    mock_get_s3.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"Extracted text content.")),
    }
    mock_groq.side_effect = RuntimeError("Groq API 503")
    mock_bedrock.return_value = {
        "summary": "Bedrock Nova fallback summary.",
        "tags": ["bedrock", "fallback"],
    }
    event = {
        "bucket": "test-bucket",
        "extractedTextKey": "extracted-text/u/d/extracted.txt",
        "docId": "doc-123",
    }
    res = summarize_app.lambda_handler(event, None)
    assert res["summary"] == "Bedrock Nova fallback summary."
    assert "bedrock" in res["tags"]
    assert res["summaryProvider"] == "nova"


# -----------------------------------------------------------------------------
# Detect PII Tests
# -----------------------------------------------------------------------------

@patch.object(detect_pii_app.s3_client, "get_object")
def test_detect_pii_success(mock_get_s3):
    text = "User bob@example.com phone 555-888-9999 and credit card 4111-2222-3333-4444."
    mock_get_s3.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=text.encode())),
    }
    event = {
        "bucket": "test-bucket",
        "extractedTextKey": "extracted-text/u/d/extracted.txt",
    }
    res = detect_pii_app.lambda_handler(event, None)
    assert "EMAIL" in res["piiEntities"]
    assert "PHONE" in res["piiEntities"]
    assert "CREDIT_CARD" in res["piiEntities"]


# -----------------------------------------------------------------------------
# Save Results Tests
# -----------------------------------------------------------------------------

@patch.object(save_results_app.dynamodb, "Table")
def test_save_results_success(mock_table):
    event = {
        "userId": "user-123",
        "docId": "doc-456",
        "extractedTextKey": "extracted-text/u/d/extracted.txt",
        "preview": "Preview text",
        "wordCount": 100,
        "summary": "Done.",
        "tags": ["tag1"],
        "piiEntities": ["EMAIL"],
        "summaryProvider": "groq",
    }
    res = save_results_app.lambda_handler(event, None)
    assert res["status"] == "PROCESSED"
    assert res["summaryProvider"] == "groq"
    mock_table.return_value.update_item.assert_called_once()
    saved_values = mock_table.return_value.update_item.call_args[1]["ExpressionAttributeValues"]
    assert saved_values[":summaryProvider"] == "groq"


# -----------------------------------------------------------------------------
# Notify Failure Tests
# -----------------------------------------------------------------------------

@patch.object(notify_failure_app.sqs, "send_message")
@patch.object(notify_failure_app.dynamodb, "Table")
def test_notify_failure_handles_error(mock_table, mock_sqs, monkeypatch):
    monkeypatch.setattr(notify_failure_app, "DLQ_URL", "https://sqs.mock.url")
    event = {
        "ExecutionInput": {"userId": "user-123", "docId": "doc-456"},
        "Error": {"Error": "ValidationError", "Cause": "File size exceeds limit"},
    }
    res = notify_failure_app.lambda_handler(event, None)
    assert res["status"] == "FAILED"
    assert mock_table.return_value.update_item.call_count >= 1
    update_args = mock_table.return_value.update_item.call_args[1]
    assert ":processedAt" in update_args["ExpressionAttributeValues"]
    assert update_args["ExpressionAttributeValues"][":status"] == "FAILED"
    mock_sqs.assert_called_once()
    sqs_body = json.loads(mock_sqs.call_args[1]["MessageBody"])
    assert sqs_body["docId"] == "doc-456"
    assert sqs_body["userId"] == "user-123"
    assert "text" not in sqs_body  # Ensure text is NEVER in DLQ payload
