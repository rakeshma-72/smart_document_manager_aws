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

# Exact model ID that passed Phase 0 verification in ap-southeast-2
BEDROCK_EMBED_MODEL_ID = os.environ.get(
    "BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"
)


def embed_text(text: str) -> list:
    """Generates embedding vector using Amazon Titan Text Embeddings V2."""
    clean = text[:8000].strip()
    if not clean:
        clean = "empty document chunk"

    body = json.dumps({"inputText": clean})
    resp = bedrock_runtime.invoke_model(
        modelId=BEDROCK_EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    resp_body = json.loads(resp["body"].read().decode("utf-8"))
    return resp_body.get("embedding", [])


def lambda_handler(event, context):
    """
    Pipeline Step: EmbedChunks
    Reads chunks.json from S3, generates embeddings for each chunk via Bedrock,
    and writes embeddings.json to S3. Never passes vector floats in state payload.
    """
    bucket = event.get("bucket") or os.environ.get("DOCUMENTS_BUCKET")
    user_id = event["userId"]
    doc_id = event["docId"]
    chunks_key = event.get("chunksKey")

    if not chunks_key:
        raise ValueError("Missing chunksKey in event")

    s3_obj = s3_client.get_object(Bucket=bucket, Key=chunks_key)
    chunks = json.loads(s3_obj["Body"].read().decode("utf-8"))

    embedded_chunks = []
    for chunk in chunks:
        vec = embed_text(chunk["text"])
        embedded_chunks.append({
            "chunkIndex": chunk["chunkIndex"],
            "text": chunk["text"],
            "vector": vec,
        })

    embeddings_key = f"embeddings/{user_id}/{doc_id}/embeddings.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=embeddings_key,
        Body=json.dumps(embedded_chunks).encode("utf-8"),
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
                    "#step": "embed_chunks",
                    "#u": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":cs": "embed_chunks",
                    ":sval": {"status": "COMPLETED", "timestamp": now_iso},
                    ":updatedAt": now_iso
                }
            )
        except Exception as e:
            print(f"Warning: Failed to update progress in embed_chunks: {e}")

    output = dict(event)
    output["embeddingsKey"] = embeddings_key
    output["embeddedChunkCount"] = len(embedded_chunks)
    return output
