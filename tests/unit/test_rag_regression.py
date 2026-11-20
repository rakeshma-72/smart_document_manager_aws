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

ask_mod = load_module("ask_regression_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/ask/app.py')))
save_results_mod = load_module("save_results_regression_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/pipeline/save_results/app.py')))
chunk_text_mod = load_module("chunk_text_regression_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/pipeline/chunk_text/app.py')))
embed_chunks_mod = load_module("embed_chunks_regression_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/pipeline/embed_chunks/app.py')))

ask_handler = ask_mod.lambda_handler
save_results_handler = save_results_mod.lambda_handler
chunk_text_handler = chunk_text_mod.lambda_handler
embed_chunks_handler = embed_chunks_mod.lambda_handler


# 1. Pipeline Contract: SaveResults preserves all input context for ChunkText and EmbedChunks
def test_pipeline_contract_preserves_bucket_and_metadata():
    """Verify SaveResults passes all S3 bucket and key information to downstream ChunkText."""
    event = {
        "bucket": "test-docs-bucket",
        "key": "uploads/user-1/doc-1/file.pdf",
        "userId": "user-1",
        "docId": "doc-1",
        "fileName": "file.pdf",
        "fileExt": ".pdf",
        "extractedTextKey": "extracted-text/user-1/doc-1/extracted.txt",
        "preview": "Test preview",
        "wordCount": 100,
        "summary": "Document summary",
        "tags": ["test"],
        "summaryProvider": "groq",
        "docType": "report",
        "keyFields": [{"label": "Date", "value": "2026-11-05"}],
        "piiEntities": []
    }

    with patch.object(save_results_mod.dynamodb, "Table") as mock_table_cls:
        mock_table = MagicMock()
        mock_table_cls.return_value = mock_table
        out = save_results_handler(event, None)

    # Must preserve bucket and extractedTextKey for chunk_text
    assert out["bucket"] == "test-docs-bucket"
    assert out["extractedTextKey"] == "extracted-text/user-1/doc-1/extracted.txt"
    assert out["userId"] == "user-1"
    assert out["docId"] == "doc-1"
    assert out["status"] == "PROCESSED"

    # Now verify chunk_text can execute with this exact output without KeyError: 'bucket'
    with patch.object(chunk_text_mod.s3_client, "get_object") as mock_get_obj, \
         patch.object(chunk_text_mod.s3_client, "put_object") as mock_put_obj, \
         patch.object(chunk_text_mod.dynamodb, "Table") as mock_chunk_table:

        mock_get_obj.return_value = {
            "Body": MagicMock(read=lambda: b"This is the extracted text that needs to be chunked into overlapping segments.")
        }

        chunk_out = chunk_text_handler(out, None)
        assert "chunksKey" in chunk_out
        assert chunk_out["chunkCount"] >= 1
        assert chunk_out["bucket"] == "test-docs-bucket"

        # Verify chunksKey stored strictly under caller's tenant prefix
        assert chunk_out["chunksKey"] == "chunks/user-1/doc-1/chunks.json"


# 2. User A can retrieve their own processed documents and citations
@patch.object(ask_mod, "GROQ_API_KEY", "dummy-groq-key")
@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.s3_client, "get_object")
@patch.object(ask_mod.dynamodb, "Table")
@patch("urllib.request.urlopen")
def test_user_a_can_retrieve_own_processed_documents(mock_urlopen, mock_dynamo_table, mock_s3_get, mock_get_paginator, mock_bedrock_invoke):
    q_vec = [0.5] * 1024
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": q_vec}).encode("utf-8"))
    }

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    mock_table.query.return_value = {
        "Items": [
            {"docId": "doc-a1", "fileName": "Project_Report.pdf", "status": "PROCESSED"}
        ]
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Contents": [{"Key": "embeddings/user-A/doc-a1/embeddings.json"}]
        }
    ]

    mock_s3_get.return_value = {
        "Body": MagicMock(read=lambda: json.dumps([
            {
                "chunkIndex": 0,
                "text": "Antigravity agents automate complex software delivery cycles.",
                "vector": [0.5] * 1024
            }
        ]).encode("utf-8"))
    }

    mock_groq_resp = MagicMock()
    mock_groq_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Antigravity automates software cycles."}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_groq_resp

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-A"}}
            }
        },
        "body": json.dumps({"question": "What does Antigravity do?"})
    }

    res = ask_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert "Antigravity automates" in body["answer"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["docId"] == "doc-a1"
    assert body["sources"][0]["fileName"] == "Project_Report.pdf"


# 3. User A cannot retrieve User B's documents, chunks, or embeddings
@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.dynamodb, "Table")
def test_user_a_cannot_retrieve_user_b_documents(mock_dynamo_table, mock_get_paginator, mock_bedrock_invoke):
    q_vec = [0.5] * 1024
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": q_vec}).encode("utf-8"))
    }

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    # User A has no processed documents in DynamoDB
    mock_table.query.return_value = {"Items": []}

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-A"}}
            }
        },
        "body": json.dumps({"question": "Show me secret numbers"})
    }

    res = ask_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["answer"] == "You do not have any processed documents yet. Upload a document first to ask questions."
    assert body["sources"] == []


