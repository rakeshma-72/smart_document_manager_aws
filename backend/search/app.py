import json
import math
import os
import time
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"}
)

dynamodb = boto3.resource("dynamodb", config=boto_config)
s3_client = boto3.client("s3", config=boto_config)
bedrock_runtime = boto3.client("bedrock-runtime", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET")
BEDROCK_EMBED_MODEL_ID = os.environ.get(
    "BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"
)

MAX_QUERY_LENGTH = 500
SIMILARITY_THRESHOLD = 0.45
DAILY_SEARCH_LIMIT = 100


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(body, default=str)
    }


def cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def check_and_increment_daily_search_limit(user_id: str) -> tuple[bool, int]:
    """
    Checks per-user daily search limit and increments count in DynamoDB.
    Returns (allowed, current_count).
    """
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    usage_doc_id = f"USAGE#{today_str}"
    table = dynamodb.Table(DOCUMENTS_TABLE)
    now_epoch = int(time.time())
    ttl_epoch = now_epoch + (30 * 86400)

    try:
        resp = table.get_item(Key={"userId": user_id, "docId": usage_doc_id})
        count = int(resp.get("Item", {}).get("searchCount", 0))
        if count >= DAILY_SEARCH_LIMIT:
            return False, count

        update_resp = table.update_item(
            Key={"userId": user_id, "docId": usage_doc_id},
            UpdateExpression="ADD searchCount :inc SET updatedAt = :now, recordType = :rtype, #ttl = :ttl, #dt = :dt",
            ExpressionAttributeNames={
                "#ttl": "ttl",
                "#dt": "date"
            },
            ExpressionAttributeValues={
                ":inc": 1,
                ":now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ":rtype": "DAILY_USAGE",
                ":ttl": ttl_epoch,
                ":dt": today_str
            },
            ReturnValues="UPDATED_NEW"
        )
        new_count = int(update_resp.get("Attributes", {}).get("searchCount", count + 1))
        return True, new_count
    except Exception as e:
        print(f"Warning: Daily usage check in search failed: {e}")
        return True, 0


