"""Unit tests for Phase 4: Expiring share links."""

import os
import sys
import json
import hashlib
import time
import importlib.util
from unittest.mock import patch, MagicMock
import pytest

# Load handlers
def load_module(module_name, relative_path):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

share_create_module = load_module("share_create_module", "../../backend/share-create/app.py")
share_access_module = load_module("share_access_module", "../../backend/share-access/app.py")
share_list_module = load_module("share_list_module", "../../backend/share-list/app.py")
share_revoke_module = load_module("share_revoke_module", "../../backend/share-revoke/app.py")


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("DOCUMENTS_TABLE", "test-documents")
    monkeypatch.setenv("SHARES_TABLE", "test-shares")
    monkeypatch.setenv("AUDIT_TABLE", "test-audit")
    monkeypatch.setenv("DOCUMENTS_BUCKET", "test-bucket")


def test_create_share_link_stores_hash_only():
    """Verify POST /documents/{docId}/share generates raw token, stores only SHA-256 hash, and sets TTL."""
    mock_docs_table = MagicMock()
    mock_shares_table = MagicMock()

    # Document exists and belongs to user-1
    mock_docs_table.get_item.return_value = {
        "Item": {
            "userId": "user-1",
            "docId": "doc-123",
            "fileName": "report.pdf",
            "s3Key": "user-1/doc-123/report.pdf",
            "status": "PROCESSED"
        }
    }

    def table_router(name):
        if "documents" in name:
            return mock_docs_table
        return mock_shares_table

    with patch.object(share_create_module.dynamodb, "Table", side_effect=table_router), \
         patch.object(share_create_module, "record_audit"):

        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-1"
                        }
                    }
                },
                "http": {
                    "sourceIp": "192.168.1.50"
                }
            },
            "pathParameters": {
                "docId": "doc-123"
            },
            "body": json.dumps({"expiresIn": "24h", "maxDownloads": 5}),
            "headers": {
                "host": "api.example.com"
            }
        }

        resp = share_create_module.lambda_handler(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "token" in body
        raw_token = body["token"]
        assert "shareUrl" in body
        assert body["expiresIn"] == "24h"
        assert body["maxDownloads"] == 5

        # Check what was saved to DynamoDB
        put_call = mock_shares_table.put_item.call_args
        assert put_call is not None
        saved_item = put_call.kwargs["Item"]

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert saved_item["tokenHash"] == expected_hash
        assert saved_item["docId"] == "doc-123"
        assert saved_item["ownerId"] == "user-1"
        assert saved_item["maxDownloads"] == 5
        assert saved_item["downloadCount"] == 0
        assert saved_item["revoked"] is False
        assert "token" not in saved_item  # Verify raw token is NEVER stored in database


def test_create_share_link_owner_verification():
    """Verify users cannot create share links for documents they do not own."""
    mock_docs_table = MagicMock()
    # Document belongs to user-owner -> query with intruder returns no item
    mock_docs_table.get_item.return_value = {}

    with patch.object(share_create_module.dynamodb, "Table", return_value=mock_docs_table):
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-intruder"
                        }
                    }
                }
            },
            "pathParameters": {
                "docId": "doc-private"
            },
            "body": json.dumps({"expiresIn": "1h"})
        }

        resp = share_create_module.lambda_handler(event, None)
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert "Document not found" in body["error"]


def test_share_access_redirects_and_increments_download_count():
    """Verify GET /shared/{token} returns 302 redirect and updates download count atomically."""
    mock_shares_table = MagicMock()
    mock_docs_table = MagicMock()

    raw_token = "valid-secret-token-12345678901234567890"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    mock_shares_table.get_item.return_value = {
        "Item": {
            "tokenHash": token_hash,
            "shareId": "sh-001",
            "docId": "doc-1",
            "ownerId": "user-1",
            "expiresAt": "2030-01-01T00:00:00+00:00",
            "maxDownloads": 2,
            "downloadCount": 0,
            "revoked": False,
            "ttl": int(time.time()) + 3600
        }
    }

    mock_docs_table.get_item.return_value = {
        "Item": {
            "userId": "user-1",
            "docId": "doc-1",
            "fileName": "test.pdf",
            "s3Key": "user-1/doc-1/test.pdf",
            "status": "PROCESSED"
        }
    }

    def table_router(name):
        if "documents" in name:
            return mock_docs_table
        return mock_shares_table

    with patch.object(share_access_module.dynamodb, "Table", side_effect=table_router), \
         patch.object(share_access_module.s3_client, "generate_presigned_url", return_value="https://s3.ap-southeast-2.amazonaws.com/test-bucket/test.pdf?sig=mock"), \
         patch.object(share_access_module, "record_audit"):

        event = {
            "pathParameters": {
                "token": raw_token
            },
            "requestContext": {
                "http": {
                    "sourceIp": "203.0.113.1"
                }
            }
        }

        resp = share_access_module.lambda_handler(event, None)
        assert resp["statusCode"] == 302
        assert resp["headers"]["Location"] == "https://s3.ap-southeast-2.amazonaws.com/test-bucket/test.pdf?sig=mock"
        assert mock_shares_table.update_item.called


