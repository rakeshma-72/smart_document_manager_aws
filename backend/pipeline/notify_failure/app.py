import json
import os
import time
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)

dynamodb = boto3.resource("dynamodb", config=boto_config)
sqs = boto3.client("sqs", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
DLQ_URL = os.environ.get("DLQ_URL")


def lambda_handler(event, context):
    """
    Step 6 (Catch/Failure Handler):
    - Sets DynamoDB status to FAILED with safe error code and failing step name only
    - Never stores error message text or raw document content
    - Sends failure record to SQS DLQ (IDs and error code ONLY)
    """
    execution_input = event.get("ExecutionInput", {})
    user_id = execution_input.get("userId")
    doc_id = execution_input.get("docId")

    error_info = event.get("Error", {})
    error_type = error_info.get("Error", "PipelineExecutionError")
    
    # Extract safe error code and step name without leaking sensitive message/stack trace text
    safe_error_code = str(error_type).split(".")[-1]
    if not safe_error_code or len(safe_error_code) > 64:
        safe_error_code = "ProcessingError"

    # Identify failing step if known from context or error name
    failing_step = event.get("FailingStep", "pipeline")

    print(f"Handling failure for docId={doc_id}, userId={user_id}: step={failing_step}, code={safe_error_code}")

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 1. Update DynamoDB item if userId and docId exist
    # Safe error code and failing step only, never raw message text
    if user_id and doc_id:
        try:
            table = dynamodb.Table(DOCUMENTS_TABLE)
            # Ensure stepStatus map exists on item for safe nested attribute updates
            try:
                table.update_item(
                    Key={"userId": user_id, "docId": doc_id},
                    UpdateExpression="SET stepStatus = if_not_exists(stepStatus, :empty_map)",
                    ExpressionAttributeValues={":empty_map": {}}
                )
            except Exception as ex_init:
                print(f"Warning: Failed to ensure stepStatus map exists on failure: {ex_init}")

            table.update_item(
                Key={"userId": user_id, "docId": doc_id},
                UpdateExpression="SET #s = :status, #u = :updatedAt, #pr = :processedAt, #err = :errorCode, #fs = :failedStep, currentStep = :cs, #st.#step = :sval",
                ExpressionAttributeNames={
                    "#s": "status",
                    "#u": "updatedAt",
                    "#pr": "processedAt",
                    "#err": "errorCode",
                    "#fs": "failedStep",
                    "#st": "stepStatus",
                    "#step": failing_step,
                },
                ExpressionAttributeValues={
                    ":status": "FAILED",
                    ":updatedAt": now_iso,
                    ":processedAt": now_iso,
                    ":errorCode": safe_error_code,
                    ":failedStep": failing_step,
                    ":cs": failing_step,
                    ":sval": {"status": "FAILED", "errorCode": safe_error_code, "timestamp": now_iso},
                },
            )
        except Exception as e:
            print(f"Failed to update DynamoDB status to FAILED: {str(e)}")

    # 2. Publish failure event to SQS DLQ (IDs and safe error code ONLY - zero document text)
    dlq_payload = {
        "docId": doc_id,
        "userId": user_id,
        "failedStep": failing_step,
        "errorCode": safe_error_code,
        "timestamp": now_iso,
    }

    if DLQ_URL:
        try:
            sqs.send_message(
                QueueUrl=DLQ_URL,
                MessageBody=json.dumps(dlq_payload),
            )
            print("Dispatched failure notice to DLQ.")
        except Exception as e:
            print(f"Failed to publish to DLQ: {str(e)}")

    return {"status": "FAILED", "docId": doc_id, "failedStep": failing_step, "errorCode": safe_error_code}
