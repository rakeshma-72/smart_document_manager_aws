# =============================================================================
# DynamoDB Metadata Table
# =============================================================================
resource "aws_dynamodb_table" "documents" {
  name         = "${var.project_name}-${var.environment}-documents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "docId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "docId"
    type = "S"
  }

  attribute {
    name = "createdAt"
    type = "S"
  }

  # Global Secondary Index: list user documents ordered by createdAt descending
  global_secondary_index {
    name            = "userId-createdAt-index"
    hash_key        = "userId"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }
}

# =============================================================================
# DynamoDB Shares Table
# =============================================================================
resource "aws_dynamodb_table" "shares" {
  name         = "${var.project_name}-${var.environment}-shares"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tokenHash" # SHA-256 hash of token

  attribute {
    name = "tokenHash"
    type = "S"
  }

  attribute {
    name = "shareId"
    type = "S"
  }

  attribute {
    name = "docId"
    type = "S"
  }

  # GSI to list shares by docId
  global_secondary_index {
    name            = "docId-index"
    hash_key        = "docId"
    range_key       = "shareId"
    projection_type = "ALL"
  }

  # GSI to query/revoke by shareId
  global_secondary_index {
    name            = "shareId-index"
    hash_key        = "shareId"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

# =============================================================================
# DynamoDB Audit Table
# =============================================================================
resource "aws_dynamodb_table" "audit" {
  name         = "${var.project_name}-${var.environment}-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "eventKey" # timestamp#id

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "eventKey"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}


# =============================================================================
# Lambda Packaging
# =============================================================================
data "archive_file" "upload_url_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/upload-url/app.py"
  output_path = "${path.module}/.terraform/upload_url.zip"
}

data "archive_file" "ask_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/ask/app.py"
  output_path = "${path.module}/.terraform/ask.zip"
}

data "archive_file" "list_docs_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/list-docs/app.py"
  output_path = "${path.module}/.terraform/list_docs.zip"
}

data "archive_file" "search_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/search/app.py"
  output_path = "${path.module}/.terraform/search.zip"
}

data "archive_file" "delete_doc_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/delete-doc/app.py"
  output_path = "${path.module}/.terraform/delete_doc.zip"
}

data "archive_file" "admin_stats_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/admin-stats/app.py"
  output_path = "${path.module}/.terraform/admin_stats.zip"
}

data "archive_file" "share_create_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/share-create/app.py"
  output_path = "${path.module}/.terraform/share_create.zip"
}

data "archive_file" "share_access_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/share-access/app.py"
  output_path = "${path.module}/.terraform/share_access.zip"
}

data "archive_file" "share_list_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/share-list/app.py"
  output_path = "${path.module}/.terraform/share_list.zip"
}

data "archive_file" "share_revoke_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/share-revoke/app.py"
  output_path = "${path.module}/.terraform/share_revoke.zip"
}

data "archive_file" "audit_list_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/audit-list/app.py"
  output_path = "${path.module}/.terraform/audit_list.zip"
}



# =============================================================================
# IAM Roles & Policies for Lambdas
# =============================================================================

