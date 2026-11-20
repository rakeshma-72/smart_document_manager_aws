# =============================================================================
# Dead-Letter Queue (SQS) & CloudWatch Alarm for Processing Failures
# =============================================================================

resource "aws_sqs_queue" "processor_dlq" {
  name                      = "${var.project_name}-${var.environment}-processor-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

resource "aws_cloudwatch_metric_alarm" "processor_dlq_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-processor-dlq-messages"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5 minutes
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Triggered when one or more failed document processing events land in the DLQ."
  alarm_actions       = [aws_sns_topic.operational_alerts.arn]

  dimensions = {
    QueueName = aws_sqs_queue.processor_dlq.name
  }
}

# =============================================================================
# Step Functions Failed Executions Alarm
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "sfn_failed_executions" {
  alarm_name          = "${var.project_name}-${var.environment}-sfn-failed-executions"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Triggered when one or more Step Functions state machine executions fail."
  alarm_actions       = [aws_sns_topic.operational_alerts.arn]

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.document_pipeline.arn
  }
}

# =============================================================================
# Pipeline Lambdas Packaging
# =============================================================================

data "archive_file" "trigger_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/trigger/app.py"
  output_path = "${path.module}/.terraform/trigger.zip"
}

data "archive_file" "validate_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/validate/app.py"
  output_path = "${path.module}/.terraform/validate.zip"
}

data "archive_file" "extract_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/extract/app.py"
  output_path = "${path.module}/.terraform/extract.zip"
}

data "archive_file" "summarize_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/summarize/app.py"
  output_path = "${path.module}/.terraform/summarize.zip"
}

data "archive_file" "detect_pii_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/detect_pii/app.py"
  output_path = "${path.module}/.terraform/detect_pii.zip"
}

data "archive_file" "save_results_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/save_results/app.py"
  output_path = "${path.module}/.terraform/save_results.zip"
}

data "archive_file" "notify_failure_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/notify_failure/app.py"
  output_path = "${path.module}/.terraform/notify_failure.zip"
}

data "archive_file" "chunk_text_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/chunk_text/app.py"
  output_path = "${path.module}/.terraform/chunk_text.zip"
}

data "archive_file" "embed_chunks_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/pipeline/embed_chunks/app.py"
  output_path = "${path.module}/.terraform/embed_chunks.zip"
}

