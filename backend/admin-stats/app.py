import datetime
import json
import math
import os
import time
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
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
            "Access-Control-Allow-Methods": "OPTIONS,GET",
        },
        "body": json.dumps(body),
    }


def parse_cognito_groups(raw_groups) -> list[str]:
    """
    Parses cognito:groups claim delivered by API Gateway HTTP API v2 JWT authorizer.
    Can be:
      - Python list: ["Admin", "User"]
      - JSON string: '["Admin", "User"]'
      - Space-separated bracketed string: '[Admin User]' or '[Admin]'
      - Comma-separated bracketed string: '[Admin, User]'
      - Plain string: 'Admin'
    Always returns exact, clean group names without brackets or whitespace.
    """
    if not raw_groups:
        return []

    if isinstance(raw_groups, list):
        return [str(g).strip() for g in raw_groups if str(g).strip()]

    if isinstance(raw_groups, str):
        trimmed = raw_groups.strip()
        if not trimmed:
            return []

        # Attempt 1: Standard JSON array parse, e.g. '["Admin"]'
        if trimmed.startswith("[") and trimmed.endswith("]"):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, list):
                    return [str(g).strip() for g in parsed if str(g).strip()]
            except Exception:
                pass

            # Attempt 2: Bracketed format without JSON quotes: '[Admin User]' or '[Admin, User]'
            inner = trimmed[1:-1].strip()
            if "," in inner:
                parts = inner.split(",")
            else:
                parts = inner.split()
            return [p.strip() for p in parts if p.strip()]

        # Attempt 3: Comma-separated plain string, e.g. 'Admin,User'
        if "," in trimmed:
            return [p.strip() for p in trimmed.split(",") if p.strip()]

        return [trimmed]

    return []



def parse_iso(ts_str):
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        clean = ts_str.strip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(clean)
    except Exception:
        return None


