output "aws_region" {
  description = "Configured AWS deployment region"
  value       = var.aws_region
}

output "project_name" {
  description = "Project name prefix"
  value       = var.project_name
}

output "billing_alarm_arn" {
  description = "ARN of the monthly billing CloudWatch alarm"
  value       = try(aws_cloudwatch_metric_alarm.monthly_billing_alarm[0].arn, null)
}

output "billing_sns_topic_arn" {
  description = "ARN of the SNS topic receiving billing alert notifications"
  value       = try(aws_sns_topic.billing_alerts[0].arn, null)
}

output "documents_bucket_name" {
  description = "Private S3 bucket name for document uploads"
  value       = aws_s3_bucket.documents.id
}

output "documents_bucket_arn" {
  description = "ARN of the private documents S3 bucket"
  value       = aws_s3_bucket.documents.arn
}

output "frontend_bucket_name" {
  description = "S3 bucket name hosting the static React web application"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for frontend CDN cache invalidation"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name serving the web application"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "app_url" {
  description = "Public HTTPS application URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool"
  value       = aws_cognito_user_pool.main.arn
}

output "cognito_user_pool_client_id" {
  description = "Cognito Web Client ID for SPA authentication"
  value       = aws_cognito_user_pool_client.web.id
}

output "dynamodb_table_name" {
  description = "DynamoDB document metadata table name"
  value       = aws_dynamodb_table.documents.name
}

output "api_endpoint" {
  description = "API Gateway HTTP API base URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "processor_dlq_arn" {
  description = "ARN of the SQS Dead-Letter Queue for failed processing"
  value       = aws_sqs_queue.processor_dlq.arn
}

output "processor_dlq_url" {
  description = "URL of the SQS Dead-Letter Queue for failed processing"
  value       = aws_sqs_queue.processor_dlq.url
}


output "cloudwatch_dashboard_name" {
  description = "Name of the CloudWatch operational dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "operational_alerts_sns_arn" {
  description = "ARN of the operational SNS topic in primary region"
  value       = aws_sns_topic.operational_alerts.arn
}

output "state_machine_arn" {
  description = "ARN of the Step Functions document processing pipeline"
  value       = aws_sfn_state_machine.document_pipeline.arn
}

output "shares_table_name" {
  description = "DynamoDB shares table name for expiring download links"
  value       = aws_dynamodb_table.shares.name
}

output "audit_table_name" {
  description = "DynamoDB audit events table name"
  value       = aws_dynamodb_table.audit.name
}
