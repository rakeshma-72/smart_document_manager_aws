import json
import os
import importlib.util
from unittest.mock import MagicMock, patch

def load_handler(relative_path, module_name):
    full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

list_mod = load_handler("../../backend/list-docs/app.py", "iso_list_mod")
search_mod = load_handler("../../backend/search/app.py", "iso_search_mod")
delete_mod = load_handler("../../backend/delete-doc/app.py", "iso_delete_mod")
upload_mod = load_handler("../../backend/upload-url/app.py", "iso_upload_mod")

def test_multi_tenant_user_isolation():
    """
    User Isolation Security Test:
    Proves User A cannot access, view, search, or delete User B's documents.
    """
    user_a = "user-alice-111"
    user_b = "user-bob-222"

    database_store = {
        (user_a, "doc-a-01"): {
            "userId": user_a,
            "docId": "doc-a-01",
            "fileName": "alice_secret_roadmap.pdf",
            "summary": "Confidential roadmap for Alice projects.",
            "tags": ["roadmap", "confidential"],
            "status": "PROCESSED",
            "s3Key": f"uploads/{user_a}/doc-a-01/alice_secret_roadmap.pdf"
        },
        (user_b, "doc-b-99"): {
            "userId": user_b,
            "docId": "doc-b-99",
            "fileName": "bob_financial_payroll.pdf",
            "summary": "Confidential payroll and executive salaries for Bob.",
            "tags": ["payroll", "executive", "salaries"],
            "status": "PROCESSED",
            "s3Key": f"uploads/{user_b}/doc-b-99/bob_financial_payroll.pdf"
        }
    }

    class MockIsolatedTable:
        def query(self, KeyConditionExpression, **kwargs):
            # Inspect key condition extracted value
            items = []
            for (uid, did), item in database_store.items():
                # In DynamoDB, KeyConditionExpression enforces equality on partition key (userId)
                if hasattr(KeyConditionExpression, "get_expression"):
                    # Mock evaluation of Key('userId').eq(user_id)
                    pass
                # Strict tenant partition match
                pass
            return {"Items": items}

        def get_item(self, Key):
            # Strict multi-attribute key lookup: (userId, docId)
            k = (Key["userId"], Key["docId"])
            if k in database_store:
                return {"Item": database_store[k]}
            return {}

        def delete_item(self, Key):
            k = (Key["userId"], Key["docId"])
            database_store.pop(k, None)

    mock_table = MockIsolatedTable()

    # -------------------------------------------------------------------------
    # 1. Isolation Proof: User A listing documents never returns User B's files
    # -------------------------------------------------------------------------
    def mock_query_for_list(IndexName, KeyConditionExpression, **kwargs):
        # Emulate DynamoDB GSI Key('userId').eq(caller_id)
        # Extract target userId from query condition
        caller_id = KeyConditionExpression._values[1]
        items = [v for (uid, _), v in database_store.items() if uid == caller_id]
        return {"Items": items}

    with patch.object(list_mod.dynamodb, "Table") as mock_tbl_ref:
        mock_instance = MagicMock()
        mock_instance.query.side_effect = mock_query_for_list
        mock_tbl_ref.return_value = mock_instance

        event_alice = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_a}}}
            }
        }
        res_alice = list_mod.lambda_handler(event_alice, None)
        assert res_alice["statusCode"] == 200
        alice_docs = json.loads(res_alice["body"])["documents"]

        # User A must only see their own document
        assert len(alice_docs) == 1
        assert alice_docs[0]["docId"] == "doc-a-01"
        assert not any(d["docId"] == "doc-b-99" for d in alice_docs)

    # -------------------------------------------------------------------------
    # 2. Isolation Proof: User A searching for Bob's exact keywords finds 0 items
    # -------------------------------------------------------------------------
    def mock_query_for_search(KeyConditionExpression, **kwargs):
        caller_id = KeyConditionExpression._values[1]
        items = [v for (uid, _), v in database_store.items() if uid == caller_id]
        return {"Items": items}

    with patch.object(search_mod.dynamodb, "Table") as mock_tbl_ref:
        mock_instance = MagicMock()
        mock_instance.query.side_effect = mock_query_for_search
        mock_tbl_ref.return_value = mock_instance

        # Alice searches for "payroll" (which exists exclusively in Bob's document)
        event_search_bob_term = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_a}}}
            },
            "queryStringParameters": {"q": "payroll"}
        }
        res_search = search_mod.lambda_handler(event_search_bob_term, None)
        assert res_search["statusCode"] == 200
        search_results = json.loads(res_search["body"])["results"]

        # Alice receives 0 results because Bob's partition is isolated
        assert len(search_results) == 0

    # -------------------------------------------------------------------------
    # 3. Isolation Proof: User A attempting to delete User B's file is denied (404)
    # -------------------------------------------------------------------------
    with patch.object(delete_mod.dynamodb, "Table", return_value=mock_table), \
         patch.object(delete_mod.s3_client, "delete_object") as mock_s3_del:

        # Alice attempts to delete doc-b-99
        event_alice_attack = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_a}}}
            },
            "pathParameters": {"docId": "doc-b-99"}
        }

        res_attack = delete_mod.lambda_handler(event_alice_attack, None)
        assert res_attack["statusCode"] == 404
        assert "not found" in json.loads(res_attack["body"])["error"].lower()

        # Bob's document remains intact in database
        assert (user_b, "doc-b-99") in database_store
        assert not mock_s3_del.called

    # -------------------------------------------------------------------------
    # 4. Storage Isolation: Pre-signed URLs are partitioned by caller sub
    # -------------------------------------------------------------------------
    with patch.object(upload_mod.dynamodb, "Table") as mock_tbl, \
         patch.object(upload_mod.s3_client, "generate_presigned_url", return_value="https://s3.amazonaws.com/put"):
        mock_tbl.return_value = MagicMock()

        event_upload_alice = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": user_a}}}
            },
            "body": json.dumps({"fileName": "contract.pdf", "contentType": "application/pdf"})
        }
        res_url = upload_mod.lambda_handler(event_upload_alice, None)
        body = json.loads(res_url["body"])
        assert body["s3Key"].startswith(f"uploads/{user_a}/")
        assert user_b not in body["s3Key"]