# =============================================================================
# Helper Macro / Common IAM Assume Role
# =============================================================================

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# -----------------------------------------------------------------------------
# 1. Trigger Lambda (S3 -> Step Functions)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_trigger" {
  name               = "${var.project_name}-${var.environment}-lambda-pipeline-trigger"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "trigger_basic" {
  role       = aws_iam_role.lambda_trigger.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "trigger_policy" {
  name        = "${var.project_name}-${var.environment}-trigger-policy"
  description = "Allows trigger Lambda to start executions of document pipeline state machine"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "StartSFNExecution"
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = aws_sfn_state_machine.document_pipeline.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "trigger_custom" {
  role       = aws_iam_role.lambda_trigger.name
  policy_arn = aws_iam_policy.trigger_policy.arn
}

resource "aws_lambda_function" "pipeline_trigger" {
  function_name    = "${var.project_name}-${var.environment}-pipeline-trigger"
  filename         = data.archive_file.trigger_zip.output_path
  source_code_hash = data.archive_file.trigger_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_trigger.arn

  environment {
    variables = {
      STATE_MACHINE_ARN = aws_sfn_state_machine.document_pipeline.arn
    }
  }
}

resource "aws_lambda_permission" "s3_pipeline_trigger" {
  statement_id  = "AllowS3InvokePipelineTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pipeline_trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.documents.arn
}

# S3 ObjectCreated event trigger on uploads/ prefix -> pipeline trigger
resource "aws_s3_bucket_notification" "document_upload" {
  bucket = aws_s3_bucket.documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.pipeline_trigger.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }

  depends_on = [aws_lambda_permission.s3_pipeline_trigger]
}

# -----------------------------------------------------------------------------
# 2. Validate Lambda (S3 head, DynamoDB update)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_validate" {
  name               = "${var.project_name}-${var.environment}-lambda-validate"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "validate_basic" {
  role       = aws_iam_role.lambda_validate.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "validate_policy" {
  name = "${var.project_name}-${var.environment}-validate-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3HeadObject"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.documents.arn}/uploads/*"
      },
      {
        Sid      = "DynamoDBUpdate"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "validate_custom" {
  role       = aws_iam_role.lambda_validate.name
  policy_arn = aws_iam_policy.validate_policy.arn
}

resource "aws_lambda_function" "step_validate" {
  function_name    = "${var.project_name}-${var.environment}-step-validate"
  filename         = data.archive_file.validate_zip.output_path
  source_code_hash = data.archive_file.validate_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_validate.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 3. Extract Lambda (S3 get upload, S3 put extracted text, Bedrock Nova Lite)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_extract" {
  name               = "${var.project_name}-${var.environment}-lambda-extract"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "extract_basic" {
  role       = aws_iam_role.lambda_extract.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "extract_policy" {
  name = "${var.project_name}-${var.environment}-extract-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadUploadWriteExtracted"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.documents.arn}/uploads/*",
          "${aws_s3_bucket.documents.arn}/extracted-text/*"
        ]
      },
      {
        Sid    = "BedrockConverse"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      },
      {
        Sid      = "DynamoDBUpdateProgress"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "extract_custom" {
  role       = aws_iam_role.lambda_extract.name
  policy_arn = aws_iam_policy.extract_policy.arn
}

resource "aws_lambda_function" "step_extract" {
  function_name    = "${var.project_name}-${var.environment}-step-extract"
  filename         = data.archive_file.extract_zip.output_path
  source_code_hash = data.archive_file.extract_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 120
  role             = aws_iam_role.lambda_extract.arn

  environment {
    variables = {
      BEDROCK_MULTIMODAL_MODEL_ID = var.bedrock_multimodal_model_id
      DOCUMENTS_TABLE              = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 4. Summarize Lambda (S3 get extracted text, Groq with Bedrock Nova Micro fallback)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_summarize" {
  name               = "${var.project_name}-${var.environment}-lambda-summarize"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "summarize_basic" {
  role       = aws_iam_role.lambda_summarize.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "summarize_policy" {
  name = "${var.project_name}-${var.environment}-summarize-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadExtractedText"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.documents.arn}/extracted-text/*"
      },
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      },
      {
        Sid      = "DynamoDBUpdateProgress"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "summarize_custom" {
  role       = aws_iam_role.lambda_summarize.name
  policy_arn = aws_iam_policy.summarize_policy.arn
}

resource "aws_lambda_function" "step_summarize" {
  function_name    = "${var.project_name}-${var.environment}-step-summarize"
  filename         = data.archive_file.summarize_zip.output_path
  source_code_hash = data.archive_file.summarize_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 60
  role             = aws_iam_role.lambda_summarize.arn

  environment {
    variables = {
      GROQ_API_KEY     = var.groq_api_key
      GROQ_MODEL       = var.groq_model
      BEDROCK_MODEL_ID = var.bedrock_model_id
      DOCUMENTS_TABLE  = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 5. Detect PII Lambda (S3 get extracted text, regex analysis)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_detect_pii" {
  name               = "${var.project_name}-${var.environment}-lambda-detect-pii"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "detect_pii_basic" {
  role       = aws_iam_role.lambda_detect_pii.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "detect_pii_policy" {
  name = "${var.project_name}-${var.environment}-detect-pii-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadExtractedText"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.documents.arn}/extracted-text/*"
      },
      {
        Sid      = "DynamoDBUpdateProgress"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "detect_pii_custom" {
  role       = aws_iam_role.lambda_detect_pii.name
  policy_arn = aws_iam_policy.detect_pii_policy.arn
}

resource "aws_lambda_function" "step_detect_pii" {
  function_name    = "${var.project_name}-${var.environment}-step-detect-pii"
  filename         = data.archive_file.detect_pii_zip.output_path
  source_code_hash = data.archive_file.detect_pii_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_detect_pii.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 6. Save Results Lambda (DynamoDB update PROCESSED)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_save_results" {
  name               = "${var.project_name}-${var.environment}-lambda-save-results"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "save_results_basic" {
  role       = aws_iam_role.lambda_save_results.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "save_results_policy" {
  name = "${var.project_name}-${var.environment}-save-results-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBUpdateProcessed"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "save_results_custom" {
  role       = aws_iam_role.lambda_save_results.name
  policy_arn = aws_iam_policy.save_results_policy.arn
}

resource "aws_lambda_function" "step_save_results" {
  function_name    = "${var.project_name}-${var.environment}-step-save-results"
  filename         = data.archive_file.save_results_zip.output_path
  source_code_hash = data.archive_file.save_results_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_save_results.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 7. Chunk Text Lambda (S3 get extracted.txt, S3 put chunks.json)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_chunk_text" {
  name               = "${var.project_name}-${var.environment}-lambda-chunk-text"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "chunk_text_basic" {
  role       = aws_iam_role.lambda_chunk_text.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "chunk_text_policy" {
  name = "${var.project_name}-${var.environment}-chunk-text-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadExtractedWriteChunks"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.documents.arn}/extracted-text/*",
          "${aws_s3_bucket.documents.arn}/chunks/*"
        ]
      },
      {
        Sid      = "DynamoDBUpdateProgress"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "chunk_text_custom" {
  role       = aws_iam_role.lambda_chunk_text.name
  policy_arn = aws_iam_policy.chunk_text_policy.arn
}

resource "aws_lambda_function" "step_chunk_text" {
  function_name    = "${var.project_name}-${var.environment}-step-chunk-text"
  filename         = data.archive_file.chunk_text_zip.output_path
  source_code_hash = data.archive_file.chunk_text_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_chunk_text.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 8. Embed Chunks Lambda (S3 get chunks.json, Bedrock Titan V2, S3 put embeddings.json)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_embed_chunks" {
  name               = "${var.project_name}-${var.environment}-lambda-embed-chunks"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "embed_chunks_basic" {
  role       = aws_iam_role.lambda_embed_chunks.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "embed_chunks_policy" {
  name = "${var.project_name}-${var.environment}-embed-chunks-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadChunksWriteEmbeddings"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.documents.arn}/chunks/*",
          "${aws_s3_bucket.documents.arn}/embeddings/*"
        ]
      },
      {
        Sid    = "BedrockTitanEmbed"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      },
      {
        Sid      = "DynamoDBUpdateProgress"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "embed_chunks_custom" {
  role       = aws_iam_role.lambda_embed_chunks.name
  policy_arn = aws_iam_policy.embed_chunks_policy.arn
}

resource "aws_lambda_function" "step_embed_chunks" {
  function_name    = "${var.project_name}-${var.environment}-step-embed-chunks"
  filename         = data.archive_file.embed_chunks_zip.output_path
  source_code_hash = data.archive_file.embed_chunks_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 120
  role             = aws_iam_role.lambda_embed_chunks.arn

  environment {
    variables = {
      BEDROCK_EMBED_MODEL_ID = var.bedrock_embed_model_id
      DOCUMENTS_TABLE        = aws_dynamodb_table.documents.name
    }
  }
}

# -----------------------------------------------------------------------------
# 9. Notify Failure Lambda (Catch handler: DynamoDB FAILED, DLQ message)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_notify_failure" {
  name               = "${var.project_name}-${var.environment}-lambda-notify-failure"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "notify_failure_basic" {
  role       = aws_iam_role.lambda_notify_failure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "notify_failure_policy" {
  name = "${var.project_name}-${var.environment}-notify-failure-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBUpdateFailed"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      },
      {
        Sid      = "SQSSendDLQ"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.processor_dlq.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "notify_failure_custom" {
  role       = aws_iam_role.lambda_notify_failure.name
  policy_arn = aws_iam_policy.notify_failure_policy.arn
}

resource "aws_lambda_function" "step_notify_failure" {
  function_name    = "${var.project_name}-${var.environment}-step-notify-failure"
  filename         = data.archive_file.notify_failure_zip.output_path
  source_code_hash = data.archive_file.notify_failure_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_notify_failure.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
      DLQ_URL         = aws_sqs_queue.processor_dlq.url
    }
  }
}

# =============================================================================
# Step Functions State Machine
# =============================================================================

resource "aws_iam_role" "sfn_pipeline" {
  name = "${var.project_name}-${var.environment}-sfn-pipeline-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "sfn_pipeline_policy" {
  name = "${var.project_name}-${var.environment}-sfn-pipeline-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokePipelineLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.step_validate.arn,
          aws_lambda_function.step_extract.arn,
          aws_lambda_function.step_summarize.arn,
          aws_lambda_function.step_detect_pii.arn,
          aws_lambda_function.step_save_results.arn,
          aws_lambda_function.step_chunk_text.arn,
          aws_lambda_function.step_embed_chunks.arn,
          aws_lambda_function.step_notify_failure.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "sfn_custom" {
  role       = aws_iam_role.sfn_pipeline.name
  policy_arn = aws_iam_policy.sfn_pipeline_policy.arn
}

resource "aws_sfn_state_machine" "document_pipeline" {
  name     = "${var.project_name}-${var.environment}-document-pipeline"
  role_arn = aws_iam_role.sfn_pipeline.arn

  definition = jsonencode({
    Comment = "Smart Document Manager Multi-Step Processing Pipeline with RAG Chunking and Embeddings"
    StartAt = "ValidateFile"
    States = {
      ValidateFile = {
        Type     = "Task"
        Resource = aws_lambda_function.step_validate.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "ExtractText"
      }

      ExtractText = {
        Type     = "Task"
        Resource = aws_lambda_function.step_extract.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "ThrottlingException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "Summarize"
      }

      Summarize = {
        Type     = "Task"
        Resource = aws_lambda_function.step_summarize.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "DetectPII"
      }

      DetectPII = {
        Type     = "Task"
        Resource = aws_lambda_function.step_detect_pii.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "SaveResults"
      }

      SaveResults = {
        Type     = "Task"
        Resource = aws_lambda_function.step_save_results.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "ChunkText"
      }

      ChunkText = {
        Type     = "Task"
        Resource = aws_lambda_function.step_chunk_text.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        Next = "EmbedChunks"
      }

      EmbedChunks = {
        Type     = "Task"
        Resource = aws_lambda_function.step_embed_chunks.arn
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "ThrottlingException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "NotifyFailure"
            ResultPath  = "$.Error"
          }
        ]
        End = true
      }

      NotifyFailure = {
        Type     = "Task"
        Resource = aws_lambda_function.step_notify_failure.arn
        Parameters = {
          "ExecutionInput.$" = "$"
          "Error.$"          = "$.Error"
        }
        End = true
      }
    }
  })
}