# 4. Identical embeddings belonging to different users remain strictly isolated
@patch.object(ask_mod, "GROQ_API_KEY", "dummy-groq-key")
@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.s3_client, "get_object")
@patch.object(ask_mod.dynamodb, "Table")
@patch("urllib.request.urlopen")
def test_identical_embeddings_belonging_to_different_users_remain_isolated(mock_urlopen, mock_dynamo_table, mock_s3_get, mock_get_paginator, mock_bedrock_invoke):
    """
    User A and User B have documents with identical text and vector embeddings.
    When User A queries, verify S3 Prefix is strictly 'embeddings/user-A/' and never loads User B's object.
    """
    identical_vector = [0.123] * 1024
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": identical_vector}).encode("utf-8"))
    }

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    mock_table.query.return_value = {
        "Items": [{"docId": "doc-a1", "fileName": "SharedTopic.pdf"}]
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator

    def paginate_check(Bucket, Prefix):
        # Assert caller can only query their own partition
        assert Prefix == "embeddings/user-A/"
        return [
            {"Contents": [{"Key": "embeddings/user-A/doc-a1/embeddings.json"}]}
        ]

    mock_paginator.paginate.side_effect = paginate_check

    mock_s3_get.return_value = {
        "Body": MagicMock(read=lambda: json.dumps([
            {"chunkIndex": 0, "text": "Secret User A content", "vector": identical_vector}
        ]).encode("utf-8"))
    }

    mock_groq_resp = MagicMock()
    mock_groq_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Answer based only on User A content."}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_groq_resp

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-A"}}
            }
        },
        "body": json.dumps({"question": "Tell me about the topic"})
    }

    res = ask_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["sources"][0]["docId"] == "doc-a1"


# 5. Documents without chunks return clear message
@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.dynamodb, "Table")
def test_documents_without_chunks_return_clear_message(mock_dynamo_table, mock_get_paginator, mock_bedrock_invoke):
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode("utf-8"))
    }

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    # User has document in DynamoDB, but no embeddings have been generated yet in S3
    mock_table.query.return_value = {
        "Items": [{"docId": "doc-processing", "fileName": "Draft.pdf"}]
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Contents": []}]

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-A"}}
            }
        },
        "body": json.dumps({"question": "What is in my draft?"})
    }

    res = ask_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["answer"] == "You do not have any processed documents yet. Upload a document first to ask questions."
    assert body["sources"] == []


# 6. Fallback from Groq to Bedrock Nova Micro when Groq fails
@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.s3_client, "get_object")
@patch.object(ask_mod.dynamodb, "Table")
@patch("urllib.request.urlopen")
def test_ask_groq_failure_falls_back_to_bedrock_nova_micro(mock_urlopen, mock_dynamo_table, mock_s3_get, mock_get_paginator, mock_bedrock_invoke):
    mock_bedrock_invoke.side_effect = [
        # 1. embed_question
        {"body": MagicMock(read=lambda: json.dumps({"embedding": [0.5] * 1024}).encode("utf-8"))},
        # 2. answer_with_bedrock
        {"body": MagicMock(read=lambda: json.dumps({"output": {"message": {"content": [{"text": "Nova Micro answer"}]}}}).encode("utf-8"))}
    ]

    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    mock_table.query.return_value = {
        "Items": [{"docId": "doc-1", "fileName": "Document.pdf"}]
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "embeddings/user-1/doc-1/embeddings.json"}]}
    ]

    mock_s3_get.return_value = {
        "Body": MagicMock(read=lambda: json.dumps([
            {"chunkIndex": 0, "text": "Document content", "vector": [0.5] * 1024}
        ]).encode("utf-8"))
    }

    # Groq fails with HTTP 500
    mock_urlopen.side_effect = Exception("Groq API Timeout")

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-1"}}
            }
        },
        "body": json.dumps({"question": "Summary?"})
    }

    res = ask_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["answer"] == "Nova Micro answer"
    assert body["provider"] == "nova"
    assert len(body["sources"]) == 1
