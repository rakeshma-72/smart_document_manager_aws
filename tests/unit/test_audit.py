"""Unit tests for Phase 4: Audit logging system and API."""

import os
import json
import time
import importlib.util
from unittest.mock import patch, MagicMock
import pytest

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("DOCUMENTS_TABLE", "test-documents")
    monkeypatch.setenv("AUDIT_TABLE", "test-audit")

def load_module(module_name, relative_path):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

audit_list_module = load_module("audit_list_module", "../../backend/audit-list/app.py")


def test_audit_log_event_writes_sanitized_record_with_hash():
    """Verify record_audit_event writes truncated IP hash and zero secret/raw text."""
    import backend.common.audit as audit_module
    from backend.common.audit import record_audit_event, hash_ip

    mock_table = MagicMock()
    ip = "198.51.100.42"
    expected_ip_hash = hash_ip(ip)
    assert len(expected_ip_hash) == 16  # 16-character truncated hex

    with patch.dict(os.environ, {"AUDIT_TABLE": "test-audit"}), \
         patch.object(audit_module.dynamodb, "Table", return_value=mock_table):
        record_audit_event(
            user_id="user-xyz",
            action="SHARE_CREATE",
            doc_id="doc-abc",
            result="SUCCESS",
            ip_address=ip,
            extra={"expiresIn": "24h", "question": "SECRET QUESTION SHOULD BE FILTERED"}
        )

        assert mock_table.put_item.called
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["userId"] == "user-xyz"
        assert item["action"] == "SHARE_CREATE"
        assert item["result"] == "SUCCESS"
        assert item["ipHash"] == expected_ip_hash
        assert item["docId"] == "doc-abc"
        assert item["expiresIn"] == "24h"
        assert "question" not in item  # Verify filtered out
        assert "ttl" in item
        assert item["ttl"] > int(time.time()) + 80 * 86400


def test_audit_logging_is_best_effort():
    """Verify audit failure never raises exception or disrupts main application."""
    import backend.common.audit as audit_module
    from backend.common.audit import record_audit_event

    with patch.dict(os.environ, {"AUDIT_TABLE": "test-audit"}), \
         patch.object(audit_module.dynamodb, "Table", side_effect=Exception("DynamoDB unreachable")):
        # Should not raise exception
        record_audit_event(
            user_id="user-xyz",
            action="UPLOAD",
            result="SUCCESS",
            ip_address="127.0.0.1"
        )


def test_audit_list_returns_caller_events_only():
    """Verify GET /audit returns caller's own events, newest first."""
    mock_audit_table = MagicMock()

    mock_audit_table.query.return_value = {
        "Items": [
            {
                "userId": "alice",
                "eventKey": "2026-11-03T11:00:00.000Z#ev2",
                "eventId": "ev2",
                "action": "ASK",
                "result": "SUCCESS",
                "timestamp": "2026-11-03T11:00:00.000Z"
            },
            {
                "userId": "alice",
                "eventKey": "2026-11-03T10:00:00.000Z#ev1",
                "eventId": "ev1",
                "action": "UPLOAD",
                "result": "SUCCESS",
                "timestamp": "2026-11-03T10:00:00.000Z"
            }
        ]
    }

    with patch.object(audit_list_module.dynamodb, "Table", return_value=mock_audit_table):
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "alice"
                        }
                    }
                }
            },
            "queryStringParameters": {
                "limit": "10"
            }
        }

        resp = audit_list_module.lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        events = body["events"]

        assert len(events) == 2
        assert events[0]["eventKey"] == "2026-11-03T11:00:00.000Z#ev2"
        assert events[1]["eventKey"] == "2026-11-03T10:00:00.000Z#ev1"
        assert events[0]["action"] == "ASK"
        assert events[1]["action"] == "UPLOAD"
        # Check query call
        query_call = mock_audit_table.query.call_args
        assert query_call.kwargs["ScanIndexForward"] is False  # Newest first
