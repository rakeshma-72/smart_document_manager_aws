import collections
import json
import os
import re
import time
import urllib.parse
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)

s3_client = boto3.client("s3", config=boto_config)
dynamodb = boto3.resource("dynamodb", config=boto_config)
bedrock_runtime = boto3.client("bedrock-runtime", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-micro-v1:0")
BEDROCK_MULTIMODAL_MODEL_ID = os.environ.get(
    "BEDROCK_MULTIMODAL_MODEL_ID", "apac.amazon.nova-lite-v1:0"
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}
TEXT_EXTENSIONS = {".txt"}

# Safety constraints
MAX_FILE_BYTES = 4 * 1024 * 1024  # 4 MB payload limit (Bedrock Converse safe ceiling)
MAX_TEXT_CHARS = 10000  # Truncate extracted/input text to 10k chars for safety and cost control

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves"
}


def update_document_status(user_id: str, doc_id: str, status: str, extra_fields: dict = None):
    table = dynamodb.Table(DOCUMENTS_TABLE)
    update_expr = "SET #s = :status, #u = :updatedAt"
    expr_attr_names = {"#s": "status", "#u": "updatedAt"}
    expr_attr_values = {
        ":status": status,
        ":updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if extra_fields:
        for k, v in extra_fields.items():
            safe_k = f"#{k}"
            safe_v = f":{k}"
            update_expr += f", {safe_k} = {safe_v}"
            expr_attr_names[safe_k] = k
            expr_attr_values[safe_v] = v

    table.update_item(
        Key={"userId": user_id, "docId": doc_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
    )


def detect_pii_basic(text: str) -> list:
    """
    Performs basic regex-based PII detection without AWS Comprehend.
    Note: This is a basic pattern check for common identifiers (Email, Phone, SSN, Credit Card).
    """
    if not text:
        return []

    pii_types = set()
    patterns = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    }

    for pii_name, pattern in patterns.items():
        if re.search(pattern, text):
            pii_types.add(pii_name)

    return sorted(list(pii_types))


def fallback_summary_and_tags(text: str) -> dict:
    """
    Lightweight local fallback for summary and topic tags using keyword frequency.
    Used when Bedrock is unavailable or fails.
    """
    if not text or len(text.strip()) < 10:
        return {
            "summary": "Document contains minimal or no extractable text.",
            "tags": ["empty-doc"],
        }

    clean_sample = text[:MAX_TEXT_CHARS].strip()

    # Extract sentences for 2-sentence summary
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", clean_sample)
        if len(s.strip()) > 15
    ]
    summary_text = " ".join(sentences[:2]) if sentences else clean_sample[:160] + "..."

    # Frequency-based keyword extraction
    words = re.findall(r"\b[a-z]{3,20}\b", clean_sample.lower())
    content_words = [w for w in words if w not in STOPWORDS]
    counts = collections.Counter(content_words)
    top_tags = [word for word, _ in counts.most_common(5)] or ["document"]

    return {
        "summary": summary_text,
        "tags": top_tags,
    }


def parse_json_from_text(text: str) -> dict:
    """Safely extracts and parses JSON from LLM output string."""
    if not text:
        return {}
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return {}


def process_multimodal_document(file_bytes: bytes, file_ext: str) -> dict:
    """
    Extracts text, summary, and tags in a single call using Amazon Nova Lite via the Bedrock Converse API.
    Replaces Amazon Textract for PDF and image documents.
    """
    format_map = {
        ".pdf": "pdf",
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".tiff": "tiff",
        ".tif": "tiff",
    }
    fmt = format_map.get(file_ext)
    if not fmt:
        raise ValueError(f"Unsupported format for multimodal processing: {file_ext}")

    content_block = {}
    if fmt == "pdf":
        content_block = {
            "document": {
                "format": "pdf",
                "name": "uploaded_doc",
                "source": {"bytes": file_bytes},
            }
        }
    else:
        content_block = {
            "image": {
                "format": fmt,
                "source": {"bytes": file_bytes},
            }
        }

    prompt = (
        "Analyze this document accurately.\n"
        "1. Extract all text clearly.\n"
        "2. Provide a 2-sentence executive summary.\n"
        "3. Provide 3-5 lowercase topic keyword tags.\n"
        "Respond ONLY with valid JSON in this exact structure with no extra text or markdown:\n"
        '{"extracted_text": "...", "summary": "...", "tags": ["tag1", "tag2"]}'
    )

    try:
        response = bedrock_runtime.converse(
            modelId=BEDROCK_MULTIMODAL_MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        content_block,
                        {"text": prompt},
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.1},
        )

        resp_content = response.get("output", {}).get("message", {}).get("content", [])
        output_text = resp_content[0].get("text", "") if resp_content else ""
        parsed = parse_json_from_text(output_text)

        if parsed and "extracted_text" in parsed:
            raw_text = str(parsed.get("extracted_text", "")).strip()[:MAX_TEXT_CHARS]
            summary = str(parsed.get("summary", "")).strip()
            raw_tags = parsed.get("tags", [])
            tags = [str(t).lower().strip().replace("#", "") for t in raw_tags] if isinstance(raw_tags, list) else []

            if not summary or not tags:
                fb = fallback_summary_and_tags(raw_text)
                summary = summary or fb["summary"]
                tags = tags or fb["tags"]

            return {
                "extracted_text": raw_text,
                "summary": summary,
                "tags": tags[:6],
            }
        else:
            print("Failed to parse structured JSON from Nova Lite. Using text fallback.")
            raw_text = output_text[:MAX_TEXT_CHARS]
            fb = fallback_summary_and_tags(raw_text)
            return {
                "extracted_text": raw_text,
                "summary": fb["summary"],
                "tags": fb["tags"],
            }

    except Exception as exc:
        print(f"Nova Lite document extraction failed: {exc}")
        raise exc


