import os
import re
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

PATTERNS = {
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
}


def lambda_handler(event, context):
    """
    Step 4: Detect PII from extracted text using regex.
    Reads extracted text from S3; never puts text in state payload.
    """
    bucket = event["bucket"]
    extracted_key = event["extractedTextKey"]
    user_id = event.get("userId")
    doc_id = event.get("docId")

    s3_obj = s3_client.get_object(Bucket=bucket, Key=extracted_key)
    text = s3_obj["Body"].read().decode("utf-8", errors="replace")

    detected = set()
    for pii_name, pattern in PATTERNS.items():
        if re.search(pattern, text):
            detected.add(pii_name)

    # Record pipeline progress
    if DOCUMENTS_TABLE and user_id and doc_id:
        try:
            table = dynamodb.Table(DOCUMENTS_TABLE)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            table.update_item(
                Key={"userId": user_id, "docId": doc_id},
                UpdateExpression="SET currentStep = :cs, #st.#step = :sval, #u = :updatedAt",
                ExpressionAttributeNames={
                    "#st": "stepStatus",
                    "#step": "detect_pii",
                    "#u": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":cs": "detect_pii",
                    ":sval": {"status": "COMPLETED", "timestamp": now_iso},
                    ":updatedAt": now_iso
                }
            )
        except Exception as e:
            print(f"Warning: Failed to update progress in detect_pii: {e}")

    output = dict(event)
    output["piiEntities"] = sorted(list(detected))
    return output
