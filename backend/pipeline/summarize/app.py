import json
import os
import re
import time
import urllib.request
import urllib.error
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)

s3_client = boto3.client("s3", config=boto_config)
bedrock_runtime = boto3.client("bedrock-runtime", config=boto_config)
dynamodb = boto3.resource("dynamodb", config=boto_config)

DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-micro-v1:0")

ALLOWED_DOC_TYPES = {"invoice", "resume", "report", "contract", "notes", "letter", "other"}

# Basic PII regex patterns for pre-Groq masking and keyFields validation
PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL_MASKED]"),
    (r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_MASKED]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_MASKED]"),
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[CARD_MASKED]"),
]


def contains_pii(text: str) -> bool:
    """Checks whether a string contains raw PII (emails, phone, SSN, credit cards)."""
    for pattern, _ in PII_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def mask_pii_for_groq(text: str) -> str:
    """Masks PII patterns before sending prompt to third-party Groq API."""
    masked = text
    for pattern, replacement in PII_PATTERNS:
        masked = re.sub(pattern, replacement, masked)
    return masked


def clean_json_response(raw_text: str) -> dict:
    """Strips <think> reasoning blocks and safely parses JSON object with docType and keyFields."""
    if not raw_text:
        return {}
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.DOTALL).strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            parsed = json.loads(match.group(0))
            summary = str(parsed.get("summary", "")).strip()
            raw_tags = parsed.get("tags", [])
            tags = (
                [str(t).lower().strip().replace("#", "") for t in raw_tags]
                if isinstance(raw_tags, list)
                else []
            )

            # Auto-classification validation against allow-list
            raw_type = str(parsed.get("docType", "")).lower().strip()
            doc_type = raw_type if raw_type in ALLOWED_DOC_TYPES else "other"

            # Parse and sanitize keyFields (at most 6 label/value pairs, truncated to 80 chars, PII excluded)
            raw_key_fields = parsed.get("keyFields", [])
            key_fields = []
            if isinstance(raw_key_fields, list):
                for item in raw_key_fields:
                    if isinstance(item, dict):
                        label = str(item.get("label", "")).strip()[:40]
                        val = str(item.get("value", "")).strip()[:80]
                        # Never store emails, phone numbers, SSNs or card numbers
                        if label and val and not contains_pii(val) and not contains_pii(label):
                            key_fields.append({"label": label, "value": val})
                    elif isinstance(item, (list, tuple)) and len(item) == 2:
                        label = str(item[0]).strip()[:40]
                        val = str(item[1]).strip()[:80]
                        if label and val and not contains_pii(val) and not contains_pii(label):
                            key_fields.append({"label": label, "value": val})
                    if len(key_fields) >= 6:
                        break

            return {
                "summary": summary,
                "tags": tags[:6],
                "docType": doc_type,
                "keyFields": key_fields
            }
        except Exception:
            pass
    return {}


