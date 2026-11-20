import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

HANDLER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend/list-docs/app.py"))
spec = importlib.util.spec_from_file_location("list_docs_module", HANDLER_PATH)
list_docs_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(list_docs_module)

@patch.object(list_docs_module.dynamodb, "Table")
def test_list_docs_success(mock_table):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_table_instance.query.return_value = {
        "Items": [
            {
                "userId": "user-123-abc",
                "docId": "doc-001",
                "fileName": "invoice.pdf",
                "contentType": "application/pdf",
                "status": "PROCESSED",
                "createdAt": "2026-11-03T00:00:00Z"
            }
        ]
    }

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-123-abc"
                    }
                }
            }
        }
    }

    response = list_docs_module.lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "documents" in body
    assert len(body["documents"]) == 1
    assert body["documents"][0]["docId"] == "doc-001"
    assert mock_table_instance.query.called

def test_list_docs_unauthorized():
    event = {
        "requestContext": {}
    }

    response = list_docs_module.lambda_handler(event, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert "Unauthorized" in body["error"]
