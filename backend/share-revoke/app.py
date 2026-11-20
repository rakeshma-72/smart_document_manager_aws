import datetime
import hashlib
import json
import os
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)
dynamodb = boto3.resource("dynamodb", config=boto_config)


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,DELETE",
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
    DELETE /shares/{shareId}:
    - Revokes a share link.
    - Owner only (verified JWT sub).
    """
    shares_table_name = os.environ.get("SHARES_TABLE")

    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {}) or authorizer.get("claims", {})
        user_id = jwt_claims.get("sub") or event.get("headers", {}).get("x-user-id")
        source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        path_params = event.get("pathParameters") or {}
        share_id = path_params.get("shareId")
        if not share_id:
            return build_response(400, {"error": "shareId path parameter is required"})

        shares_table = dynamodb.Table(shares_table_name)

        # Query share by shareId-index
        query_res = shares_table.query(
            IndexName="shareId-index",
            KeyConditionExpression="shareId = :s",
            ExpressionAttributeValues={":s": share_id}
        )
        items = query_res.get("Items", [])
        if not items:
            return build_response(404, {"error": "Share link not found"})

        share_item = items[0]
        if share_item.get("ownerId") != user_id:
            return build_response(403, {"error": "Forbidden: You do not own this share link"})

        token_hash = share_item["tokenHash"]
        doc_id = share_item.get("docId")

        # Mark revoked = True
        shares_table.update_item(
            Key={"tokenHash": token_hash},
            UpdateExpression="SET revoked = :t, updatedAt = :now",
            ExpressionAttributeValues={
                ":t": True,
                ":now": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        )

        record_audit(user_id, "SHARE_REVOKE", doc_id=doc_id, result="SUCCESS", ip=source_ip)

        return build_response(200, {"message": "Share link revoked successfully", "shareId": share_id})

    except Exception as exc:
        print(f"Error revoking share: {str(exc)}")
        return build_response(500, {"error": "Internal error revoking share link"})

handler = lambda_handler