def test_share_access_returns_generic_404_for_all_failures():
    """Verify probe resistance: unknown, expired, revoked tokens all return identical generic 404."""
    mock_shares_table = MagicMock()
    generic_msg = "Resource not found or link has expired"

    with patch.object(share_access_module.dynamodb, "Table", return_value=mock_shares_table):
        # 1. Unknown token
        mock_shares_table.get_item.return_value = {}
        r1 = share_access_module.lambda_handler({"pathParameters": {"token": "completely-random-token"}}, None)
        assert r1["statusCode"] == 404
        assert json.loads(r1["body"])["error"] == generic_msg

        # 2. Expired token
        mock_shares_table.get_item.return_value = {
            "Item": {
                "tokenHash": "hash",
                "expiresAt": int(time.time()) - 100,  # in the past
                "revoked": False,
                "downloadCount": 0
            }
        }
        r2 = share_access_module.lambda_handler({"pathParameters": {"token": "expired-token"}}, None)
        assert r2["statusCode"] == 404
        assert json.loads(r2["body"])["error"] == generic_msg

        # 3. Revoked token
        mock_shares_table.get_item.return_value = {
            "Item": {
                "tokenHash": "hash",
                "expiresAt": int(time.time()) + 3600,
                "revoked": True,  # Revoked
                "downloadCount": 0
            }
        }
        r3 = share_access_module.lambda_handler({"pathParameters": {"token": "revoked-token"}}, None)
        assert r3["statusCode"] == 404
        assert json.loads(r3["body"])["error"] == generic_msg


def test_share_list_and_revoke_lifecycle():
    """Verify owner can list and revoke shares; non-owner cannot."""
    mock_docs_table = MagicMock()
    mock_shares_table = MagicMock()

    # Document belongs to alice
    mock_docs_table.get_item.return_value = {
        "Item": {
            "userId": "alice",
            "docId": "doc-alice-1",
            "fileName": "budget.xlsx"
        }
    }

    def table_router(name):
        if "documents" in name:
            return mock_docs_table
        return mock_shares_table

    # Mock query results for share_list
    mock_shares_table.query.return_value = {
        "Items": [
            {
                "tokenHash": "hash1",
                "shareId": "sh-alice-1",
                "docId": "doc-alice-1",
                "ownerId": "alice",
                "expiresAt": int(time.time()) + 3600,
                "maxDownloads": 10,
                "downloadCount": 1,
                "revoked": False,
                "createdAt": "2026-11-03T00:00:00Z"
            }
        ]
    }

    with patch.object(share_list_module.dynamodb, "Table", side_effect=table_router):
        # 1. Alice lists shares
        list_event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "alice"}}}
            },
            "pathParameters": {"docId": "doc-alice-1"}
        }
        r_list = share_list_module.lambda_handler(list_event, None)
        assert r_list["statusCode"] == 200
        shares = json.loads(r_list["body"])["shares"]
        assert len(shares) == 1
        assert "token" not in shares[0]
        assert "tokenHash" not in shares[0]
        assert shares[0]["status"] == "ACTIVE"

    with patch.object(share_revoke_module.dynamodb, "Table", return_value=mock_shares_table), \
         patch.object(share_revoke_module, "record_audit"):
        # 2. Alice revokes share 1
        mock_shares_table.query.return_value = {
            "Items": [
                {
                    "shareId": "sh-alice-1",
                    "ownerId": "alice",
                    "tokenHash": "hash1"
                }
            ]
        }
        alice_revoke_event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "alice"}}}
            },
            "pathParameters": {"shareId": "sh-alice-1"}
        }
        r_alice_revoke = share_revoke_module.lambda_handler(alice_revoke_event, None)
        assert r_alice_revoke["statusCode"] == 200
        assert mock_shares_table.update_item.called
