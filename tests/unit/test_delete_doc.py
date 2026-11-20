import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

HANDLER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend/delete-doc/app.py"))
spec = importlib.util.spec_from_file_location("delete_doc_module", HANDLER_PATH)
delete_doc_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delete_doc_module)

@patch.object(delete_doc_module.s3_client, "get_paginator")
@patch.object(delete_doc_module.s3_client, "delete_object")
@patch.object(delete_doc_module.dynamodb, "Table")
def test_delete_doc_success(mock_table, mock_s3_delete, mock_paginator):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_table_instance.get_item.return_value = {
        "Item": {
            "userId": "user-del-1",
            "docId": "doc-del-123",
            "s3Key": "uploads/user-del-1/doc-del-123/file.pdf",
            "extractedTextKey": "extracted-text/user-del-1/doc-del-123/extracted.txt",
            "chunksKey": "chunks/user-del-1/doc-del-123/chunks.json"
        }
    }

    mock_pag_instance = MagicMock()
    mock_paginator.return_value = mock_pag_instance
    mock_pag_instance.paginate.return_value = [
        {"Contents": [{"Key": "embeddings/user-del-1/doc-del-123/embeddings.json"}]}
    ]

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-del-1"
                    }
                }
            }
        },
        "pathParameters": {
            "docId": "doc-del-123"
        }
    }

    response = delete_doc_module.lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["docId"] == "doc-del-123"
    # S3 deletes called for: original upload, extracted text, chunks.json, and embeddings.json
    assert mock_s3_delete.call_count >= 4
    assert mock_table_instance.delete_item.called


@patch.object(delete_doc_module.dynamodb, "Table")
def test_delete_doc_not_found(mock_table):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance
    mock_table_instance.get_item.return_value = {} # Document not found for this user

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-del-1"
                    }
                }
            }
        },
        "pathParameters": {
            "docId": "doc-nonexistent"
        }
    }

    response = delete_doc_module.lambda_handler(event, None)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "not found" in body["error"].lower()

def test_delete_doc_unauthorized():
    event = {
        "requestContext": {},
        "pathParameters": {"docId": "doc-123"}
    }

    response = delete_doc_module.lambda_handler(event, None)
    assert response["statusCode"] == 401