def embed_search_query(text: str) -> list:
    """Embeds user search query with Amazon Titan Embeddings V2."""
    clean = text[:MAX_QUERY_LENGTH].strip()
    body = json.dumps({"inputText": clean})
    resp = bedrock_runtime.invoke_model(
        modelId=BEDROCK_EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(resp["body"].read().decode("utf-8"))
    return result.get("embedding", [])


def retrieve_user_chunks_for_search(user_id: str, doc_map: dict) -> list:
    """
    Reads embeddings strictly for the authenticated user (embeddings/{userId}/*).
    """
    if not DOCUMENTS_BUCKET:
        return []

    prefix = f"embeddings/{user_id}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    chunks = []

    try:
        for page in paginator.paginate(Bucket=DOCUMENTS_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")
                if len(parts) >= 4 and parts[-1] == "embeddings.json":
                    doc_id = parts[2]
                    doc_item = doc_map.get(doc_id, {})
                    try:
                        s3_data = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=key)
                        raw_chunks = json.loads(s3_data["Body"].read().decode("utf-8"))
                        for ch in raw_chunks:
                            chunks.append({
                                "docId": doc_id,
                                "document": doc_item,
                                "chunkIndex": ch.get("chunkIndex", 0),
                                "text": ch.get("text", ""),
                                "vector": ch.get("vector", []),
                            })
                    except Exception as err:
                        print(f"Warning: Could not read chunk for {doc_id}: {err}")
    except Exception as e:
        print(f"Warning: Could not list user embeddings: {e}")

    return chunks


def perform_keyword_search(items: list, search_query: str, tag_filter: str) -> list:
    refined_items = []
    for item in items:
        fname = item.get("fileName", "").lower()
        summary = item.get("summary", "").lower()
        preview = item.get("preview", "").lower()
        tags = [str(t).lower() for t in item.get("tags", [])]
        doc_type = str(item.get("docType", "")).lower()

        matches_query = True
        if search_query:
            matches_query = (
                search_query in fname or
                search_query in summary or
                search_query in preview or
                search_query in doc_type or
                any(search_query in t for t in tags)
            )

        matches_tag = True
        if tag_filter:
            matches_tag = any(tag_filter == t for t in tags) or (tag_filter == doc_type)

        if matches_query and matches_tag:
            refined_items.append(item)
    return refined_items


def lambda_handler(event, context):
    """
    Multi-tenant document search:
    - mode=keyword: search DynamoDB items across fileName, summary, preview, tags
    - mode=semantic: embed query with Titan V2, compare against user's embeddings in S3,
      aggregate best chunk per document, filter with SIMILARITY_THRESHOLD, top 5 docs.
      Falls back to keyword if no embeddings exist.
    """
    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {})
        user_id = jwt_claims.get("sub")

        if not user_id:
            user_id = authorizer.get("claims", {}).get("sub") or event.get("headers", {}).get("x-user-id")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        params = event.get("queryStringParameters") or {}
        search_query = params.get("q", "").strip()
        tag_filter = params.get("tag", "").strip().lower()
        type_filter = params.get("type", "").strip().lower()
        mode = params.get("mode", "keyword").strip().lower()

        if len(search_query) > MAX_QUERY_LENGTH:
            return build_response(400, {
                "error": f"Search query exceeds maximum length of {MAX_QUERY_LENGTH} characters."
            })

        # Fetch all documents belonging to user to build lookup map & support keyword search
        table = dynamodb.Table(DOCUMENTS_TABLE)
        db_resp = table.query(
            KeyConditionExpression=Key("userId").eq(user_id),
            Limit=100
        )
        all_user_docs = [
            i for i in db_resp.get("Items", [])
            if not i.get("docId", "").startswith("USAGE#")
        ]
        doc_map = {d["docId"]: d for d in all_user_docs}

        # Apply type filter if requested
        if type_filter and type_filter != "all":
            all_user_docs = [d for d in all_user_docs if d.get("docType", "").lower() == type_filter]

        # 1. Semantic Search Mode
        if mode == "semantic" and search_query:
            # Enforce daily quota
            allowed, count = check_and_increment_daily_search_limit(user_id)
            if not allowed:
                return build_response(429, {
                    "error": f"Daily semantic search limit of {DAILY_SEARCH_LIMIT} requests reached. Resets at midnight UTC."
                })

            user_chunks = retrieve_user_chunks_for_search(user_id, doc_map)

            # Fallback to keyword if no embeddings found
            if not user_chunks:
                keyword_results = perform_keyword_search(all_user_docs, search_query.lower(), tag_filter)
                return build_response(200, {
                    "results": keyword_results,
                    "count": len(keyword_results),
                    "query": search_query,
                    "mode": "keyword",
                    "fallback": True,
                    "fallbackReason": "No document embeddings available yet. Showing keyword search results instead."
                })

            query_vec = embed_search_query(search_query)

            # Score each chunk
            doc_scores = {}
            for chunk in user_chunks:
                doc_id = chunk["docId"]
                # Skip if filtered by type
                if type_filter and type_filter != "all":
                    if doc_map.get(doc_id, {}).get("docType", "").lower() != type_filter:
                        continue

                sim = cosine_similarity(query_vec, chunk.get("vector", []))
                if doc_id not in doc_scores or sim > doc_scores[doc_id]["similarity"]:
                    doc_scores[doc_id] = {
                        "similarity": sim,
                        "bestSnippet": chunk.get("text", "")[:240],
                        "chunkIndex": chunk.get("chunkIndex", 0),
                        "docId": doc_id,
                    }

            # Filter by threshold & sort top 5
            filtered_scored = [
                entry for entry in doc_scores.values()
                if entry["similarity"] >= SIMILARITY_THRESHOLD
            ]
            filtered_scored.sort(key=lambda x: x["similarity"], reverse=True)
            top_scored = filtered_scored[:5]

            semantic_results = []
            for item in top_scored:
                doc_item = dict(doc_map.get(item["docId"], {}))
                doc_item["similarityScore"] = round(item["similarity"], 4)
                doc_item["matchPercentage"] = int(round(item["similarity"] * 100))
                doc_item["matchingSnippet"] = item["bestSnippet"]
                semantic_results.append(doc_item)

            return build_response(200, {
                "results": semantic_results,
                "count": len(semantic_results),
                "query": search_query,
                "mode": "semantic",
                "fallback": False,
                "threshold": SIMILARITY_THRESHOLD,
            })

        # 2. Keyword Search Mode (Default)
        keyword_results = perform_keyword_search(all_user_docs, search_query.lower(), tag_filter)
        return build_response(200, {
            "results": keyword_results,
            "count": len(keyword_results),
            "query": search_query,
            "tag": tag_filter,
            "type": type_filter,
            "mode": "keyword",
            "fallback": False,
        })

    except Exception as exc:
        print(f"Error executing document search: {str(exc)}")
        return build_response(500, {"error": "Internal server error executing document search"})
