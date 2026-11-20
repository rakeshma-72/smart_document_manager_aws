import json
import os
import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"}
)

dynamodb = boto3.resource("dynamodb", config=boto_config)
DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
AUDIT_TABLE = os.environ.get("AUDIT_TABLE")

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

def lambda_handler(event, context):
    """
    Retrieves the document library for the authenticated user,
    sorted with most recently uploaded documents first.
    """
    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {})
        user_id = jwt_claims.get("sub")

        if not user_id:
            user_id = authorizer.get("claims", {}).get("sub") or event.get("headers", {}).get("x-user-id")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        table = dynamodb.Table(DOCUMENTS_TABLE)

        # Query GSI for user's documents sorted by createdAt descending
        response = table.query(
            IndexName="userId-createdAt-index",
            KeyConditionExpression=Key("userId").eq(user_id),
            ScanIndexForward=False, # Newest first
            Limit=50
        )

        items = [item for item in response.get("Items", []) if not item.get("docId", "").startswith("USAGE#")]

        # Record best-effort VIEW audit event
        if AUDIT_TABLE:
            try:
                audit_table = dynamodb.Table(AUDIT_TABLE)
                import time, datetime, hashlib
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_iso = now_utc.isoformat()
                source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
                ip_hash = hashlib.sha256((source_ip or "anon").encode("utf-8")).hexdigest()[:16]
                audit_table.put_item(
                    Item={
                        "userId": user_id,
                        "eventKey": f"{now_iso}#{os.urandom(4).hex()}",
                        "timestamp": now_iso,
                        "action": "VIEW",
                        "result": "SUCCESS",
                        "ipHash": ip_hash,
                        "ttl": int(now_utc.timestamp()) + (90 * 86400)
                    }
                )
            except Exception as e:
                print(f"Warning: Audit log error: {e}")

        return build_response(200, {"documents": items, "count": len(items)})

    except Exception as exc:
        print(f"Error querying documents: {str(exc)}")
        return build_response(500, {"error": "Internal server error listing documents"})
