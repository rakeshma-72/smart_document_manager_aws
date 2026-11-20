import datetime
import hashlib
import json
import os
import boto3
from botocore.config import Config

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


def generic_not_found():
    """Returns identical 404 response for ANY failure to prevent token probing."""
    return {
        "statusCode": 404,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": "Resource not found or link has expired"}),
    }


def record_audit(user_id, action, doc_id=None, result="SUCCESS", ip=None):
    audit_table_name = os.environ.get("AUDIT_TABLE")
    if not audit_table_name or not user_id:
        return
    try:
        table = dynamodb.Table(audit_table_name)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_utc.isoformat()
        event_key = f"{now_iso}#{os.urandom(4).hex()}"
        ip_hash = hashlib.sha256((ip or "anon").encode("utf-8")).hexdigest()[:16]
        item = {
            "userId": user_id,
            "eventKey": event_key,
            "timestamp": now_iso,
            "action": action,
            "result": result,
            "ipHash": ip_hash,
            "ttl": int(now_utc.timestamp()) + (90 * 86400),
        }
        if doc_id:
            item["docId"] = doc_id
        table.put_item(Item=item)
    except Exception as e:
        print(f"Warning: Audit log error: {e}")


def lambda_handler(event, context):
    """
    GET /shared/{token} - PUBLIC ROUTE (No Cognito Authorizer)
    - Hashes token using SHA-256.
    - NEVER logs the raw token.
    - Validates expiry, revocation, and download count.
    - Atomically increments downloadCount.
    - Resolves document S3 key and returns 302 redirect with 60-second pre-signed GET URL.
    - For ANY failure: returns generic 404.
    """
    documents_table_name = os.environ.get("DOCUMENTS_TABLE")
    documents_bucket_name = os.environ.get("DOCUMENTS_BUCKET")
    shares_table_name = os.environ.get("SHARES_TABLE")

    path_params = event.get("pathParameters") or {}
    raw_token = path_params.get("token")
    source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")

    if not raw_token:
        return generic_not_found()

    try:
        # Compute SHA-256 hash
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        shares_table = dynamodb.Table(shares_table_name)
        share_res = shares_table.get_item(Key={"tokenHash": token_hash})
        share_item = share_res.get("Item")

        if not share_item:
            record_audit("anonymous", "SHARE_ACCESS", result="NOT_FOUND", ip=source_ip)
            return generic_not_found()

        owner_id = share_item.get("ownerId")
        doc_id = share_item.get("docId")

        # Check revocation
        if share_item.get("revoked", False):
            record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="REVOKED", ip=source_ip)
            return generic_not_found()

        # Check expiration
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        expires_at_str = share_item.get("expiresAt")
        if expires_at_str:
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if now_utc > expires_at:
                record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="EXPIRED", ip=source_ip)
                return generic_not_found()

        # Check maxDownloads
        max_downloads = share_item.get("maxDownloads")
        download_count = int(share_item.get("downloadCount", 0))
        if max_downloads is not None and download_count >= int(max_downloads):
            record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="EXHAUSTED", ip=source_ip)
            return generic_not_found()

        # Atomically increment downloadCount with conditional check
        try:
            update_expr = "ADD downloadCount :inc"
            expr_vals = {":inc": 1}
            cond_expr = "attribute_exists(tokenHash) AND revoked = :f"
            expr_vals[":f"] = False

            if max_downloads is not None:
                cond_expr += " AND downloadCount < :maxD"
                expr_vals[":maxD"] = int(max_downloads)

            shares_table.update_item(
                Key={"tokenHash": token_hash},
                UpdateExpression=update_expr,
                ConditionExpression=cond_expr,
                ExpressionAttributeValues=expr_vals
            )
        except Exception as cond_err:
            print(f"Conditional update failed: {cond_err}")
            record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="EXHAUSTED", ip=source_ip)
            return generic_not_found()

        # Lookup document in DOCUMENTS_TABLE
        doc_table = dynamodb.Table(documents_table_name)
        doc_res = doc_table.get_item(Key={"userId": owner_id, "docId": doc_id})
        doc_item = doc_res.get("Item")
        if not doc_item or not doc_item.get("s3Key"):
            record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="NOT_FOUND", ip=source_ip)
            return generic_not_found()

        s3_key = doc_item["s3Key"]
        file_name = doc_item.get("fileName", "downloaded_document")

        # Generate 60-second regional pre-signed GET URL with attachment header
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": documents_bucket_name,
                "Key": s3_key,
                "ResponseContentDisposition": f'attachment; filename="{file_name}"'
            },
            ExpiresIn=60
        )

        record_audit(owner_id, "SHARE_ACCESS", doc_id=doc_id, result="SUCCESS", ip=source_ip)

        # 302 Redirect to pre-signed URL
        return {
            "statusCode": 302,
            "headers": {
                "Location": presigned_url,
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Access-Control-Allow-Origin": "*"
            },
            "body": ""
        }

    except Exception as exc:
        print(f"Error resolving share token: {str(exc)}")
        return generic_not_found()

handler = lambda_handler
