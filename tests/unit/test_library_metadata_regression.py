import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# Import list-docs
list_docs_path = os.path.join(ROOT_DIR, "backend/list-docs/app.py")
spec = importlib.util.spec_from_file_location("list_docs_mod", list_docs_path)
list_docs_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(list_docs_mod)

# Import validate
validate_path = os.path.join(ROOT_DIR, "backend/pipeline/validate/app.py")
spec = importlib.util.spec_from_file_location("validate_mod", validate_path)
validate_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_mod)

# Import notify_failure
notify_path = os.path.join(ROOT_DIR, "backend/pipeline/notify_failure/app.py")
spec = importlib.util.spec_from_file_location("notify_failure_mod", notify_path)
notify_failure_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify_failure_mod)

# Import save_results
save_path = os.path.join(ROOT_DIR, "backend/pipeline/save_results/app.py")
spec = importlib.util.spec_from_file_location("save_results_mod", save_path)
save_results_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(save_results_mod)


def test_validate_ensures_step_status_map_exists_for_fresh_upload():
    """Validates that ValidateFile initializes stepStatus if missing, avoiding ValidationException."""
    mock_table = MagicMock()
    with patch.object(validate_mod.dynamodb, "Table", return_value=mock_table), \
         patch.object(validate_mod.s3_client, "head_object", return_value={"ContentLength": 500}):

        event = {
            "bucket": "test-bucket",
            "key": "uploads/user-1/doc-1/test.pdf",
            "userId": "user-1",
            "docId": "doc-1",
            "fileName": "test.pdf",
            "fileExt": ".pdf",
        }
        res = validate_mod.lambda_handler(event, None)
        assert res["docId"] == "doc-1"

        # Verify update calls: 1 to ensure stepStatus map, 2 to set processing & step
        assert mock_table.update_item.call_count == 2
        first_call = mock_table.update_item.call_args_list[0]
        assert "if_not_exists(stepStatus, :empty_map)" in first_call[1]["UpdateExpression"]

        second_call = mock_table.update_item.call_args_list[1]
        assert second_call[1]["ExpressionAttributeValues"][":status"] == "PROCESSING"
        assert second_call[1]["ExpressionAttributeValues"][":cs"] == "validate"


def test_notify_failure_ensures_step_status_map_and_sets_safe_error():
    """Ensures NotifyFailure handles documents where stepStatus was not initialized without crashing."""
    mock_table = MagicMock()
    mock_sqs = MagicMock()
    with patch.object(notify_failure_mod.dynamodb, "Table", return_value=mock_table), \
         patch.object(notify_failure_mod.sqs, "send_message", mock_sqs):

        event = {
            "ExecutionInput": {"userId": "user-1", "docId": "doc-failed"},
            "Error": {"Error": "RuntimeError", "Cause": "Something went wrong"},
            "FailingStep": "extract",
        }
        res = notify_failure_mod.lambda_handler(event, None)
        assert res["status"] == "FAILED"
        assert res["failedStep"] == "extract"

        # First call ensures stepStatus map
        first_call = mock_table.update_item.call_args_list[0]
        assert "if_not_exists(stepStatus, :empty_map)" in first_call[1]["UpdateExpression"]

        # Second call sets FAILED status and safe error code
        second_call = mock_table.update_item.call_args_list[1]
        assert second_call[1]["ExpressionAttributeValues"][":status"] == "FAILED"
        assert second_call[1]["ExpressionAttributeValues"][":errorCode"] == "RuntimeError"
        assert second_call[1]["ExpressionAttributeValues"][":failedStep"] == "extract"


def test_save_results_persists_classification_summary_and_fields():
    """Verifies SaveResults persists docType, summary, tags, and keyFields."""
    mock_table = MagicMock()
    with patch.object(save_results_mod.dynamodb, "Table", return_value=mock_table):
        event = {
            "userId": "user-abc",
            "docId": "doc-xyz",
            "extractedTextKey": "extracted-text/user-abc/doc-xyz/extracted.txt",
            "preview": "Test preview",
            "wordCount": 150,
            "summary": "This is an executive summary of the document.",
            "tags": ["cloud", "architecture"],
            "docType": "report",
            "keyFields": [{"label": "Author", "value": "Alice"}],
            "summaryProvider": "groq",
        }
        res = save_results_mod.lambda_handler(event, None)
        assert res["status"] == "PROCESSED"
        assert res["docType"] == "report"
        assert res["summary"] == "This is an executive summary of the document."

        call_args = mock_table.update_item.call_args[1]
        values = call_args["ExpressionAttributeValues"]
        assert values[":status"] == "PROCESSED"
        assert values[":docType"] == "report"
        assert values[":summary"] == "This is an executive summary of the document."
        assert len(values[":keyFields"]) == 1


def test_list_docs_returns_real_metadata_without_hardcoded_overrides():
    """Confirms GET /documents returns actual DynamoDB metadata for the user."""
    mock_table = MagicMock()
    mock_table.query.return_value = {
        "Items": [
            {
                "userId": "user-test",
                "docId": "doc-1",
                "fileName": "report.pdf",
                "status": "PROCESSED",
                "docType": "report",
                "summary": "Detailed financial report summary.",
                "keyFields": [{"label": "Total", "value": "$5000"}],
                "tags": ["finance"],
            },
            {
                "userId": "user-test",
                "docId": "doc-2",
                "fileName": "invoice.pdf",
                "status": "PROCESSING",
                "currentStep": "extract",
                "docType": "invoice",
                "summary": "",
            },
            {
                "userId": "user-test",
                "docId": "doc-3",
                "fileName": "broken.pdf",
                "status": "FAILED",
                "errorCode": "ValidationError",
                "failedStep": "validate",
            },
        ]
    }

    with patch.object(list_docs_mod.dynamodb, "Table", return_value=mock_table):
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-test"
                        }
                    }
                }
            }
        }
        resp = list_docs_mod.lambda_handler(event, None)
        assert resp["statusCode"] == 200
        data = json.loads(resp["body"])
        docs = data["documents"]
        assert len(docs) == 3

        # Document 1 (PROCESSED)
        assert docs[0]["status"] == "PROCESSED"
        assert docs[0]["docType"] == "report"
        assert docs[0]["summary"] == "Detailed financial report summary."
        assert docs[0]["keyFields"][0]["value"] == "$5000"

        # Document 2 (PROCESSING)
        assert docs[1]["status"] == "PROCESSING"
        assert docs[1]["currentStep"] == "extract"

        # Document 3 (FAILED)
        assert docs[2]["status"] == "FAILED"
        assert docs[2]["errorCode"] == "ValidationError"
