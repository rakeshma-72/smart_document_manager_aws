#!/usr/bin/env bash
set -euo pipefail

echo ">>> Fetching Terraform outputs..."
cd "$(dirname "$0")/../infra"
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
CF_DIST_ID=$(terraform output -raw cloudfront_distribution_id)

echo "Target Frontend Bucket: $FRONTEND_BUCKET"
echo "CloudFront Distribution: $CF_DIST_ID"

echo ">>> Building React frontend..."
cd ../frontend
npm run build

echo ">>> Syncing build artifacts to S3..."
aws s3 sync dist/ "s3://${FRONTEND_BUCKET}" --delete

echo ">>> Invalidating CloudFront cache..."
aws cloudfront create-invalidation --distribution-id "${CF_DIST_ID}" --paths "/*"

echo ">>> Deployment completed successfully!"
