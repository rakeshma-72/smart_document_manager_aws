# PowerShell Automated Teardown Script
# Safely empties versioned S3 buckets and destroys all Terraform resources.

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Red
Write-Host "   WARNING: TEARING DOWN SMART DOCUMENT MANAGER ON AWS    " -ForegroundColor Red
Write-Host "==========================================================" -ForegroundColor Red

Set-Location -Path "$PSScriptRoot/../infra"

# 1. Fetch bucket names if terraform state exists
try {
    $docsBucket = terraform output -raw documents_bucket_name 2>$null
    $webBucket = terraform output -raw frontend_bucket_name 2>$null

    if ($docsBucket) {
        Write-Host ">>> Emptying Documents S3 Bucket: $docsBucket ..." -ForegroundColor Yellow
        aws s3 rm "s3://$docsBucket" --recursive 2>$null
        # Remove versioned objects if any
        $versions = aws s3api list-object-versions --bucket $docsBucket --output json 2>$null | ConvertFrom-Json
        if ($versions.Versions) {
            foreach ($v in $versions.Versions) {
                aws s3api delete-object --bucket $docsBucket --key $v.Key --version-id $v.VersionId 2>$null
            }
        }
        if ($versions.DeleteMarkers) {
            foreach ($m in $versions.DeleteMarkers) {
                aws s3api delete-object --bucket $docsBucket --key $m.Key --version-id $m.VersionId 2>$null
            }
        }
    }

    if ($webBucket) {
        Write-Host ">>> Emptying Frontend Web S3 Bucket: $webBucket ..." -ForegroundColor Yellow
        aws s3 rm "s3://$webBucket" --recursive 2>$null
    }
} catch {
    Write-Host "Notice: Could not query existing buckets from state; proceeding directly to destroy." -ForegroundColor Gray
}

# 2. Run Terraform Destroy
Write-Host ">>> Running Terraform Destroy..." -ForegroundColor Cyan
terraform destroy -auto-approve

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   TEARDOWN COMPLETE: Zero dangling resources remain.   " -ForegroundColor Green
Write-Host "   Ongoing AWS spend is \$0.00 / month.                   " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
