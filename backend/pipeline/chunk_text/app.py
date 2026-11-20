import json
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

# Token approximation: ~4 characters per token. 500 tokens ~ 2000 chars. 100 token overlap ~ 400 chars.
CHUNK_SIZE_CHARS = 2000
CHUNK_OVERLAP_CHARS = 400
MAX_CHUNKS_PER_DOC = 25  # Limit chunks per document for predictable vector scan and storage


def split_text_into_chunks(text: str) -> list:
    """
    Splits text into overlapping chunks of approx 500 tokens (2000 characters)
    with 100 token (400 characters) overlap. Respects paragraph/sentence boundaries where feasible.
    """
    if not text or not text.strip():
        return []

    clean_text = text.strip()
    if len(clean_text) <= CHUNK_SIZE_CHARS:
        return [{"chunkIndex": 0, "text": clean_text}]

    chunks = []
    start = 0
    text_len = len(clean_text)
    chunk_idx = 0

    while start < text_len and len(chunks) < MAX_CHUNKS_PER_DOC:
        end = min(start + CHUNK_SIZE_CHARS, text_len)
        # Try to break at a newline or sentence boundary if not at the very end
        if end < text_len:
            boundary = clean_text.rfind("\n", start, end)
            if boundary == -1 or boundary <= start + (CHUNK_SIZE_CHARS // 2):
                boundary = clean_text.rfind(". ", start, end)
            if boundary != -1 and boundary > start + (CHUNK_SIZE_CHARS // 2):
                end = boundary + (1 if clean_text[boundary] == "\n" else 2)

        chunk_str = clean_text[start:end].strip()
        if chunk_str:
            chunks.append({
                "chunkIndex": chunk_idx,
                "text": chunk_str
            })
            chunk_idx += 1

        if end >= text_len:
            break

        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)

    return chunks


def lambda_handler(event, context):
    """
    Pipeline Step: ChunkText
    Reads extracted.txt from S3, splits into overlapping chunks,
    and writes chunks.json to S3. Never passes chunk text in state payload.
    """
    bucket = event.get("bucket") or os.environ.get("DOCUMENTS_BUCKET")
    user_id = event["userId"]
    doc_id = event["docId"]
    extracted_text_key = event.get("extractedTextKey")

    if not extracted_text_key:
        raise ValueError("Missing extractedTextKey in event")

    s3_obj = s3_client.get_object(Bucket=bucket, Key=extracted_text_key)
    raw_text = s3_obj["Body"].read().decode("utf-8", errors="replace")

    chunks = split_text_into_chunks(raw_text)

    chunks_key = f"chunks/{user_id}/{doc_id}/chunks.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=chunks_key,
        Body=json.dumps(chunks).encode("utf-8"),
        ContentType="application/json",
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
                    "#step": "chunk_text",
                    "#u": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":cs": "chunk_text",
                    ":sval": {"status": "COMPLETED", "timestamp": now_iso},
                    ":updatedAt": now_iso
                }
            )
        except Exception as e:
            print(f"Warning: Failed to update progress in chunk_text: {e}")

    output = dict(event)
    output["chunksKey"] = chunks_key
    output["chunkCount"] = len(chunks)
    return output

handler = lambda_handler

