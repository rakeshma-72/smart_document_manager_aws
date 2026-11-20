import json
import os
import uuid
import datetime
import boto3
from botocore.config import Config

# Optimized connection reuse and regional endpoint configuration
boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    signature_version="s3v4",
    s3={"addressing_style": "virtual"},
    retries={"max_attempts": 3, "mode": "standard"},
)

s3_client = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    endpoint_url=f"https://s3.{os.environ.get('AWS_REGION', 'ap-southeast-2')}.amazonaws.com",
    config=boto_config,
)
dynamodb = boto3.resource("dynamodb", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET")
AUDIT_TABLE = os.environ.get("AUDIT_TABLE")
URL_EXPIRATION_SECONDS = int(os.environ.get("URL_EXPIRATION_SECONDS", "300"))

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff"
}

def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(body)
    }

def lambda_handler(event, context):
    """
    Generates a pre-signed S3 PUT URL for direct client uploads and
    initializes document metadata in DynamoDB.
    """
    try:
        # Extract authenticated user ID from JWT claims (API Gateway HTTP API v2)
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {})
        user_id = jwt_claims.get("sub")

        # Fallback for REST API / test events
        if not user_id:
            user_id = authorizer.get("claims", {}).get("sub") or event.get("headers", {}).get("x-user-id")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        body = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError:
                return build_response(400, {"error": "Invalid JSON request body"})

        file_name = body.get("fileName", "").strip()
        content_type = body.get("contentType", "").strip().lower()
        file_size = int(body.get("fileSize", 0))

        if not file_name:
            return build_response(400, {"error": "fileName is required"})

        if content_type not in ALLOWED_CONTENT_TYPES:
            return build_response(
                400,
                {
                    "error": f"Unsupported contentType '{content_type}'. Allowed: {list(ALLOWED_CONTENT_TYPES)}"
                }
            )

        doc_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Sanitize filename and create user-partitioned S3 key
        safe_name = os.path.basename(file_name).replace(" ", "_")
        s3_key = f"uploads/{user_id}/{doc_id}/{safe_name}"

        # Generate pre-signed PUT URL
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": DOCUMENTS_BUCKET,
                "Key": s3_key,
                "ContentType": content_type
            },
            ExpiresIn=URL_EXPIRATION_SECONDS
        )

        # Write initial record to DynamoDB
        table = dynamodb.Table(DOCUMENTS_TABLE)
        item = {
            "userId": user_id,
            "docId": doc_id,
            "fileName": safe_name,
            "contentType": content_type,
            "fileSize": file_size,
            "s3Key": s3_key,
            "status": "UPLOADED",
            "currentStep": "upload",
            "stepStatus": {},
            "createdAt": timestamp,
            "uploadedAt": timestamp,
            "updatedAt": timestamp,
            "tags": [],
            "summary": ""
        }
        table.put_item(Item=item)

        # Record best-effort UPLOAD audit event (zero file content/data logged)
        if AUDIT_TABLE:
            try:
                audit_table = dynamodb.Table(AUDIT_TABLE)
                source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
                import hashlib
                ip_hash = hashlib.sha256((source_ip or "anon").encode("utf-8")).hexdigest()[:16]
                audit_table.put_item(
                    Item={
                        "userId": user_id,
                        "eventKey": f"{timestamp}#{doc_id[:8]}",
                        "timestamp": timestamp,
                        "action": "UPLOAD",
                        "docId": doc_id,
                        "result": "SUCCESS",
                        "ipHash": ip_hash,
                        "ttl": int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + (90 * 86400)
                    }
                )
            except Exception as e:
                print(f"Warning: Audit log write failed: {e}")

        return build_response(
            201,
            {
                "uploadUrl": presigned_url,
                "docId": doc_id,
                "s3Key": s3_key,
                "expiresIn": URL_EXPIRATION_SECONDS
            }
        )

    except Exception as exc:
        print(f"Error generating upload URL: {str(exc)}")
        return build_response(500, {"error": "Internal server error generating upload URL"})
