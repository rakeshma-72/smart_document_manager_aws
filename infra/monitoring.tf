# =============================================================================
# Operational SNS Topic in Primary Region (ap-southeast-2)
# =============================================================================

resource "aws_sns_topic" "operational_alerts" {
  name = "${var.project_name}-${var.environment}-operational-alerts"
}

resource "aws_sns_topic_subscription" "operational_email" {
  count     = var.billing_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.operational_alerts.arn
  protocol  = "email"
  endpoint  = var.billing_alert_email
}

# =============================================================================
# CloudWatch Operational Dashboard
# =============================================================================

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      # Widget 1: API Gateway Traffic & Errors
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway Traffic & HTTP Status"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.http_api.id, { color = "#2ca02c", label = "Total Requests" }],
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.http_api.id, { color = "#ff7f0e", label = "4xx Client Errors" }],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.http_api.id, { color = "#d62728", label = "5xx Server Errors" }]
          ]
        }
      },

      # Widget 2: Pipeline Executions & API Invocations
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline Executions & API Invocations"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", aws_sfn_state_machine.document_pipeline.arn, { color = "#1f77b4", label = "Executions Started" }],
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", aws_sfn_state_machine.document_pipeline.arn, { color = "#2ca02c", label = "Executions Succeeded" }],
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", aws_sfn_state_machine.document_pipeline.arn, { color = "#d62728", label = "Executions Failed" }],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.upload_url.function_name, { color = "#aec7e8", label = "Upload-Url Invocations" }],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.list_docs.function_name, { color = "#98df8a", label = "List-Docs Invocations" }]
          ]
        }
      },

      # Widget 3: Pipeline Latency
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline State Machine Execution Time (ms)"
          region = var.aws_region
          period = 300
          stat   = "p95"
          metrics = [
            ["AWS/States", "ExecutionTime", "StateMachineArn", aws_sfn_state_machine.document_pipeline.arn, { color = "#9467bd", label = "Execution Time p95" }]
          ]
        }
      },

      # Widget 4: SQS DLQ Messages & DynamoDB Consumed Capacity
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Queue Depth (DLQ) & DynamoDB Read/Write Units"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.processor_dlq.name, { color = "#e377c2", label = "DLQ Message Count" }],
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.documents.name, { color = "#17becf", label = "DynamoDB Consumed RCU" }],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.documents.name, { color = "#bcbd22", label = "DynamoDB Consumed WCU" }]
          ]
        }
      }
    ]
  })
}
