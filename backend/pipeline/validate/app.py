import json
import os
import time
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)

s3_client = boto3.client("s3", config=boto_config)
dynamodb = boto3.resource("dynamodb", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".txt"}
MAX_FILE_BYTES = 4 * 1024 * 1024  # 4 MB (Bedrock Converse API document limit safe ceiling)


class ValidationError(Exception):
    """Non-retryable validation error."""
    pass


def lambda_handler(event, context):
    """
    Step 1: Validate file existence, size, and extension.
    Transitions DynamoDB status to PROCESSING.
    """
    bucket = event.get("bucket")
    key = event.get("key")
    user_id = event.get("userId")
    doc_id = event.get("docId")
    file_ext = event.get("fileExt", "").lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension: {file_ext}")

    try:
        head = s3_client.head_object(Bucket=bucket, Key=key)
        content_length = head.get("ContentLength", 0)
        if content_length > MAX_FILE_BYTES:
            raise ValidationError(
                f"File size {content_length} bytes exceeds maximum allowed limit {MAX_FILE_BYTES} bytes"
            )
    except ValidationError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to inspect uploaded file in S3: {str(e)}")

    # Update status to PROCESSING and track pipeline progress
    table = dynamodb.Table(DOCUMENTS_TABLE)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Ensure stepStatus map exists on item for safe nested attribute updates
    try:
        table.update_item(
            Key={"userId": user_id, "docId": doc_id},
            UpdateExpression="SET stepStatus = if_not_exists(stepStatus, :empty_map)",
            ExpressionAttributeValues={":empty_map": {}}
        )
    except Exception as e:
        print(f"Warning: Failed to ensure stepStatus map exists: {e}")

    table.update_item(
        Key={"userId": user_id, "docId": doc_id},
        UpdateExpression="SET #s = :status, #u = :updatedAt, currentStep = :cs, #st.#step = :sval",
        ExpressionAttributeNames={
            "#s": "status",
            "#u": "updatedAt",
            "#st": "stepStatus",
            "#step": "validate"
        },
        ExpressionAttributeValues={
            ":status": "PROCESSING",
            ":updatedAt": now_iso,
            ":cs": "validate",
            ":sval": {
                "status": "COMPLETED",
                "timestamp": now_iso
            }
        },
    )

    return {
        "bucket": bucket,
        "key": key,
        "userId": user_id,
        "docId": doc_id,
        "fileName": event.get("fileName"),
        "fileExt": file_ext,
        "contentLength": content_length,
    }
