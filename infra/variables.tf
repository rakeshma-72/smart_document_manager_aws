variable "aws_region" {
  type        = string
  description = "Primary AWS region for application resources"
  default     = "ap-southeast-2"
}

variable "project_name" {
  type        = string
  description = "Project identifier used in resource names and tagging"
  default     = "smart-doc-mgr"
}

variable "environment" {
  type        = string
  description = "Deployment environment name (dev, staging, prod)"
  default     = "dev"
}

variable "monthly_billing_threshold" {
  type        = number
  description = "Estimated monthly spend in USD to trigger the billing alarm"
  default     = 10
}

variable "enable_billing_alerts" {
  type        = bool
  description = "Enable us-east-1 billing CloudWatch alarm and SNS topic. Set to false if us-east-1 is blocked by SCP."
  default     = false
}

variable "billing_alert_email" {
  type        = string
  description = "Email address to receive billing threshold breach notifications"
  default     = ""
}


variable "bedrock_model_id" {
  type        = string
  description = "Bedrock inference profile or model ID for text summarization (Amazon Nova Micro)"
  default     = "apac.amazon.nova-micro-v1:0"
}

variable "bedrock_multimodal_model_id" {
  type        = string
  description = "Bedrock inference profile or model ID for multimodal document extraction (Amazon Nova Lite)"
  default     = "apac.amazon.nova-lite-v1:0"
}

variable "bedrock_embed_model_id" {
  type        = string
  description = "Bedrock foundation model ID for dense vector text embeddings"
  default     = "amazon.titan-embed-text-v2:0"
}

variable "groq_api_key" {
  type        = string
  description = "Groq API key for high-speed document summarization"
  sensitive   = true
  default     = ""
}

variable "groq_model" {
  type        = string
  description = "Groq model ID for document summarization"
  default     = "qwen/qwen3.8-27b"
}
