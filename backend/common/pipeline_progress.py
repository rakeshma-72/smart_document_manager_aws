import time
import os
import boto3
from botocore.config import Config

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)
_dynamodb = None

def get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", config=boto_config)
    return _dynamodb

def update_pipeline_progress(user_id: str, doc_id: str, step_name: str, status: str = "COMPLETED", extra_fields: dict = None):
    """
    Updates the document item in DynamoDB with live pipeline tracker metadata:
    - currentStep: name of the latest step (e.g., 'validate', 'extract', 'summarize', 'detect_pii', 'save_results', 'chunk_text', 'embed_chunks')
    - stepStatus.<step_name>: map containing status and ISO timestamp
    - updatedAt: latest timestamp
    - optional extra_fields: e.g. status='PROCESSING'
    """
    table_name = os.environ.get("DOCUMENTS_TABLE")
    if not table_name or not user_id or not doc_id:
        return

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db = get_dynamodb()
    table = db.Table(table_name)

    update_expr = "SET currentStep = :cs, #st.#sname = :sval, #u = :updatedAt"
    expr_names = {
        "#st": "stepStatus",
        "#sname": step_name,
        "#u": "updatedAt",
    }
    expr_values = {
        ":cs": step_name,
        ":sval": {
            "status": status,
            "timestamp": now_iso
        },
        ":updatedAt": now_iso,
    }

    if extra_fields:
        for k, v in extra_fields.items():
            attr_placeholder = f"#{k}"
            val_placeholder = f":{k}"
            expr_names[attr_placeholder] = k
            expr_values[val_placeholder] = v
            update_expr += f", {attr_placeholder} = {val_placeholder}"

    try:
        # Ensure stepStatus map exists on item
        try:
            table.update_item(
                Key={"userId": user_id, "docId": doc_id},
                UpdateExpression="SET stepStatus = if_not_exists(stepStatus, :empty_map)",
                ExpressionAttributeValues={":empty_map": {}}
            )
        except Exception:
            pass

        table.update_item(
            Key={"userId": user_id, "docId": doc_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
    except Exception as e:
        print(f"Warning: Failed to update pipeline progress for {step_name}: {e}")
