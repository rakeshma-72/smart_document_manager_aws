import json
import os
import urllib.parse
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

boto_config = Config(
    region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    retries={"max_attempts": 3, "mode": "standard"},
)

sfn_client = boto3.client("stepfunctions", config=boto_config)
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")


def lambda_handler(event, context):
    """
    S3 ObjectCreated event listener.
    Parses S3 object metadata and starts Step Functions execution named after docId.
    Rejects or idempotently handles duplicate executions.
    """
    records = event.get("Records", [])
    if not records:
        print("No S3 records found in event.")
        return {"statusCode": 200, "message": "No records to process"}

    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        raw_key = record.get("s3", {}).get("object", {}).get("key", "")
        key = urllib.parse.unquote_plus(raw_key)

        parts = key.split("/")
        # Expected format: uploads/{userId}/{docId}/{fileName}
        if len(parts) < 4 or parts[0] != "uploads":
            print(f"Skipping key {key} (invalid path prefix)")
            continue

        user_id = parts[1]
        doc_id = parts[2]
        file_name = parts[3]
        file_ext = os.path.splitext(file_name)[1].lower()

        pipeline_input = {
            "bucket": bucket,
            "key": key,
            "userId": user_id,
            "docId": doc_id,
            "fileName": file_name,
            "fileExt": file_ext,
        }

        try:
            print(f"Starting execution {doc_id} for doc s3://{bucket}/{key}")
            sfn_client.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=doc_id,
                input=json.dumps(pipeline_input),
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "ExecutionAlreadyExists":
                print(f"Execution {doc_id} already exists; ignoring duplicate S3 trigger.")
            else:
                print(f"Failed to start execution {doc_id}: {str(e)}")
                raise e

    return {"statusCode": 200, "message": "Trigger processed successfully"}
