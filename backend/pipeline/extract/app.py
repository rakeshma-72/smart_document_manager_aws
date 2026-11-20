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
bedrock_runtime = boto3.client("bedrock-runtime", config=boto_config)
dynamodb = boto3.resource("dynamodb", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")

BEDROCK_MULTIMODAL_MODEL_ID = os.environ.get(
    "BEDROCK_MULTIMODAL_MODEL_ID", "apac.amazon.nova-lite-v1:0"
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}
TEXT_EXTENSIONS = {".txt"}
MAX_EXTRACT_CHARS = 10000


def lambda_handler(event, context):
    """
    Step 2: Extract text from document and save extracted text to S3.
    Passes only S3 references (s3ExtractedKey, wordCount) to keep state small.
    """
    bucket = event["bucket"]
    key = event["key"]
    user_id = event["userId"]
    doc_id = event["docId"]
    file_ext = event["fileExt"].lower()

    s3_obj = s3_client.get_object(Bucket=bucket, Key=key)
    file_bytes = s3_obj["Body"].read()

    extracted_text = ""

    if file_ext in TEXT_EXTENSIONS:
        extracted_text = file_bytes.decode("utf-8", errors="replace")[:MAX_EXTRACT_CHARS]
    elif file_ext in IMAGE_EXTENSIONS or file_ext == ".pdf":
        fmt = "pdf" if file_ext == ".pdf" else ("png" if file_ext == ".png" else "jpeg")
        if file_ext in {".tiff", ".tif"}:
            fmt = "tiff"

        content_block = (
            {
                "document": {
                    "format": "pdf",
                    "name": "doc",
                    "source": {"bytes": file_bytes},
                }
            }
            if fmt == "pdf"
            else {
                "image": {
                    "format": fmt,
                    "source": {"bytes": file_bytes},
                }
            }
        )

        prompt = "Extract all text clearly and completely from this document. Output only the extracted text with no other conversation."

        try:
            resp = bedrock_runtime.converse(
                modelId=BEDROCK_MULTIMODAL_MODEL_ID,
                messages=[
                    {
                        "role": "user",
                        "content": [content_block, {"text": prompt}],
                    }
                ],
                inferenceConfig={"maxTokens": 1024, "temperature": 0.1},
            )
            content_list = resp.get("output", {}).get("message", {}).get("content", [])
            extracted_text = content_list[0].get("text", "") if content_list else ""
        except Exception as e:
            print(f"Bedrock multimodal extraction failed: {str(e)}")
            raise e
    else:
        raise ValueError(f"Unsupported format: {file_ext}")

    extracted_text = extracted_text.strip()[:MAX_EXTRACT_CHARS]
    word_count = len(extracted_text.split()) if extracted_text else 0
    preview = extracted_text[:500] if extracted_text else "No text detected."

    # Save extracted text to S3 - never pass full text through state machine
    extracted_key = f"extracted-text/{user_id}/{doc_id}/extracted.txt"
    s3_client.put_object(
        Bucket=bucket,
        Key=extracted_key,
        Body=extracted_text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )

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
                    "#step": "extract",
                    "#u": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":cs": "extract",
                    ":sval": {"status": "COMPLETED", "timestamp": now_iso},
                    ":updatedAt": now_iso
                }
            )
        except Exception as e:
            print(f"Warning: Failed to update progress in extract: {e}")

    return {
        "bucket": bucket,
        "key": key,
        "userId": user_id,
        "docId": doc_id,
        "fileName": event.get("fileName"),
        "fileExt": file_ext,
        "extractedTextKey": extracted_key,
        "preview": preview,
        "wordCount": word_count,
    }
