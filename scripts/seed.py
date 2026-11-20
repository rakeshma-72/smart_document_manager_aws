"""
Utility script to seed dummy test document records in DynamoDB.
Usage: python scripts/seed.py [userId]
"""

import sys
import uuid
import datetime
import boto3

def seed_sample_documents(table_name="smart-doc-mgr-dev-documents", user_id="test-user-dev"):
    dynamodb = boto3.resource("dynamodb", region_name="ap-southeast-2")
    table = dynamodb.Table(table_name)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    sample_docs = [
        {
            "userId": user_id,
            "docId": str(uuid.uuid4()),
            "fileName": "aws_architecture_whitepaper.pdf",
            "contentType": "application/pdf",
            "fileSize": 1450200,
            "status": "PROCESSED",
            "createdAt": now,
            "updatedAt": now,
            "wordCount": 850,
            "summary": "Comprehensive overview of well-architected AWS serverless applications with cost optimization.",
            "tags": ["aws", "cloud", "architecture", "serverless"],
            "preview": "This whitepaper highlights AWS Well-Architected Framework pillars for serverless cloud systems."
        },
        {
            "userId": user_id,
            "docId": str(uuid.uuid4()),
            "fileName": "vendor_tax_invoice.png",
            "contentType": "image/png",
            "fileSize": 452100,
            "status": "PROCESSED",
            "createdAt": now,
            "updatedAt": now,
            "wordCount": 120,
            "summary": "Monthly vendor invoice for IT infrastructure hosting and SaaS licensing.",
            "tags": ["tax", "invoice", "finance"],
            "preview": "INVOICE #49201. Billed to Acme Inc. Total Due: $149.00. Payment terms Net 30."
        }
    ]

    print(f"Seeding {len(sample_docs)} documents for user: {user_id}")
    for doc in sample_docs:
        table.put_item(Item=doc)
        print(f"  + Added: {doc['fileName']} (ID: {doc['docId']})")

    print("Seeding completed successfully.")

if __name__ == "__main__":
    uid = sys.argv[1] if len(sys.argv) > 1 else "test-user-dev"
    seed_sample_documents(user_id=uid)
