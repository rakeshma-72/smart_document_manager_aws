import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

# Load module explicitly from backend/upload-url/app.py
HANDLER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend/upload-url/app.py"))
spec = importlib.util.spec_from_file_location("upload_url_module", HANDLER_PATH)
upload_url_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upload_url_module)

@patch.object(upload_url_module.dynamodb, "Table")
@patch.object(upload_url_module.s3_client, "generate_presigned_url")
def test_upload_url_success(mock_presigned, mock_table):
    mock_presigned.return_value = "https://mock-bucket.s3.amazonaws.com/test-key?signature=mock"
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-123-abc"
                    }
                }
            }
        },
        "body": json.dumps({
            "fileName": "report.pdf",
            "contentType": "application/pdf",
            "fileSize": 1048576
        })
    }

    response = upload_url_module.lambda_handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert "uploadUrl" in body
    assert body["uploadUrl"].startswith("https://mock-bucket.s3.amazonaws.com")
    assert "docId" in body
    assert "s3Key" in body
    assert body["s3Key"].startswith("uploads/user-123-abc/")
    assert mock_table_instance.put_item.called

def test_upload_url_unauthorized():
    event = {
        "requestContext": {},
        "body": json.dumps({"fileName": "sample.pdf", "contentType": "application/pdf"})
    }

    response = upload_url_module.lambda_handler(event, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert "Unauthorized" in body["error"]

def test_upload_url_invalid_content_type():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-123-abc"
                    }
                }
            }
        },
        "body": json.dumps({
            "fileName": "malicious.exe",
            "contentType": "application/x-msdownload"
        })
    }

    response = upload_url_module.lambda_handler(event, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Unsupported contentType" in body["error"]
