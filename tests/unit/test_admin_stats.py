import json
import pytest
from unittest.mock import MagicMock, patch
import importlib.util
import os
import sys

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

admin_mod = load_module("admin_stats_app", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend/admin-stats/app.py')))
lambda_handler = admin_mod.lambda_handler
parse_cognito_groups = admin_mod.parse_cognito_groups


# -----------------------------------------------------------------------------
# 1. Group Claim Parsing Tests
# -----------------------------------------------------------------------------

def test_parse_cognito_groups_formats():
    # Real list
    assert parse_cognito_groups(["Admin", "User"]) == ["Admin", "User"]
    assert parse_cognito_groups(["Admin"]) == ["Admin"]

    # Bracketed string with quotes: '["Admin"]'
    assert parse_cognito_groups('["Admin"]') == ["Admin"]
    assert parse_cognito_groups('["Admin", "User"]') == ["Admin", "User"]

    # Space-separated bracketed string: '[Admin User]' or '[Admin]'
    assert parse_cognito_groups("[Admin]") == ["Admin"]
    assert parse_cognito_groups("[Admin User]") == ["Admin", "User"]

    # Comma-separated bracketed string: '[Admin, User]'
    assert parse_cognito_groups("[Admin, User]") == ["Admin", "User"]

    # Plain string
    assert parse_cognito_groups("Admin") == ["Admin"]
    assert parse_cognito_groups("Admin,User") == ["Admin", "User"]

    # Negative / non-admin exact matches
    assert parse_cognito_groups("SuperAdmin") == ["SuperAdmin"]
    assert "Admin" not in parse_cognito_groups("SuperAdmin")
    assert "Admin" not in parse_cognito_groups("NotAdmin")
    assert "Admin" not in parse_cognito_groups("[SuperAdmin]")
    assert "Admin" not in parse_cognito_groups("[NotAdmin User]")

    # Empty and missing
    assert parse_cognito_groups("") == []
    assert parse_cognito_groups("   ") == []
    assert parse_cognito_groups(None) == []
    assert parse_cognito_groups([]) == []


@pytest.mark.parametrize("group_claim,expected_status", [
    (["Admin"], 200),
    ("[Admin]", 200),
    ("[Admin User]", 200),
    ('["Admin"]', 200),
    ("SuperAdmin", 403),
    ("NotAdmin", 403),
    ("[SuperAdmin]", 403),
    ("", 403),
    ([], 403),
    (None, 403),
])
@patch.object(admin_mod.dynamodb, "Table")
def test_admin_stats_group_authorization_matrix(mock_table, group_claim, expected_status):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance
    mock_client = MagicMock()
    mock_table_instance.meta.client = mock_client
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Items": []}]

    claims = {"sub": "user-test"}
    if group_claim is not None:
        claims["cognito:groups"] = group_claim

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": claims
                }
            }
        }
    }
    res = lambda_handler(event, None)
    assert res["statusCode"] == expected_status


# -----------------------------------------------------------------------------
# 2. Old Documents & Latency Math Tests
# -----------------------------------------------------------------------------

@patch.object(admin_mod.dynamodb, "Table")
def test_admin_stats_handles_old_records_missing_timestamps(mock_table):
    """
    Documents without uploadedAt or processedAt must be skipped in latency math
    without raising exceptions or causing division by zero.
    """
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance
    mock_client = MagicMock()
    mock_table_instance.meta.client = mock_client
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator

    # Items with missing or malformed timestamps
    mock_paginator.paginate.return_value = [
        {
            "Items": [
                # 1. Old record with NO timestamps at all
                {
                    "userId": "user-old-1",
                    "docId": "doc-legacy-1",
                    "status": "PROCESSED",
                    "fileSize": 500,
                },
                # 2. Old record with uploadedAt but no processedAt
                {
                    "userId": "user-old-2",
                    "docId": "doc-legacy-2",
                    "status": "PROCESSING",
                    "uploadedAt": "2026-11-03T08:00:00Z",
                    "fileSize": 1000,
                },
                # 3. Old record with invalid non-ISO string
                {
                    "userId": "user-old-3",
                    "docId": "doc-legacy-3",
                    "status": "PROCESSED",
                    "uploadedAt": "invalid-timestamp",
                    "processedAt": "invalid-timestamp",
                    "fileSize": 1500,
                },
                # 4. Valid modern record with both timestamps
                {
                    "userId": "user-modern-4",
                    "docId": "doc-modern-4",
                    "status": "PROCESSED",
                    "uploadedAt": "2026-11-03T10:00:00Z",
                    "processedAt": "2026-11-03T10:00:04Z",
                    "fileSize": 2000,
                }
            ]
        }
    ]

    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "admin-1", "cognito:groups": ["Admin"]}
                }
            }
        }
    }

    res = lambda_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])

    # Document counts must tally all 4 documents
    assert body["totalDocuments"] == 4
    assert body["activeUsers"] == 4
    assert body["storage"]["totalBytes"] == 5000

    # Latency math must only measure the single valid document (4s duration)
    assert body["performance"]["measuredCount"] == 1
    assert body["performance"]["avgProcessingTimeSec"] == 4.0
    assert body["performance"]["p95ProcessingTimeSec"] == 4.0