# Upload URL Lambda Role
resource "aws_iam_role" "lambda_upload_url" {
  name = "${var.project_name}-${var.environment}-lambda-upload-url"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "upload_url_basic" {
  role       = aws_iam_role.lambda_upload_url.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "upload_url_policy" {
  name        = "${var.project_name}-${var.environment}-upload-url-policy"
  description = "Allows pre-signing S3 uploads and recording initial item in DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.documents.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "upload_url_custom" {
  role       = aws_iam_role.lambda_upload_url.name
  policy_arn = aws_iam_policy.upload_url_policy.arn
}

# List Docs Lambda Role
resource "aws_iam_role" "lambda_list_docs" {
  name = "${var.project_name}-${var.environment}-lambda-list-docs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "list_docs_basic" {
  role       = aws_iam_role.lambda_list_docs.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "list_docs_policy" {
  name        = "${var.project_name}-${var.environment}-list-docs-policy"
  description = "Allows querying user documents from DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:GetItem"
        ]
        Resource = [
          aws_dynamodb_table.documents.arn,
          "${aws_dynamodb_table.documents.arn}/index/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "list_docs_custom" {
  role       = aws_iam_role.lambda_list_docs.name
  policy_arn = aws_iam_policy.list_docs_policy.arn
}

# Delete Doc Lambda Role
resource "aws_iam_role" "lambda_delete_doc" {
  name = "${var.project_name}-${var.environment}-lambda-delete-doc"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_doc_basic" {
  role       = aws_iam_role.lambda_delete_doc.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "delete_doc_policy" {
  name        = "${var.project_name}-${var.environment}-delete-doc-policy"
  description = "Allows deleting document records from DynamoDB and objects from S3"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.documents.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.documents.arn}/uploads/*",
          "${aws_s3_bucket.documents.arn}/extracted-text/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_doc_custom" {
  role       = aws_iam_role.lambda_delete_doc.name
  policy_arn = aws_iam_policy.delete_doc_policy.arn
}

# =============================================================================
# Lambda Functions
# =============================================================================

resource "aws_lambda_function" "upload_url" {
  function_name    = "${var.project_name}-${var.environment}-upload-url"
  filename         = data.archive_file.upload_url_zip.output_path
  source_code_hash = data.archive_file.upload_url_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 10
  role             = aws_iam_role.lambda_upload_url.arn

  environment {
    variables = {
      DOCUMENTS_TABLE        = aws_dynamodb_table.documents.name
      DOCUMENTS_BUCKET       = aws_s3_bucket.documents.id
      URL_EXPIRATION_SECONDS = "300"
    }
  }
}

resource "aws_lambda_function" "list_docs" {
  function_name    = "${var.project_name}-${var.environment}-list-docs"
  filename         = data.archive_file.list_docs_zip.output_path
  source_code_hash = data.archive_file.list_docs_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 10
  role             = aws_iam_role.lambda_list_docs.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

# Search Lambda Role
resource "aws_iam_role" "lambda_search" {
  name = "${var.project_name}-${var.environment}-lambda-search"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "search_basic" {
  role       = aws_iam_role.lambda_search.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "search_policy" {
  name        = "${var.project_name}-${var.environment}-search-policy"
  description = "Permissions for search Lambda: query documents, read embeddings, invoke Titan embed model, and update daily usage"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBQueryAndUpdateUsage"
        Effect   = "Allow"
        Action   = [
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.documents.arn,
          "${aws_dynamodb_table.documents.arn}/index/*"
        ]
      },
      {
        Sid      = "S3ReadEmbeddings"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/embeddings/*"
        ]
      },
      {
        Sid      = "BedrockTitanEmbed"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "search_custom" {
  role       = aws_iam_role.lambda_search.name
  policy_arn = aws_iam_policy.search_policy.arn
}

resource "aws_lambda_function" "search" {
  function_name    = "${var.project_name}-${var.environment}-search"
  filename         = data.archive_file.search_zip.output_path
  source_code_hash = data.archive_file.search_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 30
  role             = aws_iam_role.lambda_search.arn

  environment {
    variables = {
      DOCUMENTS_TABLE        = aws_dynamodb_table.documents.name
      DOCUMENTS_BUCKET       = aws_s3_bucket.documents.id
      BEDROCK_EMBED_MODEL_ID = var.bedrock_embed_model_id
    }
  }
}

resource "aws_lambda_function" "delete_doc" {
  function_name    = "${var.project_name}-${var.environment}-delete-doc"
  filename         = data.archive_file.delete_doc_zip.output_path
  source_code_hash = data.archive_file.delete_doc_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 10
  role             = aws_iam_role.lambda_delete_doc.arn

  environment {
    variables = {
      DOCUMENTS_TABLE  = aws_dynamodb_table.documents.name
      DOCUMENTS_BUCKET = aws_s3_bucket.documents.id
    }
  }
}

# -----------------------------------------------------------------------------
# Ask Lambda Role & Function (RAG Question Answering)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_ask" {
  name = "${var.project_name}-${var.environment}-lambda-ask"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ask_basic" {
  role       = aws_iam_role.lambda_ask.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "ask_policy" {
  name        = "${var.project_name}-${var.environment}-ask-policy"
  description = "Permissions for ask Lambda to read embeddings and query DynamoDB/Bedrock"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ReadEmbeddings"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/embeddings/*"
        ]
      },
      {
        Sid      = "DynamoDBQuery"
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.documents.arn
      },
      {
        Sid      = "BedrockEmbedAndInvoke"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ask_custom" {
  role       = aws_iam_role.lambda_ask.name
  policy_arn = aws_iam_policy.ask_policy.arn
}

resource "aws_lambda_function" "ask" {
  function_name    = "${var.project_name}-${var.environment}-ask"
  filename         = data.archive_file.ask_zip.output_path
  source_code_hash = data.archive_file.ask_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 30
  role             = aws_iam_role.lambda_ask.arn

  environment {
    variables = {
      DOCUMENTS_TABLE        = aws_dynamodb_table.documents.name
      DOCUMENTS_BUCKET       = aws_s3_bucket.documents.id
      BEDROCK_EMBED_MODEL_ID = var.bedrock_embed_model_id
      BEDROCK_MODEL_ID       = var.bedrock_model_id
      GROQ_API_KEY           = var.groq_api_key
      GROQ_MODEL             = var.groq_model
    }
  }
}

# Admin Stats Lambda Role & Definition
resource "aws_iam_role" "lambda_admin_stats" {
  name               = "${var.project_name}-${var.environment}-lambda-admin-stats"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "admin_stats_basic" {
  role       = aws_iam_role.lambda_admin_stats.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "admin_stats_policy" {
  name        = "${var.project_name}-${var.environment}-admin-stats-policy"
  description = "Allows scanning DynamoDB table for aggregate statistics"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBScanOnly"
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem"]
        Resource = [
          aws_dynamodb_table.documents.arn,
          aws_dynamodb_table.audit.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "admin_stats_custom" {
  role       = aws_iam_role.lambda_admin_stats.name
  policy_arn = aws_iam_policy.admin_stats_policy.arn
}

resource "aws_lambda_function" "admin_stats" {
  function_name    = "${var.project_name}-${var.environment}-admin-stats"
  filename         = data.archive_file.admin_stats_zip.output_path
  source_code_hash = data.archive_file.admin_stats_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_admin_stats.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
      AUDIT_TABLE     = aws_dynamodb_table.audit.name
    }
  }
}

# =============================================================================
# Shares & Audit Lambda Roles & Functions
# =============================================================================

# 1. Share Create Lambda
resource "aws_iam_role" "lambda_share_create" {
  name               = "${var.project_name}-${var.environment}-lambda-share-create"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "share_create_basic" {
  role       = aws_iam_role.lambda_share_create.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "share_create_policy" {
  name = "${var.project_name}-${var.environment}-share-create-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBShareAccess"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = [
          aws_dynamodb_table.documents.arn,
          aws_dynamodb_table.shares.arn,
          aws_dynamodb_table.audit.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "share_create_custom" {
  role       = aws_iam_role.lambda_share_create.name
  policy_arn = aws_iam_policy.share_create_policy.arn
}

resource "aws_lambda_function" "share_create" {
  function_name    = "${var.project_name}-${var.environment}-share-create"
  filename         = data.archive_file.share_create_zip.output_path
  source_code_hash = data.archive_file.share_create_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_share_create.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
      SHARES_TABLE    = aws_dynamodb_table.shares.name
      AUDIT_TABLE     = aws_dynamodb_table.audit.name
      API_ENDPOINT    = aws_apigatewayv2_stage.default.invoke_url
    }
  }
}

# 2. Share Access Lambda (Public 302 Redirect to 60s SigV4 S3 GET)
resource "aws_iam_role" "lambda_share_access" {
  name               = "${var.project_name}-${var.environment}-lambda-share-access"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "share_access_basic" {
  role       = aws_iam_role.lambda_share_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "share_access_policy" {
  name = "${var.project_name}-${var.environment}-share-access-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBShareAccess"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:PutItem"]
        Resource = [
          aws_dynamodb_table.documents.arn,
          aws_dynamodb_table.shares.arn,
          aws_dynamodb_table.audit.arn
        ]
      },
      {
        Sid      = "S3GetObjectPresign"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.documents.arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "share_access_custom" {
  role       = aws_iam_role.lambda_share_access.name
  policy_arn = aws_iam_policy.share_access_policy.arn
}

resource "aws_lambda_function" "share_access" {
  function_name    = "${var.project_name}-${var.environment}-share-access"
  filename         = data.archive_file.share_access_zip.output_path
  source_code_hash = data.archive_file.share_access_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_share_access.arn

  environment {
    variables = {
      DOCUMENTS_TABLE  = aws_dynamodb_table.documents.name
      DOCUMENTS_BUCKET = aws_s3_bucket.documents.id
      SHARES_TABLE     = aws_dynamodb_table.shares.name
      AUDIT_TABLE      = aws_dynamodb_table.audit.name
    }
  }
}

# 3. Share List Lambda
resource "aws_iam_role" "lambda_share_list" {
  name               = "${var.project_name}-${var.environment}-lambda-share-list"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "share_list_basic" {
  role       = aws_iam_role.lambda_share_list.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "share_list_policy" {
  name = "${var.project_name}-${var.environment}-share-list-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBShareQuery"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.documents.arn,
          aws_dynamodb_table.shares.arn,
          "${aws_dynamodb_table.shares.arn}/index/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "share_list_custom" {
  role       = aws_iam_role.lambda_share_list.name
  policy_arn = aws_iam_policy.share_list_policy.arn
}

resource "aws_lambda_function" "share_list" {
  function_name    = "${var.project_name}-${var.environment}-share-list"
  filename         = data.archive_file.share_list_zip.output_path
  source_code_hash = data.archive_file.share_list_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_share_list.arn

  environment {
    variables = {
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
      SHARES_TABLE    = aws_dynamodb_table.shares.name
    }
  }
}

# 4. Share Revoke Lambda
resource "aws_iam_role" "lambda_share_revoke" {
  name               = "${var.project_name}-${var.environment}-lambda-share-revoke"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "share_revoke_basic" {
  role       = aws_iam_role.lambda_share_revoke.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "share_revoke_policy" {
  name = "${var.project_name}-${var.environment}-share-revoke-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBShareRevoke"
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:PutItem"]
        Resource = [
          aws_dynamodb_table.shares.arn,
          "${aws_dynamodb_table.shares.arn}/index/*",
          aws_dynamodb_table.audit.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "share_revoke_custom" {
  role       = aws_iam_role.lambda_share_revoke.name
  policy_arn = aws_iam_policy.share_revoke_policy.arn
}

resource "aws_lambda_function" "share_revoke" {
  function_name    = "${var.project_name}-${var.environment}-share-revoke"
  filename         = data.archive_file.share_revoke_zip.output_path
  source_code_hash = data.archive_file.share_revoke_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_share_revoke.arn

  environment {
    variables = {
      SHARES_TABLE = aws_dynamodb_table.shares.name
      AUDIT_TABLE  = aws_dynamodb_table.audit.name
    }
  }
}

# 5. Audit List Lambda
resource "aws_iam_role" "lambda_audit_list" {
  name               = "${var.project_name}-${var.environment}-lambda-audit-list"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "audit_list_basic" {
  role       = aws_iam_role.lambda_audit_list.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "audit_list_policy" {
  name = "${var.project_name}-${var.environment}-audit-list-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBAuditQuery"
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = aws_dynamodb_table.audit.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "audit_list_custom" {
  role       = aws_iam_role.lambda_audit_list.name
  policy_arn = aws_iam_policy.audit_list_policy.arn
}

resource "aws_lambda_function" "audit_list" {
  function_name    = "${var.project_name}-${var.environment}-audit-list"
  filename         = data.archive_file.audit_list_zip.output_path
  source_code_hash = data.archive_file.audit_list_zip.output_base64sha256
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 30
  role             = aws_iam_role.lambda_audit_list.arn

  environment {
    variables = {
      AUDIT_TABLE = aws_dynamodb_table.audit.name
    }
  }
}



# =============================================================================
# API Gateway HTTP API (v2) with Cognito JWT Authorizer
# =============================================================================

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project_name}-${var.environment}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.http_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-authorizer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://${aws_cognito_user_pool.main.endpoint}"
  }
}

# Integrations
resource "aws_apigatewayv2_integration" "upload_url" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.upload_url.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "list_docs" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.list_docs.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "search" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.search.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "delete_doc" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.delete_doc.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "ask" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ask.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "admin_stats" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.admin_stats.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Phase 4 Integrations
resource "aws_apigatewayv2_integration" "share_create" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.share_create.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "share_access" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.share_access.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "share_list" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.share_list.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "share_revoke" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.share_revoke.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "audit_list" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.audit_list.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}


# Routes
resource "aws_apigatewayv2_route" "upload_url" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "POST /documents/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.upload_url.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "list_docs" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /documents"
  target             = "integrations/${aws_apigatewayv2_integration.list_docs.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "search" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /documents/search"
  target             = "integrations/${aws_apigatewayv2_integration.search.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "delete_doc" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "DELETE /documents/{docId}"
  target             = "integrations/${aws_apigatewayv2_integration.delete_doc.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "ask" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "POST /ask"
  target             = "integrations/${aws_apigatewayv2_integration.ask.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "admin_stats" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /admin/stats"
  target             = "integrations/${aws_apigatewayv2_integration.admin_stats.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# Phase 4 Routes
resource "aws_apigatewayv2_route" "share_create" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "POST /documents/{docId}/share"
  target             = "integrations/${aws_apigatewayv2_integration.share_create.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "share_access" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /shared/{token}"
  target             = "integrations/${aws_apigatewayv2_integration.share_access.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "share_list" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /documents/{docId}/shares"
  target             = "integrations/${aws_apigatewayv2_integration.share_list.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "share_revoke" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "DELETE /shares/{shareId}"
  target             = "integrations/${aws_apigatewayv2_integration.share_revoke.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "audit_list" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /audit"
  target             = "integrations/${aws_apigatewayv2_integration.audit_list.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# Lambda Permissions for API Gateway
resource "aws_lambda_permission" "apigw_admin_stats" {
  statement_id  = "AllowAPIGatewayInvokeAdminStats"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.admin_stats.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_ask" {
  statement_id  = "AllowAPIGatewayInvokeAsk"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ask.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_upload_url" {
  statement_id  = "AllowAPIGatewayInvokeUploadUrl"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_url.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_list_docs" {
  statement_id  = "AllowAPIGatewayInvokeListDocs"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.list_docs.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_search" {
  statement_id  = "AllowAPIGatewayInvokeSearch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.search.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_delete_doc" {
  statement_id  = "AllowAPIGatewayInvokeDeleteDoc"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.delete_doc.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_share_create" {
  statement_id  = "AllowAPIGatewayInvokeShareCreate"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.share_create.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_share_access" {
  statement_id  = "AllowAPIGatewayInvokeShareAccess"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.share_access.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_share_list" {
  statement_id  = "AllowAPIGatewayInvokeShareList"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.share_list.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_share_revoke" {
  statement_id  = "AllowAPIGatewayInvokeShareRevoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.share_revoke.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_audit_list" {
  statement_id  = "AllowAPIGatewayInvokeAuditList"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.audit_list.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# Default Deployment Stage with per-user rate limiting / throttling
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  depends_on = [
    aws_apigatewayv2_route.ask,
    aws_apigatewayv2_route.share_access
  ]

  # Default stage route settings
  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }

  # Dedicated rate limiting on /ask to protect AI inference spend
  route_settings {
    route_key              = aws_apigatewayv2_route.ask.route_key
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }

  # Strict rate limiting on public /shared/{token} route to prevent brute-force
  route_settings {
    route_key              = aws_apigatewayv2_route.share_access.route_key
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
}