def generate_summary_and_tags(text: str) -> dict:
    """
    Generates a concise executive summary and key tags for plain text (.txt) files
    using Amazon Nova Micro to optimize latency and cost.
    Fallback: local frequency-based NLP summary.
    """
    if not text or len(text.strip()) < 10:
        return {
            "summary": "Document contains minimal or no extractable text.",
            "tags": ["empty-doc"],
        }

    clean_sample = text[:3500].strip()

    try:
        prompt = (
            f"You are an AI document analysis assistant. Read the document excerpt below:\n\n"
            f'"""\n{clean_sample}\n"""\n\n'
            "Task:\n"
            "1. Provide a concise 2-sentence summary of the document.\n"
            "2. Provide 3 to 6 lowercase single-word tags representing key topics.\n"
            "Respond ONLY with valid JSON in this exact structure:\n"
            '{"summary": "...", "tags": ["tag1", "tag2", "tag3"]}'
        )

        nova_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            "inferenceConfig": {
                "max_new_tokens": 256,
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(nova_payload),
        )

        response_body = json.loads(response["body"].read().decode("utf-8"))
        content_list = response_body.get("output", {}).get("message", {}).get("content", [])
        output_text = content_list[0].get("text", "") if content_list else ""

        parsed = parse_json_from_text(output_text)
        if isinstance(parsed, dict) and "summary" in parsed and "tags" in parsed:
            raw_tags = parsed.get("tags")
            tags_list = (
                [str(t).lower().strip().replace("#", "") for t in raw_tags]
                if isinstance(raw_tags, list)
                else []
            )
            return {
                "summary": str(parsed.get("summary", "")).strip(),
                "tags": tags_list[:6],
            }

    except Exception as bedrock_err:
        print(f"Bedrock invocation failed ({type(bedrock_err).__name__}). Using local keyword fallback.")

    return fallback_summary_and_tags(clean_sample)


def lambda_handler(event, context):
    """
    S3 ObjectCreated event listener.
    Extracts text, summary, and tags via Bedrock (Nova Lite for PDF/images, Nova Micro for TXT),
    runs basic PII detection, saves extracted text to S3, and updates DynamoDB.
    """
    records = event.get("Records", [])
    if not records:
        print("No S3 records found in event.")
        return {"statusCode": 200, "message": "No records to process"}

    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        raw_key = record.get("s3", {}).get("object", {}).get("key", "")
        key = urllib.parse.unquote_plus(raw_key)

        print(f"Processing object: s3://{bucket}/{key}")

        # Expected format: uploads/{userId}/{docId}/{fileName}
        parts = key.split("/")
        if len(parts) < 4 or parts[0] != "uploads":
            print(f"Skipping key {key} (does not match uploads/{{userId}}/{{docId}}/{{fileName}})")
            continue

        user_id = parts[1]
        doc_id = parts[2]
        file_name = parts[3]
        file_ext = os.path.splitext(file_name)[1].lower()

        try:
            # Step 1: Transition status to PROCESSING
            update_document_status(user_id, doc_id, "PROCESSING")

            # Step 2: Fetch document from S3 with size check
            s3_obj = s3_client.get_object(Bucket=bucket, Key=key)
            content_length = s3_obj.get("ContentLength", 0)
            if content_length > MAX_FILE_BYTES:
                raise ValueError(
                    f"File size {content_length} bytes exceeds maximum allowed {MAX_FILE_BYTES} bytes (4MB)"
                )

            file_bytes = s3_obj["Body"].read()

            # Step 3: Process document based on file type
            if file_ext in IMAGE_EXTENSIONS or file_ext == ".pdf":
                multimodal_res = process_multimodal_document(file_bytes, file_ext)
                extracted_text = multimodal_res.get("extracted_text", "")
                summary = multimodal_res.get("summary", "")
                tags = multimodal_res.get("tags", [])
            elif file_ext in TEXT_EXTENSIONS:
                extracted_text = file_bytes.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
                ai_res = generate_summary_and_tags(extracted_text)
                summary = ai_res.get("summary", "")
                tags = ai_res.get("tags", [])
            else:
                raise ValueError(f"Unsupported file extension for extraction: {file_ext}")

            # Step 4: Run basic regex-based PII check
            pii_detected = detect_pii_basic(extracted_text)

            # Step 5: Save full extracted text to S3
            extracted_key = f"extracted-text/{user_id}/{doc_id}/extracted.txt"
            s3_client.put_object(
                Bucket=bucket,
                Key=extracted_key,
                Body=extracted_text.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )

            preview_snippet = (
                extracted_text[:500] if extracted_text else "No text detected in document."
            )
            word_count = len(extracted_text.split()) if extracted_text else 0

            # Step 6: Transition status to PROCESSED with AI metadata
            update_document_status(
                user_id,
                doc_id,
                "PROCESSED",
                {
                    "extractedTextKey": extracted_key,
                    "preview": preview_snippet,
                    "wordCount": word_count,
                    "summary": summary,
                    "tags": tags,
                    "piiEntities": pii_detected,
                },
            )
            print(
                f"Successfully processed {doc_id}: {word_count} words, {len(tags)} tags, PII: {pii_detected}."
            )

        except Exception as exc:
            print(f"Error processing {key}: {str(exc)}")
            update_document_status(
                user_id,
                doc_id,
                "FAILED",
                {"errorMessage": str(exc)[:250]},
            )
            raise exc

    return {"statusCode": 200, "message": "Processing batch completed"}