def summarize_with_groq(text: str) -> dict:
    """Summarizes text using Groq with PII masked and JSON output mode."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")

    safe_text = mask_pii_for_groq(text[:3500])
    prompt = (
        "Analyze this document. In valid JSON, provide:\n"
        "1. summary: 2 concise sentences.\n"
        "2. tags: 3 to 5 lowercase topic keywords.\n"
        "3. docType: exactly one of: invoice, resume, report, contract, notes, letter, other.\n"
        "4. keyFields: list of up to 6 key data points with label and value (e.g. dates, names, organizations, amounts). Never include emails, phone numbers, SSNs or credit cards.\n"
        "Respond with valid JSON in this exact structure:\n"
        '{"summary": "...", "tags": ["tag1"], "docType": "invoice", "keyFields": [{"label": "Amount Due", "value": "$150.00"}]}'
    )

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "SmartDocManager/2.0",
        },
        data=json.dumps({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "You are a professional document analysis assistant that outputs strictly valid JSON."},
                {"role": "user", "content": f"{prompt}\n\nDocument:\n{safe_text}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 300,
        }).encode("utf-8"),
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        raw_content = data["choices"][0]["message"]["content"]
        parsed = clean_json_response(raw_content)
        if parsed.get("summary"):
            return parsed
        raise ValueError("Groq returned empty summary")


def summarize_with_bedrock(text: str) -> dict:
    """Fallback: Generates summary, tags, docType and keyFields using Amazon Bedrock Nova Micro."""
    clean_sample = text[:3500].strip()
    prompt = (
        "Analyze this document. In valid JSON, provide:\n"
        "1. summary: 2 concise sentences.\n"
        "2. tags: 3 to 5 lowercase topic keywords.\n"
        "3. docType: exactly one of: invoice, resume, report, contract, notes, letter, other.\n"
        "4. keyFields: list of up to 6 key data points with label and value (e.g. dates, names, organizations, amounts). Never include emails, phone numbers, SSNs or credit cards.\n"
        "Respond ONLY with valid JSON in this exact structure with no extra text:\n"
        '{"summary": "...", "tags": ["tag1"], "docType": "report", "keyFields": [{"label": "Date", "value": "2026-11-05"}]}\n\n'
        f"Document:\n{clean_sample}"
    )

    payload = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"max_new_tokens": 300, "temperature": 0.2, "top_p": 0.9},
    }

    resp = bedrock_runtime.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(payload),
    )
    result = json.loads(resp["body"].read().decode("utf-8"))
    content_list = result.get("output", {}).get("message", {}).get("content", [])
    raw_text = content_list[0].get("text", "") if content_list else ""
    parsed = clean_json_response(raw_text)
    if parsed.get("summary"):
        return parsed
    raise ValueError("Bedrock returned empty summary")


def lambda_handler(event, context):
    """
    Step 3: Read extracted text from S3, summarize & classify with Groq (or fallback to Bedrock Nova Micro).
    Passes summary, tags, docType, and keyFields to the next state, and updates live pipeline progress.
    """
    bucket = event["bucket"]
    extracted_key = event["extractedTextKey"]
    user_id = event.get("userId")
    doc_id = event.get("docId")

    s3_obj = s3_client.get_object(Bucket=bucket, Key=extracted_key)
    text = s3_obj["Body"].read().decode("utf-8", errors="replace").strip()

    if not text or len(text) < 10:
        summary_res = {
            "summary": "Document contains minimal or no extractable text.",
            "tags": ["empty-doc"],
            "docType": "other",
            "keyFields": [],
        }
        provider = "local"
    else:
        # Strategy: Groq primary -> Bedrock Nova Micro fallback -> local heuristic
        try:
            summary_res = summarize_with_groq(text)
            provider = "groq"
        except Exception as e_groq:
            print(f"Groq summarization failed ({type(e_groq).__name__}). Falling back to Bedrock Nova Micro.")
            try:
                summary_res = summarize_with_bedrock(text)
                provider = "nova"
            except Exception as e_bedrock:
                print(f"Bedrock summarization failed ({type(e_bedrock).__name__}). Using local heuristic.")
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]
                summary_res = {
                    "summary": " ".join(sentences[:2]) if sentences else text[:160] + "...",
                    "tags": ["document", "upload"],
                    "docType": "other",
                    "keyFields": [],
                }
                provider = "local"

    print(f"Summary generated using provider: {provider}, docType: {summary_res.get('docType', 'other')}")

    # Record pipeline progress
    if DOCUMENTS_TABLE and user_id and doc_id:
        try:
            table = dynamodb.Table(DOCUMENTS_TABLE)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            table.update_item(
                Key={"userId": user_id, "docId": doc_id},
                UpdateExpression="SET currentStep = :cs, #st.#step = :sval, #u = :updatedAt",
                ExpressionAttributeNames={
                    "#st": "stepStatus",
                    "#step": "summarize",
                    "#u": "updatedAt"
                },
                ExpressionAttributeValues={
                    ":cs": "summarize",
                    ":sval": {"status": "COMPLETED", "timestamp": now_iso},
                    ":updatedAt": now_iso
                }
            )
        except Exception as e:
            print(f"Warning: Failed to update progress in summarize: {e}")

    output = dict(event)
    output["summary"] = summary_res.get("summary", "")
    output["tags"] = summary_res.get("tags", [])
    output["docType"] = summary_res.get("docType", "other")
    output["keyFields"] = summary_res.get("keyFields", [])
    output["summaryProvider"] = provider
    return output
