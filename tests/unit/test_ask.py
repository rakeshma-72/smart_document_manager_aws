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

chunk_mod = load_module("chunk_text_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/pipeline/chunk_text/app.py')))
ask_mod = load_module("ask_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/ask/app.py')))

split_text_into_chunks = chunk_mod.split_text_into_chunks
chunk_handler = chunk_mod.lambda_handler
cosine_similarity = ask_mod.cosine_similarity
ask_handler = ask_mod.lambda_handler


def test_split_text_into_chunks_basic():
    text = "Short sentence. Another sentence."
    chunks = split_text_into_chunks(text)
    assert len(chunks) == 1
    assert chunks[0]["chunkIndex"] == 0
    assert chunks[0]["text"] == text


def test_split_text_into_chunks_overlapping_and_limits():
    paragraphs = [f"This is paragraph {i} containing enough text to test overlap boundaries. " * 5 for i in range(20)]
    text = "\n\n".join(paragraphs)
    
    chunks = split_text_into_chunks(text)
    assert len(chunks) <= 25
    assert chunks[0]["chunkIndex"] == 0
    assert len(chunks) > 1
    assert len(chunks[0]["text"]) > 0


def test_cosine_similarity():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    vec_c = [0.0, 1.0, 0.0]
    vec_zero = [0.0, 0.0, 0.0]

    assert pytest.approx(cosine_similarity(vec_a, vec_b), 0.0001) == 1.0
    assert pytest.approx(cosine_similarity(vec_a, vec_c), 0.0001) == 0.0
    assert cosine_similarity(vec_a, vec_zero) == 0.0


@patch.object(chunk_mod.s3_client, "get_object")
@patch.object(chunk_mod.s3_client, "put_object")
def test_chunk_handler_success(mock_put, mock_get):
    sample_text = "Chapter 1: Cloud Architecture. Step functions provide robust serverless workflow orchestration."
    mock_get.return_value = {
        'Body': MagicMock(read=lambda: sample_text.encode('utf-8'))
    }

    event = {
        "userId": "user-123",
        "docId": "doc-456",
        "bucket": "test-bucket",
        "extractedTextKey": "extracted-text/user-123/doc-456.txt"
    }

    res = chunk_handler(event, None)
    assert res["chunksKey"] == "chunks/user-123/doc-456/chunks.json"
    assert res["chunkCount"] == 1

    mock_put.assert_called_once()
    put_call = mock_put.call_args[1]
    assert put_call["Bucket"] == "test-bucket"
    assert put_call["Key"] == "chunks/user-123/doc-456/chunks.json"
    data = json.loads(put_call["Body"].decode('utf-8') if isinstance(put_call["Body"], bytes) else put_call["Body"])
    assert len(data) == 1


def test_ask_handler_unauthorized():
    event = {
        "body": json.dumps({"question": "What is cloud?"}),
        "requestContext": {}
    }
    res = ask_handler(event, None)
    assert res["statusCode"] == 401
    assert "Unauthorized" in json.loads(res["body"])["error"]


def test_ask_handler_missing_question():
    event = {
        "body": json.dumps({"question": "   "}),
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "user-123"}
                }
            }
        }
    }
    res = ask_handler(event, None)
    assert res["statusCode"] == 400
    assert "required" in json.loads(res["body"])["error"]


def test_ask_handler_question_too_long():
    event = {
        "body": json.dumps({"question": "a" * 501}),
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "user-123"}
                }
            }
        }
    }
    res = ask_handler(event, None)
    assert res["statusCode"] == 400
    assert "exceeds maximum limit" in json.loads(res["body"])["error"]


@patch.object(ask_mod.dynamodb, "Table")
def test_ask_handler_daily_cap_exceeded(mock_dynamo_table):
    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    # Mock get_item returning 50 questions already used
    mock_table.get_item.return_value = {
        "Item": {"questionCount": 50}
    }

    event = {
        "body": json.dumps({"question": "Is this allowed?"}),
        "requestContext": {
            "authorizer": {
                "jwt": {"claims": {"sub": "user-rate-limited"}}
            }
        }
    }
    res = ask_handler(event, None)
    assert res["statusCode"] == 429
    body = json.loads(res["body"])
    assert "Daily question limit reached" in body["error"]
    assert body["limit"] == 50
    assert body["current"] == 50



@patch.object(ask_mod.bedrock_runtime, "invoke_model")
@patch.object(ask_mod.s3_client, "get_paginator")
@patch.object(ask_mod.s3_client, "get_object")
@patch.object(ask_mod.dynamodb, "Table")
@patch('urllib.request.urlopen')
def test_ask_handler_groq_success(mock_urlopen, mock_dynamo_table, mock_s3_get, mock_get_paginator, mock_bedrock_invoke):
    mock_table = MagicMock()
    mock_dynamo_table.return_value = mock_table
    mock_table.query.return_value = {
        "Items": [{"docId": "doc-1", "fileName": "arch.pdf"}]
    }

    q_vec = [1.0] + [0.0] * 1023
    mock_bedrock_invoke.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"embedding": q_vec}).encode('utf-8'))
    }

    mock_paginator = MagicMock()
    mock_get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "embeddings/user-123/doc-1/embeddings.json"}
            ]
        }
    ]

    # Matching normalized vector with high cosine similarity to q_vec
    doc_chunk_vec = [0.99] + [0.0] * 1023
    embeddings_data = [
        {
            "chunkIndex": 0,
            "text": "AWS Step Functions manages the document processing state machine.",
            "vector": doc_chunk_vec
        }
    ]
    mock_s3_get.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(embeddings_data).encode('utf-8'))
    }

    mock_groq_resp = MagicMock()
    mock_groq_resp.read.return_value = json.dumps({
        "choices": [
            {
                "message": {
                    "content": "Step Functions coordinates the processing workflow across tasks."
                }
            }
        ]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_groq_resp

    with patch.dict(os.environ, {
        "DOCUMENTS_BUCKET": "test-bucket",
        "DOCUMENTS_TABLE": "test-table",
        "GROQ_API_KEY": "gsk-mockkey12345"
    }):
        event = {
            "body": json.dumps({"question": "How does workflow coordination work?"}),
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {"sub": "user-123"}
                    }
                }
            }
        }
        res = ask_handler(event, None)
        assert res["statusCode"] == 200
        body = json.loads(res["body"])
        assert "Step Functions" in body["answer"]
        assert body["provider"] == "groq"
        assert len(body["sources"]) == 1
        assert body["sources"][0]["docId"] == "doc-1"
        assert body["sources"][0]["fileName"] == "arch.pdf"
        assert body["sources"][0]["similarity"] > 0.9
