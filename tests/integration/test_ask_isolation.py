import json
import pytest
from unittest.mock import MagicMock, patch
import importlib.util
import os
import sys

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

ask_mod = load_module("ask_isolation_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/ask/app.py')))
ask_handler = ask_mod.lambda_handler


@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.s3_client, "get_object")
@patch.object(ask_mod.dynamodb, "Table")
@patch('urllib.request.urlopen')
def test_user_a_cannot_access_user_b_chunks(mock_urlopen, mock_dynamo_table, mock_s3_get, mock_get_paginator, mock_bedrock_invoke):
    """
    Integration test for multi-tenant vector RAG isolation:
    User A queries /ask.
    Ensure S3 paginate is strictly scoped to prefix 'embeddings/user-A/'
    and can NEVER retrieve User B's documents/chunks even if User B's chunk has 100% vector similarity.
    """
    q_vec = [1.0] * 1024
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": q_vec}).encode('utf-8'))
    }

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    mock_table.query.return_value = {
        "Items": [{"docId": "doc-user-a", "fileName": "user_a_report.pdf"}]
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator

    def paginate_side_effect(Bucket, Prefix):
        if Prefix.startswith("embeddings/user-A/"):
            return [
                {
                    "Contents": [
                        {"Key": "embeddings/user-A/doc-user-a/embeddings.json"}
                    ]
                }
            ]
        elif Prefix.startswith("embeddings/user-B/"):
            return [
                {
                    "Contents": [
                        {"Key": "embeddings/user-B/secret-doc-user-b/embeddings.json"}
                    ]
                }
            ]
        return []

    mock_paginator.paginate.side_effect = paginate_side_effect

    user_a_embeddings = [
        {
            "chunkIndex": 0,
            "text": "User A public report summary regarding Q3 revenue.",
            "vector": [0.8] * 1024
        }
    ]
    mock_s3_get.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(user_a_embeddings).encode('utf-8'))
    }

    mock_groq_resp = MagicMock()
    mock_groq_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Revenue grew significantly in Q3."}}]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_groq_resp

    with patch.dict(os.environ, {
        "DOCUMENTS_BUCKET": "test-bucket",
        "DOCUMENTS_TABLE": "test-table",
        "GROQ_API_KEY": "gsk-mock123"
    }):
        event = {
            "body": json.dumps({"question": "What is the secret data?"}),
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {"sub": "user-A"}
                    }
                }
            }
        }
        res = ask_handler(event, None)
        assert res["statusCode"] == 200

        # Assert Prefix passed to S3 paginate is strictly user-A
        mock_paginator.paginate.assert_called_once()
        called_prefix = mock_paginator.paginate.call_args[1]["Prefix"]
        assert called_prefix == "embeddings/user-A/"
        assert "user-B" not in called_prefix

        # Assert the citations contain ONLY user-A documents
        body = json.loads(res["body"])
        for src in body["sources"]:
            assert src["docId"] == "doc-user-a"
            assert "user-B" not in src["docId"]
            assert "secret-doc-user-b" not in src["fileName"]


del_mod = load_module("del_doc_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/delete-doc/app.py')))
del_handler = del_mod.lambda_handler

def test_deleted_document_chunks_not_returned_in_ask():
    """
    Test verifying that once a document is deleted via delete-doc handler,
    /ask can no longer return its chunks:
    1. Simulate existing document doc-to-delete in DynamoDB and S3 embeddings.
    2. Invoke delete-doc handler to delete doc-to-delete.
    3. Assert S3 delete was called on chunks and embeddings.
    4. Query /ask for that user -> returns 'no processed documents' or chunks from remaining docs only.
    """
    mock_s3 = MagicMock()
    mock_dynamo = MagicMock()
    mock_bedrock = MagicMock()

    # Step 1: Mock S3 & DynamoDB storage state
    stored_s3_keys = {
        "uploads/user-A/doc-to-delete/file.pdf": b"content",
        "extracted-text/user-A/doc-to-delete/extracted.txt": b"content",
        "chunks/user-A/doc-to-delete/chunks.json": b"content",
        "embeddings/user-A/doc-to-delete/embeddings.json": json.dumps([
            {"chunkIndex": 0, "text": "Confidential financial projections", "vector": [1.0] * 1024}
        ]).encode("utf-8")
    }

    dynamo_items = {
        ("user-A", "doc-to-delete"): {
            "userId": "user-A",
            "docId": "doc-to-delete",
            "fileName": "financials.pdf",
            "s3Key": "uploads/user-A/doc-to-delete/file.pdf",
            "extractedTextKey": "extracted-text/user-A/doc-to-delete/extracted.txt",
            "chunksKey": "chunks/user-A/doc-to-delete/chunks.json",
        }
    }

    # Setup delete_doc mocks
    with patch.object(del_mod, "s3_client", mock_s3), \
         patch.object(del_mod, "dynamodb", mock_dynamo), \
         patch.dict(os.environ, {"DOCUMENTS_BUCKET": "test-bucket", "DOCUMENTS_TABLE": "test-table"}):

        mock_del_table = MagicMock()
        mock_dynamo.Table.return_value = mock_del_table
        mock_del_table.get_item.return_value = {"Item": dynamo_items[("user-A", "doc-to-delete")]}

        def mock_del_item(Key):
            k = (Key["userId"], Key["docId"])
            if k in dynamo_items:
                del dynamo_items[k]

        mock_del_table.delete_item.side_effect = mock_del_item

        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "embeddings/user-A/doc-to-delete/embeddings.json"}]}
        ]

        def mock_s3_del(Bucket, Key):
            if Key in stored_s3_keys:
                del stored_s3_keys[Key]

        mock_s3.delete_object.side_effect = mock_s3_del

        # Execute document deletion
        del_event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"sub": "user-A"}}
                }
            },
            "pathParameters": {"docId": "doc-to-delete"}
        }
        del_resp = del_handler(del_event, None)
        assert del_resp["statusCode"] == 200

        # Assert files were deleted
        assert "uploads/user-A/doc-to-delete/file.pdf" not in stored_s3_keys
        assert "extracted-text/user-A/doc-to-delete/extracted.txt" not in stored_s3_keys
        assert "chunks/user-A/doc-to-delete/chunks.json" not in stored_s3_keys
        assert "embeddings/user-A/doc-to-delete/embeddings.json" not in stored_s3_keys
        assert ("user-A", "doc-to-delete") not in dynamo_items

    # Step 2: Now invoke /ask as user-A
    with patch.object(ask_mod, "s3_client", mock_s3), \
         patch.object(ask_mod, "dynamodb", mock_dynamo), \
         patch.object(ask_mod, "bedrock_runtime", mock_bedrock), \
         patch.dict(os.environ, {"DOCUMENTS_BUCKET": "test-bucket", "DOCUMENTS_TABLE": "test-table", "GROQ_API_KEY": "mock"}):

        # DynamoDB query returns empty list since doc was deleted
        mock_ask_table = MagicMock()
        mock_dynamo.Table.return_value = mock_ask_table
        mock_ask_table.query.return_value = {"Items": [v for k, v in dynamo_items.items() if k[0] == "user-A"]}

        mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [1.0] * 1024}).encode('utf-8'))
        }

        ask_event = {
            "body": json.dumps({"question": "What are the financial projections?"}),
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"sub": "user-A"}}
                }
            }
        }

        ask_resp = ask_handler(ask_event, None)
        assert ask_resp["statusCode"] == 200
        body = json.loads(ask_resp["body"])
        # Should return no processed documents message, and zero sources
        assert len(body["sources"]) == 0
        assert "do not have any processed documents" in body["answer"]

