import os
import pytest

# Ensure boto3 never attempts network or EC2 metadata calls during test runs
os.environ["AWS_ACCESS_KEY_ID"] = "testing-mock-access-key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing-mock-secret-key"
os.environ["AWS_SECURITY_TOKEN"] = "testing-mock-security-token"
os.environ["AWS_SESSION_TOKEN"] = "testing-mock-session-token"
os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-2"
os.environ["AWS_REGION"] = "ap-southeast-2"
os.environ["DOCUMENTS_TABLE"] = "smart-doc-mgr-dev-documents"
os.environ["DOCUMENTS_BUCKET"] = "smart-doc-mgr-dev-docs"

@pytest.fixture(autouse=True)
def speed_up_sleep(monkeypatch):
    """Bypasses real time.sleep in tests for instant execution."""
    monkeypatch.setattr("time.sleep", lambda seconds: None)
