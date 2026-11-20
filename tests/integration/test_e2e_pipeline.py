import io
import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

# Dynamically import backend handlers
def load_handler(relative_path, module_name):
    full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

upload_mod = load_handler("../../backend/upload-url/app.py", "e2e_upload_mod")
processor_mod = load_handler("../../backend/processor/app.py", "e2e_processor_mod")
search_mod = load_handler("../../backend/search/app.py", "e2e_search_mod")
list_mod = load_handler("../../backend/list-docs/app.py", "e2e_list_mod")

def test_end_to_end_document_lifecycle():
    """
    End-to-End integration test covering the complete document lifecycle:
    1. User requests pre-signed URL to upload 'annual_financial_report.pdf'.
    2. S3 ObjectCreated event triggers the processor Lambda.
    3. Textract extracts text and Bedrock generates summary and tags.
    4. User lists documents and verifies status transitions to PROCESSED.
    5. User executes search and finds document by keyword and tag.
    """
    user_id = "test-user-e2e-001"
    in_memory_db = {}
    in_memory_s3 = {}

    # Mock DynamoDB table methods for upload, processing, search, list
    class MockDynamoTable:
        def put_item(self, Item):
            key = (Item["userId"], Item["docId"])
            in_memory_db[key] = Item

        def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues):
            key = (Key["userId"], Key["docId"])
            item = in_memory_db.get(key, {})
            # Emulate status and attribute updates
            if ":status" in ExpressionAttributeValues:
                item["status"] = ExpressionAttributeValues[":status"]
            if ":summary" in ExpressionAttributeValues:
                item["summary"] = ExpressionAttributeValues[":summary"]
            if ":tags" in ExpressionAttributeValues:
                item["tags"] = ExpressionAttributeValues[":tags"]
            if ":preview" in ExpressionAttributeValues:
                item["preview"] = ExpressionAttributeValues[":preview"]
            if ":extractedTextKey" in ExpressionAttributeValues:
                item["extractedTextKey"] = ExpressionAttributeValues[":extractedTextKey"]
            in_memory_db[key] = item

        def query(self, **kwargs):
            # Emulate user scoped query
            items = [v for (uid, _), v in in_memory_db.items() if uid == user_id]
            return {"Items": items}

        def get_item(self, Key):
            key = (Key["userId"], Key["docId"])
            return {"Item": in_memory_db.get(key)}

    mock_table = MockDynamoTable()

    # Step 1: Request pre-signed URL
    with patch.object(upload_mod.dynamodb, "Table", return_value=mock_table), \
         patch.object(upload_mod.s3_client, "generate_presigned_url", return_value="https://s3.amazonaws.com/presigned-put"):
        
        event_upload = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_id}}}
            },
            "body": json.dumps({
                "fileName": "annual_financial_report.pdf",
                "contentType": "application/pdf",
                "fileSize": 2048000
            })
        }
        res_upload = upload_mod.lambda_handler(event_upload, None)
        assert res_upload["statusCode"] == 201
        upload_data = json.loads(res_upload["body"])
        doc_id = upload_data["docId"]
        s3_key = upload_data["s3Key"]

        # Verify initial DynamoDB state
        assert (user_id, doc_id) in in_memory_db
        assert in_memory_db[(user_id, doc_id)]["status"] == "UPLOADED"

    # Step 2: S3 ObjectCreated Event triggers Processor Lambda
    def mock_get_s3(Bucket, Key):
        return {
            "ContentLength": 1024,
            "Body": io.BytesIO(b"%PDF-1.4 mock financial report bytes"),
        }

    def mock_put_s3(Bucket, Key, Body, ContentType=None):
        in_memory_s3[Key] = Body

    with patch.object(processor_mod.dynamodb, "Table", return_value=mock_table), \
         patch.object(processor_mod.s3_client, "get_object", side_effect=mock_get_s3), \
         patch.object(processor_mod.s3_client, "put_object", side_effect=mock_put_s3), \
         patch.object(processor_mod, "process_multimodal_document", return_value={
             "extracted_text": "Acme Corp Annual Financial Report 2026. Total revenue grew by 24% with net profit of $1.2M. Key investments in serverless AWS architecture and generative AI.",
             "summary": "Annual financial results reporting 24% revenue growth and cloud investments.",
             "tags": ["financial", "revenue", "serverless", "growth"]
         }):

        event_s3 = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "smart-doc-mgr-dev-docs"},
                        "object": {"key": s3_key}
                    }
                }
            ]
        }

        res_proc = processor_mod.lambda_handler(event_s3, None)
        assert res_proc["statusCode"] == 200

        # Verify DynamoDB item has transitioned to PROCESSED with AI summary and tags
        processed_item = in_memory_db[(user_id, doc_id)]
        assert processed_item["status"] == "PROCESSED"
        assert "revenue" in processed_item["tags"]
        assert len(processed_item["summary"]) > 20
        assert f"extracted-text/{user_id}/{doc_id}/extracted.txt" in in_memory_s3

    # Step 3: Verify User Document List
    with patch.object(list_mod.dynamodb, "Table", return_value=mock_table):
        event_list = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_id}}}
            }
        }
        res_list = list_mod.lambda_handler(event_list, None)
        assert res_list["statusCode"] == 200
        list_body = json.loads(res_list["body"])
        assert list_body["count"] == 1
        assert list_body["documents"][0]["docId"] == doc_id
        assert list_body["documents"][0]["status"] == "PROCESSED"

    # Step 4: Verify Search by keyword ('revenue')
    with patch.object(search_mod.dynamodb, "Table", return_value=mock_table):
        event_search_kw = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_id}}}
            },
            "queryStringParameters": {"q": "revenue"}
        }
        res_search_kw = search_mod.lambda_handler(event_search_kw, None)
        assert res_search_kw["statusCode"] == 200
        search_body = json.loads(res_search_kw["body"])
        assert search_body["count"] == 1
        assert search_body["results"][0]["docId"] == doc_id

    # Step 5: Verify Search by tag ('serverless')
    with patch.object(search_mod.dynamodb, "Table", return_value=mock_table):
        event_search_tag = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_id}}}
            },
            "queryStringParameters": {"tag": "serverless"}
        }
        res_search_tag = search_mod.lambda_handler(event_search_tag, None)
        assert res_search_tag["statusCode"] == 200
        tag_body = json.loads(res_search_tag["body"])
        assert tag_body["count"] == 1
        assert "serverless" in tag_body["results"][0]["tags"]
