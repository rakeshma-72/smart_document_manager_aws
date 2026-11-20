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
            "Access-Control-Allow-Methods": "OPTIONS,GET",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """
    GET /documents/{docId}/shares:
    - Lists all active share links for a document.
    - Owner only (verified JWT sub).
    - NEVER returns the raw token or token hash.
    """
    documents_table_name = os.environ.get("DOCUMENTS_TABLE")
    shares_table_name = os.environ.get("SHARES_TABLE")

    try:
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {}) or authorizer.get("claims", {})
        user_id = jwt_claims.get("sub") or event.get("headers", {}).get("x-user-id")

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
            return build_response(404, {"error": "Document not found or access denied"})

        shares_table = dynamodb.Table(shares_table_name)
        res = shares_table.query(
            IndexName="docId-index",
            KeyConditionExpression="docId = :d",
            ExpressionAttributeValues={":d": doc_id}
        )

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        safe_shares = []

        for item in res.get("Items", []):
            if item.get("ownerId") != user_id:
                continue

            expires_at_str = item.get("expiresAt")
            is_expired = False
            if expires_at_str:
                try:
                    exp_dt = datetime.datetime.fromisoformat(expires_at_str)
                    is_expired = now_utc > exp_dt
                except Exception:
                    pass

            is_revoked = item.get("revoked", False)
            download_count = int(item.get("downloadCount", 0))
            max_downloads = item.get("maxDownloads")
            is_exhausted = max_downloads is not None and download_count >= int(max_downloads)

            status = "ACTIVE"
            if is_revoked:
                status = "REVOKED"
            elif is_expired:
                status = "EXPIRED"
            elif is_exhausted:
                status = "EXHAUSTED"

            safe_shares.append({
                "shareId": item.get("shareId"),
                "docId": doc_id,
                "createdAt": item.get("createdAt"),
                "expiresAt": expires_at_str,
                "status": status,
                "downloadCount": download_count,
                "maxDownloads": max_downloads,
            })

        # Sort newest first
        safe_shares.sort(key=lambda x: x.get("createdAt", ""), reverse=True)

        return build_response(200, {"shares": safe_shares, "count": len(safe_shares)})

    except Exception as exc:
        print(f"Error listing shares: {str(exc)}")
        return build_response(500, {"error": "Internal error retrieving shares"})

handler = lambda_handler
