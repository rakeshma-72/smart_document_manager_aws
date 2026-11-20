import json
import os
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"}
)

s3_client = boto3.client("s3", config=boto_config)
dynamodb = boto3.resource("dynamodb", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET")
SHARES_TABLE = os.environ.get("SHARES_TABLE")
AUDIT_TABLE = os.environ.get("AUDIT_TABLE")

def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET,DELETE"
        },
        "body": json.dumps(body)
    }

def lambda_handler(event, context):
    """
    Deletes a document:
    1. Validates ownership via Cognito JWT claims.
    2. Removes original file and extracted text from S3.
    3. Deletes item from DynamoDB.
    """
    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {})
        user_id = jwt_claims.get("sub")

        if not user_id:
            user_id = authorizer.get("claims", {}).get("sub") or event.get("headers", {}).get("x-user-id")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        path_params = event.get("pathParameters") or {}
        doc_id = path_params.get("docId")

        if not doc_id:
            return build_response(400, {"error": "docId path parameter is required"})

        table = dynamodb.Table(DOCUMENTS_TABLE)
        get_res = table.get_item(Key={"userId": user_id, "docId": doc_id})
        item = get_res.get("Item")

        if not item:
            return build_response(404, {"error": "Document not found or access denied"})

        # Delete S3 objects
        # 1. Original uploaded file
        s3_key = item.get("s3Key")
        if s3_key:
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
            except Exception as e:
                print(f"Warning: Failed to delete S3 upload object {s3_key}: {e}")

        # 2. Extracted text file / prefix
        extracted_keys = [
            item.get("extractedTextKey"),
            f"extracted-text/{user_id}/{doc_id}/extracted.txt",
            f"extracted-text/{user_id}/{doc_id}.txt"
        ]
        for ek in set(filter(None, extracted_keys)):
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=ek)
            except Exception as e:
                print(f"Warning: Failed to delete S3 extracted text {ek}: {e}")

        # 3. Chunks file / prefix: chunks/{userId}/{docId}/chunks.json
        chunk_keys = [
            item.get("chunksKey"),
            f"chunks/{user_id}/{doc_id}/chunks.json"
        ]
        for ck in set(filter(None, chunk_keys)):
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=ck)
            except Exception as e:
                print(f"Warning: Failed to delete S3 chunk file {ck}: {e}")

        # 4. Embeddings file / prefix: embeddings/{userId}/{docId}/embeddings.json
        # Also delete any objects with prefix embeddings/{userId}/{docId}/
        embeddings_prefix = f"embeddings/{user_id}/{doc_id}/"
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=DOCUMENTS_BUCKET, Prefix=embeddings_prefix):
                for obj in page.get("Contents", []):
                    s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=obj["Key"])
        except Exception as e:
            print(f"Warning: Failed to clean up embeddings prefix {embeddings_prefix}: {e}")

        # 5. Revoke / delete all share records for this document
        if SHARES_TABLE:
            try:
                shares_table = dynamodb.Table(SHARES_TABLE)
                share_res = shares_table.query(
                    IndexName="docId-index",
                    KeyConditionExpression="docId = :d",
                    ExpressionAttributeValues={":d": doc_id}
                )
                for s_item in share_res.get("Items", []):
                    shares_table.delete_item(Key={"tokenHash": s_item["tokenHash"]})
            except Exception as e:
                print(f"Warning: Failed to delete document shares: {e}")

        # Delete from DynamoDB
        table.delete_item(Key={"userId": user_id, "docId": doc_id})

        # Record Audit event (best-effort)
        if AUDIT_TABLE:
            try:
                audit_table = dynamodb.Table(AUDIT_TABLE)
                now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                audit_table.put_item(
                    Item={
                        "userId": user_id,
                        "eventKey": f"{now_iso}#{os.urandom(4).hex()}",
                        "timestamp": now_iso,
                        "action": "DELETE",
                        "docId": doc_id,
                        "result": "SUCCESS",
                        "ttl": int(time.time()) + (90 * 86400)
                    }
                )
            except Exception as e:
                print(f"Warning: Audit log failed: {e}")

        return build_response(
            200,
            {
                "message": "Document deleted successfully",
                "docId": doc_id
            }
        )

    except Exception as exc:
        print(f"Error deleting document: {str(exc)}")
        return build_response(500, {"error": "Internal server error deleting document"})
