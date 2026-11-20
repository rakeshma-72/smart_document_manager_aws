import io
import json
import os
import importlib.util
import pytest
from unittest.mock import MagicMock, patch

# Load module explicitly from backend/processor/app.py
HANDLER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../backend/processor/app.py")
)
spec = importlib.util.spec_from_file_location("processor_module", HANDLER_PATH)
processor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(processor_module)


@patch.object(processor_module, "process_multimodal_document")
@patch.object(processor_module.s3_client, "get_object")
@patch.object(processor_module.s3_client, "put_object")
@patch.object(processor_module.dynamodb, "Table")
def test_processor_image_success(mock_table, mock_s3_put, mock_s3_get, mock_multimodal):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_s3_get.return_value = {
        "ContentLength": 1024,
        "Body": MagicMock(read=MagicMock(return_value=b"fake-image-bytes")),
    }

    mock_multimodal.return_value = {
        "extracted_text": "Invoice #1042 Total: $120.00",
        "summary": "Sample invoice summary.",
        "tags": ["invoice", "finance"],
    }

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-docs-bucket"},
                    "object": {"key": "uploads/user-456/doc-789/receipt.png"},
                }
            }
        ]
    }

    result = processor_module.lambda_handler(event, None)
    assert result["statusCode"] == 200

    # Verify status updates: PROCESSING and PROCESSED
    assert mock_table_instance.update_item.call_count == 2
    last_update = mock_table_instance.update_item.call_args[1]["ExpressionAttributeValues"]
    assert last_update[":status"] == "PROCESSED"
    assert last_update[":summary"] == "Sample invoice summary."
    assert last_update[":tags"] == ["invoice", "finance"]


@patch.object(processor_module.bedrock_runtime, "invoke_model")
def test_generate_summary_bedrock_success(mock_invoke):
    mock_body = MagicMock()
    # Amazon Nova response structure: output.message.content[0].text
    mock_body.read.return_value = json.dumps({
        "output": {
            "message": {
                "content": [
                    {
                        "text": '{"summary": "Monthly cloud invoice.", "tags": ["cloud", "billing"]}'
                    }
                ],
                "role": "assistant",
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 45, "outputTokens": 32},
    }).encode("utf-8")
    mock_invoke.return_value = {"body": mock_body}

    text = "AWS Invoice details for compute services. Total amount due is $10.00."
    res = processor_module.generate_summary_and_tags(text)

    assert res["summary"] == "Monthly cloud invoice."
    assert "cloud" in res["tags"]
    assert "billing" in res["tags"]


@patch.object(processor_module.bedrock_runtime, "invoke_model")
def test_generate_summary_bedrock_malformed_fallback(mock_bedrock):
    # Simulate Nova returning an empty or non-JSON content structure
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({
        "output": {
            "message": {
                "content": [{"text": "I am unable to parse this document into json format."}],
                "role": "assistant",
            }
        }
    }).encode("utf-8")
    mock_bedrock.return_value = {"body": mock_body}

    text = "This document discusses Cloud Computing on AWS infrastructure for modern cloud apps."
    res = processor_module.generate_summary_and_tags(text)

    assert len(res["summary"]) > 0
    assert len(res["tags"]) > 0


@patch.object(processor_module.bedrock_runtime, "invoke_model")
def test_generate_summary_comprehend_fallback(mock_bedrock):
    # Simulate Bedrock unavailable or model access not granted
    mock_bedrock.side_effect = RuntimeError("AccessDenied: Model not enabled")

    text = (
        "This document describes a high-scale serverless architecture on AWS. "
        "It uses Lambda and S3 storage with DynamoDB databases."
    )
    res = processor_module.generate_summary_and_tags(text)

    assert len(res["summary"]) > 0
    assert len(res["tags"]) > 0
    assert any("serverless" in t or "architecture" in t or "document" in t for t in res["tags"])


@patch.object(processor_module, "process_multimodal_document")
@patch.object(processor_module.s3_client, "get_object")
@patch.object(processor_module.s3_client, "put_object")
@patch.object(processor_module.dynamodb, "Table")
def test_processor_pdf_async_success(mock_table, mock_s3_put, mock_s3_get, mock_multimodal):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_s3_get.return_value = {
        "ContentLength": 2048,
        "Body": MagicMock(read=MagicMock(return_value=b"%PDF-1.4 mock content")),
    }

    mock_multimodal.return_value = {
        "extracted_text": "Project Specification Document. Author: Engineering Team.",
        "summary": "Spec overview",
        "tags": ["spec", "engineering"],
    }

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-docs-bucket"},
                    "object": {"key": "uploads/user-456/doc-999/spec.pdf"},
                }
            }
        ]
    }

    result = processor_module.lambda_handler(event, None)
    assert result["statusCode"] == 200
    assert mock_multimodal.called
    assert mock_table_instance.update_item.call_count == 2


@patch.object(processor_module.dynamodb, "Table")
def test_processor_invalid_key_skipped(mock_table):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-docs-bucket"},
                    "object": {"key": "other-folder/random.txt"},
                }
            }
        ]
    }

    result = processor_module.lambda_handler(event, None)
    assert result["statusCode"] == 200
    assert not mock_table_instance.update_item.called


@patch.object(processor_module.s3_client, "get_object")
@patch.object(processor_module.dynamodb, "Table")
def test_processor_error_sets_failed_status(mock_table, mock_s3_get):
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    mock_s3_get.side_effect = RuntimeError("S3 service unavailable")

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-docs-bucket"},
                    "object": {"key": "uploads/user-456/doc-error/corrupt.png"},
                }
            }
        ]
    }

    with pytest.raises(RuntimeError):
        processor_module.lambda_handler(event, None)

    assert mock_table_instance.update_item.call_count == 2
    last_call = mock_table_instance.update_item.call_args[1]
    assert last_call["ExpressionAttributeValues"][":status"] == "FAILED"


def test_detect_pii_basic():
    sample_text = (
        "Contact me at john.doe@example.com or call 555-123-4567. "
        "SSN is 123-45-6789 and card is 4111-2222-3333-4444."
    )
    pii = processor_module.detect_pii_basic(sample_text)
    assert "EMAIL" in pii
    assert "PHONE" in pii
    assert "SSN" in pii
    assert "CREDIT_CARD" in pii
