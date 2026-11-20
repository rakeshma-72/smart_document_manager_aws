import json
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


def lambda_handler(event, context):
    """
    Step 5: Save processing results into DynamoDB with status = PROCESSED.
    """
    user_id = event["userId"]
    doc_id = event["docId"]
    extracted_text_key = event.get("extractedTextKey", "")
    preview = event.get("preview", "")
    word_count = event.get("wordCount", 0)
    summary = event.get("summary", "")
    tags = event.get("tags", [])
    pii_entities = event.get("piiEntities", [])
    summary_provider = event.get("summaryProvider", "local")
    doc_type = event.get("docType", "other")
    key_fields = event.get("keyFields", [])

    table = dynamodb.Table(DOCUMENTS_TABLE)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    table.update_item(
        Key={"userId": user_id, "docId": doc_id},
        UpdateExpression=(
            "SET #s = :status, #u = :updatedAt, #pr = :processedAt, #k = :extractedKey, "
            "#p = :preview, #w = :wordCount, #sm = :summary, "
            "#tg = :tags, #pi = :piiEntities, #sp = :summaryProvider, "
            "#dt = :docType, #kf = :keyFields, currentStep = :cs, #st.#step = :sval"
        ),
        ExpressionAttributeNames={
            "#s": "status",
            "#u": "updatedAt",
            "#pr": "processedAt",
            "#k": "extractedTextKey",
            "#p": "preview",
            "#w": "wordCount",
            "#sm": "summary",
            "#tg": "tags",
            "#pi": "piiEntities",
            "#sp": "summaryProvider",
            "#dt": "docType",
            "#kf": "keyFields",
            "#st": "stepStatus",
            "#step": "save_results",
        },
        ExpressionAttributeValues={
            ":status": "PROCESSED",
            ":updatedAt": now_iso,
            ":processedAt": now_iso,
            ":extractedKey": extracted_text_key,
            ":preview": preview,
            ":wordCount": word_count,
            ":summary": summary,
            ":tags": tags,
            ":piiEntities": pii_entities,
            ":summaryProvider": summary_provider,
            ":docType": doc_type,
            ":keyFields": key_fields,
            ":cs": "save_results",
            ":sval": {"status": "COMPLETED", "timestamp": now_iso},
        },
    )

    print(f"Document {doc_id} marked PROCESSED (provider: {summary_provider}, type: {doc_type}).")
    output = dict(event)
    output.update({
        "status": "PROCESSED",
        "docId": doc_id,
        "userId": user_id,
        "summary": summary,
        "tags": tags,
        "wordCount": word_count,
        "summaryProvider": summary_provider,
        "docType": doc_type,
        "keyFields": key_fields,
    })
    return output
