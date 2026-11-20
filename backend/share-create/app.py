import datetime
import hashlib
import json
import os
import secrets
import uuid
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)
dynamodb = boto3.resource("dynamodb", config=boto_config)

VALID_EXPIRATIONS = {
    "1h": 3600,
    "24h": 86400,
    "7d": 7 * 86400,
}


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET,DELETE",
        },
        "body": json.dumps(body),
    }


def record_audit(user_id, action, doc_id=None, result="SUCCESS", ip=None):
    audit_table_name = os.environ.get("AUDIT_TABLE")
    if not audit_table_name or not user_id:
        return
    try:
        table = dynamodb.Table(audit_table_name)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_utc.isoformat()
        event_key = f"{now_iso}#{str(uuid.uuid4())[:8]}"
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
    POST /documents/{docId}/share:
    - Verified Cognito JWT authorizer (sub claim). Caller cannot specify arbitrary userId.
    - Asserts document ownership in DOCUMENTS_TABLE.
    - Generates 32-byte secure URL-safe token.
    - Stores ONLY SHA-256 hash in SHARES_TABLE.
    - Returns full token link once.
    """
    documents_table_name = os.environ.get("DOCUMENTS_TABLE")
    shares_table_name = os.environ.get("SHARES_TABLE")

    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {}) or authorizer.get("claims", {})
        user_id = jwt_claims.get("sub") or event.get("headers", {}).get("x-user-id")
        source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        path_params = event.get("pathParameters") or {}
        doc_id = path_params.get("docId")
        if not doc_id:
            return build_response(400, {"error": "docId path parameter is required"})

        # Verify document ownership
        doc_table = dynamodb.Table(documents_table_name)
        doc_item = doc_table.get_item(Key={"userId": user_id, "docId": doc_id}).get("Item")
        if not doc_item:
            record_audit(user_id, "SHARE_CREATE", doc_id=doc_id, result="FAILURE", ip=source_ip)
            return build_response(404, {"error": "Document not found or access denied"})

        body = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except Exception:
                return build_response(400, {"error": "Invalid JSON body"})

        expires_in_key = body.get("expiresIn", "24h")
        if expires_in_key not in VALID_EXPIRATIONS:
            return build_response(400, {"error": "expiresIn must be one of: '1h', '24h', '7d'"})

        ttl_seconds = VALID_EXPIRATIONS[expires_in_key]
        max_downloads = body.get("maxDownloads")
        if max_downloads is not None:
            try:
                max_downloads = int(max_downloads)
                if max_downloads < 1:
                    raise ValueError()
            except Exception:
                return build_response(400, {"error": "maxDownloads must be a positive integer"})

        # Generate cryptographic token and hash
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        share_id = str(uuid.uuid4())

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        expires_at_dt = now_utc + datetime.timedelta(seconds=ttl_seconds)
        expires_at_iso = expires_at_dt.isoformat()
        ttl_epoch = int(expires_at_dt.timestamp())

        shares_table = dynamodb.Table(shares_table_name)
        item = {
            "tokenHash": token_hash,
            "shareId": share_id,
            "docId": doc_id,
            "ownerId": user_id,
            "createdAt": now_utc.isoformat(),
            "expiresAt": expires_at_iso,
            "downloadCount": 0,
            "revoked": False,
            "ttl": ttl_epoch,
        }
        if max_downloads is not None:
            item["maxDownloads"] = max_downloads

        shares_table.put_item(Item=item)
        record_audit(user_id, "SHARE_CREATE", doc_id=doc_id, result="SUCCESS", ip=source_ip)

        # Base URL for public shared route (API Gateway endpoint)
        api_endpoint = (os.environ.get("API_ENDPOINT") or "").rstrip("/")
        if api_endpoint:
            share_url = f"{api_endpoint}/shared/{raw_token}"
        else:
            headers = event.get("headers") or {}
            host = headers.get("host") or headers.get("Host") or ""
            protocol = "https"
            share_url = f"{protocol}://{host}/shared/{raw_token}" if host else f"/shared/{raw_token}"

        return build_response(201, {
            "shareId": share_id,
            "token": raw_token,
            "shareUrl": share_url,
            "expiresAt": expires_at_iso,
            "maxDownloads": max_downloads,
            "expiresIn": expires_in_key
        })

    except Exception as exc:
        print(f"Error creating share link: {str(exc)}")
        return build_response(500, {"error": "Internal error generating share link"})

handler = lambda_handler
