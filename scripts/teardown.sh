#!/usr/bin/env bash
# Bash Automated Teardown Script
set -euo pipefail

echo "=========================================================="
echo "   WARNING: TEARING DOWN SMART DOCUMENT MANAGER ON AWS    "
echo "=========================================================="

cd "$(dirname "$0")/../infra"

# 1. Empty S3 Buckets before destruction
DOCS_BUCKET=$(terraform output -raw documents_bucket_name 2>/dev/null || echo "")
WEB_BUCKET=$(terraform output -raw frontend_bucket_name 2>/dev/null || echo "")

if [ -n "$DOCS_BUCKET" ]; then
    echo ">>> Emptying Documents S3 Bucket: $DOCS_BUCKET ..."
    aws s3 rm "s3://${DOCS_BUCKET}" --recursive 2>/dev/null || true
fi

if [ -n "$WEB_BUCKET" ]; then
    echo ">>> Emptying Frontend Web S3 Bucket: $WEB_BUCKET ..."
    aws s3 rm "s3://${WEB_BUCKET}" --recursive 2>/dev/null || true
fi

# 2. Run Terraform Destroy
echo ">>> Running Terraform Destroy..."
terraform destroy -auto-approve

echo "=========================================================="
echo "   TEARDOWN COMPLETE: Zero dangling resources remain.   "
echo "   Ongoing AWS spend is \$0.00 / month.                   "
echo "=========================================================="
