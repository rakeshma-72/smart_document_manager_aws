# PowerShell script to build and deploy frontend to S3 and CloudFront
param (
    [string]$DistPath = "frontend/dist"
)

$ErrorActionPreference = "Stop"

Write-Host ">>> Fetching Terraform outputs..." -ForegroundColor Cyan
Set-Location -Path "$PSScriptRoot/../infra"
$frontendBucket = terraform output -raw frontend_bucket_name
$cfDistId = terraform output -raw cloudfront_distribution_id

Write-Host "Target Frontend Bucket: $frontendBucket" -ForegroundColor Green
Write-Host "CloudFront Distribution: $cfDistId" -ForegroundColor Green

Write-Host ">>> Building React frontend..." -ForegroundColor Cyan
Set-Location -Path "$PSScriptRoot/../frontend"
npm run build

Write-Host ">>> Syncing build artifacts to S3..." -ForegroundColor Cyan
aws s3 sync dist/ "s3://$frontendBucket" --delete

Write-Host ">>> Invalidating CloudFront cache..." -ForegroundColor Cyan
aws cloudfront create-invalidation --distribution-id $cfDistId --paths "/*"

Write-Host ">>> Deployment completed successfully!" -ForegroundColor Green
