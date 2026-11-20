import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

HANDLER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend/search/app.py"))
spec = importlib.util.spec_from_file_location("search_module", HANDLER_PATH)
search_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search_module)

@patch.object(search_module.dynamodb, "Table")
def test_search_by_query_success(mock_table):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_table_instance.query.return_value = {
        "Items": [
            {
                "userId": "user-test-1",
                "docId": "doc-001",
                "fileName": "q3_tax_invoice.pdf",
                "summary": "Third quarter tax computation and invoice.",
                "tags": ["tax", "finance"],
                "preview": "Total tax owed is $500."
            },
            {
                "userId": "user-test-1",
                "docId": "doc-002",
                "fileName": "random_notes.txt",
                "summary": "Meeting notes with marketing team.",
                "tags": ["marketing"],
                "preview": "Discussed roadmap."
            }
        ]
    }

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-test-1"
                    }
                }
            }
        },
        "queryStringParameters": {
            "q": "invoice"
        }
    }

    response = search_module.lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["count"] == 1
    assert body["results"][0]["docId"] == "doc-001"
    assert mock_table_instance.query.called

@patch.object(search_module.dynamodb, "Table")
def test_search_by_tag_success(mock_table):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_table_instance.query.return_value = {
        "Items": [
            {
                "userId": "user-test-1",
                "docId": "doc-001",
                "fileName": "q3_tax.pdf",
                "tags": ["finance", "tax"]
            }
        ]
    }

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-test-1"
                    }
                }
            }
        },
        "queryStringParameters": {
            "tag": "finance"
        }
    }

    response = search_module.lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["count"] == 1
    assert "finance" in body["results"][0]["tags"]

def test_search_unauthorized():
    event = {
        "requestContext": {},
        "queryStringParameters": {"q": "anything"}
    }

    response = search_module.lambda_handler(event, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert "Unauthorized" in body["error"]
