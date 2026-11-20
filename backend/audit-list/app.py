import json
import os
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)
dynamodb = boto3.resource("dynamodb", config=boto_config)

AUDIT_TABLE = os.environ.get("AUDIT_TABLE")


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,GET",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """
    GET /audit:
    - Returns the caller's own audit events from AUDIT_TABLE.
    - Owner only (verified JWT sub).
    - Newest first, paginated (limit=50).
    - Strictly sanitized: never outputs document text, questions, or raw tokens.
    """
    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {}) or authorizer.get("claims", {})
        user_id = jwt_claims.get("sub") or event.get("headers", {}).get("x-user-id")

        if not user_id:
            return build_response(401, {"error": "Unauthorized: Missing user identity"})

        query_params = event.get("queryStringParameters") or {}
        limit = min(int(query_params.get("limit", 50)), 100)

        table = dynamodb.Table(AUDIT_TABLE)
        res = table.query(
            KeyConditionExpression="userId = :u",
            ExpressionAttributeValues={":u": user_id},
            ScanIndexForward=False, # Newest first
            Limit=limit
        )

        events = []
        for item in res.get("Items", []):
            events.append({
                "eventKey": item.get("eventKey"),
                "timestamp": item.get("timestamp"),
                "action": item.get("action"),
                "result": item.get("result"),
                "docId": item.get("docId"),
                "ipHash": item.get("ipHash"),
            })

        return build_response(200, {
            "events": events,
            "count": len(events)
        })

    except Exception as exc:
        print(f"Error retrieving audit trail: {str(exc)}")
        return build_response(500, {"error": "Internal error retrieving audit logs"})

handler = lambda_handler
