import datetime
import hashlib
import os
import uuid
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 2, "mode": "standard"},
)
dynamodb = boto3.resource("dynamodb", config=boto_config)
AUDIT_TABLE = os.environ.get("AUDIT_TABLE")


def hash_ip(ip_address: str) -> str:
    if not ip_address:
        return "anon"
    return hashlib.sha256(ip_address.encode("utf-8")).hexdigest()[:16]


def record_audit_event(
    user_id: str,
    action: str,
    doc_id: str = None,
    result: str = "SUCCESS",
    ip_address: str = None,
    extra: dict = None
) -> None:
    """
    Best-effort audit logger:
    - Never throws; fails silently so main operations never break.
    - Partition Key: userId
    - Sort Key: timestamp#uuid
    - 90 days TTL
    - CRITICAL: Never logs document text, summaries, questions, raw tokens, or file contents.
    """
    if not AUDIT_TABLE or not user_id:
        return

    try:
        table = dynamodb.Table(AUDIT_TABLE)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_utc.isoformat()
        event_id = str(uuid.uuid4())[:8]
        event_key = f"{now_iso}#{event_id}"
        ttl_epoch = int(now_utc.timestamp()) + (90 * 86400) # 90 days retention

        item = {
            "userId": user_id,
            "eventKey": event_key,
            "timestamp": now_iso,
            "action": action, # UPLOAD, VIEW, DELETE, SHARE_CREATE, SHARE_REVOKE, SHARE_ACCESS, ASK, ADMIN_STATS_VIEW
            "result": result, # SUCCESS, FAILURE, NOT_FOUND
            "ipHash": hash_ip(ip_address),
            "ttl": ttl_epoch,
        }

        if doc_id:
            item["docId"] = doc_id

        if extra and isinstance(extra, dict):
            # Only allow non-sensitive scalar metadata
            for k, v in extra.items():
                if k not in ("text", "summary", "question", "token", "content", "file", "jwt") and isinstance(v, (str, int, float, bool)):
                    item[k] = v

        table.put_item(Item=item)
    except Exception as e:
        print(f"Warning: Audit log write failed (best-effort): {e}")