def lambda_handler(event, context):
    """
    GET /admin/stats endpoint:
    - Enforces Admin role on SERVER by checking 'cognito:groups' claim in verified JWT.
    - Scans DynamoDB to compute aggregate analytics across all documents and users.
    - Excludes USAGE# records from document counts.
    - Returns AGGREGATES ONLY: never exposes raw text, summaries, or questions.
    """
    try:
        # 1. Server-side role enforcement
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt_claims = authorizer.get("jwt", {}).get("claims", {})
        if not jwt_claims:
            jwt_claims = authorizer.get("claims", {})

        raw_groups = jwt_claims.get("cognito:groups", [])
        groups = parse_cognito_groups(raw_groups)

        # EXACT group name matching - never substring matching
        if "Admin" not in groups:
            return build_response(403, {"error": "Forbidden: Requires Admin privileges"})


        # 2. Paginated Scan over DynamoDB
        table = dynamodb.Table(DOCUMENTS_TABLE)
        paginator = table.meta.client.get_paginator("scan")

        total_documents = 0
        status_counts = {"UPLOADED": 0, "PROCESSING": 0, "PROCESSED": 0, "FAILED": 0}
        provider_counts = {"groq": 0, "nova": 0, "local": 0}
        total_storage_bytes = 0
        user_storage_map = {} # anon_user_id -> bytes
        user_ids = set()

        processing_durations_sec = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        seven_days_ago = now_utc - datetime.timedelta(days=7)
        fourteen_days_ago = now_utc - datetime.timedelta(days=14)

        failed_documents_last_7_days = 0
        ask_questions_per_day = {} # "YYYY-MM-DD" -> count

        # Pre-seed last 14 days in ask_questions_per_day
        for d in range(14):
            day_key = (now_utc - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
            ask_questions_per_day[day_key] = 0

        # Paginate scan
        for page in paginator.paginate(TableName=DOCUMENTS_TABLE):
            for item in page.get("Items", []):
                # An item from client dynamodb scan has types like {'S': '...'}, convert if raw
                def extract_field(val):
                    if isinstance(val, dict):
                        for k in ("S", "N", "BOOL"):
                            if k in val:
                                return val[k]
                    return val

                user_id = extract_field(item.get("userId"))
                doc_id = extract_field(item.get("docId"))

                if not user_id or not doc_id:
                    continue

                # Handle USAGE# records
                if str(doc_id).startswith("USAGE#"):
                    record_date = extract_field(item.get("date"))
                    if not record_date:
                        record_date = str(doc_id).replace("USAGE#", "")
                    
                    q_count_val = extract_field(item.get("questionCount"))
                    try:
                        q_count = int(q_count_val) if q_count_val is not None else 0
                    except (ValueError, TypeError):
                        q_count = 0

                    if record_date in ask_questions_per_day:
                        ask_questions_per_day[record_date] += q_count
                    continue

                # Otherwise, it's a document record
                total_documents += 1
                user_ids.add(user_id)

                # Anonymize user ID for per-user breakdown
                anon_user = f"user-{user_id[-6:]}" if len(user_id) > 6 else user_id

                # File size & storage
                fsize_val = extract_field(item.get("fileSize"))
                try:
                    fsize = int(fsize_val) if fsize_val is not None else 0
                except (ValueError, TypeError):
                    fsize = 0
                total_storage_bytes += fsize
                user_storage_map[anon_user] = user_storage_map.get(anon_user, 0) + fsize

                # Status
                st = extract_field(item.get("status")) or "UPLOADED"
                if st in status_counts:
                    status_counts[st] += 1
                else:
                    status_counts[st] = status_counts.get(st, 0) + 1

                # Provider
                prov = extract_field(item.get("summaryProvider"))
                if prov:
                    prov = str(prov).lower()
                    provider_counts[prov] = provider_counts.get(prov, 0) + 1

                # Created / Uploaded timestamp
                created_str = extract_field(item.get("uploadedAt")) or extract_field(item.get("createdAt"))
                processed_str = extract_field(item.get("processedAt"))

                dt_created = parse_iso(created_str)
                dt_processed = parse_iso(processed_str)

                # Processing time duration
                if dt_created and dt_processed and dt_processed >= dt_created:
                    duration = (dt_processed - dt_created).total_seconds()
                    processing_durations_sec.append(duration)

                # Failures in last 7 days
                if st == "FAILED":
                    if dt_created and dt_created >= seven_days_ago:
                        failed_documents_last_7_days += 1
                    elif not dt_created:
                        failed_documents_last_7_days += 1

        # 3. Calculate metrics
        avg_processing_time = (
            round(sum(processing_durations_sec) / len(processing_durations_sec), 2)
            if processing_durations_sec
            else 0.0
        )

        p95_processing_time = 0.0
        if processing_durations_sec:
            sorted_durations = sorted(processing_durations_sec)
            idx_95 = min(int(math.ceil(0.95 * len(sorted_durations))) - 1, len(sorted_durations) - 1)
            p95_processing_time = round(sorted_durations[max(0, idx_95)], 2)

        success_count = status_counts.get("PROCESSED", 0)
        failure_count = status_counts.get("FAILED", 0)
        processed_total = success_count + failure_count
        success_rate = round((success_count / processed_total) * 100, 1) if processed_total > 0 else 100.0
        failure_rate = round((failure_count / processed_total) * 100, 1) if processed_total > 0 else 0.0

        # Sort per-user storage top-10
        sorted_user_storage = sorted(
            [{"user": u, "bytes": b} for u, b in user_storage_map.items()],
            key=lambda x: x["bytes"],
            reverse=True
        )[:10]

        # Format Ask questions timeline ordered ascending by date
        ask_timeline = [
            {"date": day, "count": ask_questions_per_day[day]}
            for day in sorted(ask_questions_per_day.keys())
        ]

        # Scan recent security audit events (anonymized ids and action counts only)
        security_event_counts = {}
        recent_security_events = []
        if AUDIT_TABLE:
            try:
                audit_table = dynamodb.Table(AUDIT_TABLE)
                audit_paginator = audit_table.meta.client.get_paginator("scan")
                for a_page in audit_paginator.paginate(TableName=AUDIT_TABLE, Limit=100):
                    for a_item in a_page.get("Items", []):
                        a_action = extract_field(a_item.get("action")) or "UNKNOWN"
                        a_res = extract_field(a_item.get("result")) or "SUCCESS"
                        a_ts = extract_field(a_item.get("timestamp"))
                        a_uid = extract_field(a_item.get("userId")) or "anon"
                        anon_uid = f"user-{a_uid[-6:]}" if len(a_uid) > 6 else a_uid

                        security_event_counts[a_action] = security_event_counts.get(a_action, 0) + 1
                        recent_security_events.append({
                            "timestamp": a_ts,
                            "action": a_action,
                            "result": a_res,
                            "user": anon_uid
                        })
                    if len(recent_security_events) >= 50:
                        break
            except Exception as e:
                print(f"Warning: Audit scan error in admin stats: {e}")

        # Sort recent security events newest first
        recent_security_events.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        recent_security_events = recent_security_events[:20]

        # Record ADMIN_STATS_VIEW audit event
        if AUDIT_TABLE:
            try:
                audit_table = dynamodb.Table(AUDIT_TABLE)
                admin_uid = jwt_claims.get("sub", "admin")
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_iso = now_utc.isoformat()
                source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
                import hashlib
                ip_hash = hashlib.sha256((source_ip or "anon").encode("utf-8")).hexdigest()[:16]
                audit_table.put_item(
                    Item={
                        "userId": admin_uid,
                        "eventKey": f"{now_iso}#{os.urandom(4).hex()}",
                        "timestamp": now_iso,
                        "action": "ADMIN_STATS_VIEW",
                        "result": "SUCCESS",
                        "ipHash": ip_hash,
                        "ttl": int(now_utc.timestamp()) + (90 * 86400)
                    }
                )
            except Exception as e:
                print(f"Warning: Failed to log admin view: {e}")

        result = {
            "activeUsers": len(user_ids),
            "totalUsers": len(user_ids), # Retained for backwards compatibility
            "totalDocuments": total_documents,
            "documentsByStatus": status_counts,
            "storage": {
                "totalBytes": total_storage_bytes,
                "byUser": sorted_user_storage,
            },
            "performance": {
                "avgProcessingTimeSec": avg_processing_time,
                "p95ProcessingTimeSec": p95_processing_time,
                "measuredCount": len(processing_durations_sec),
            },
            "reliability": {
                "successRate": success_rate,
                "failureRate": failure_rate,
                "failedDocumentsLast7Days": failed_documents_last_7_days,
            },
            "summaryProviderSplit": provider_counts,
            "askUsageLast14Days": ask_timeline,
            "security": {
                "eventCounts": security_event_counts,
                "recentEvents": recent_security_events,
            }
        }

        return build_response(200, result)

    except Exception as exc:
        print(f"Error compiling admin stats: {str(exc)}")
        return build_response(500, {"error": "Internal error compiling admin statistics"})

handler = lambda_handler
