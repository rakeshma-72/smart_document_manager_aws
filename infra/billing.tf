# Billing alert SNS topic in us-east-1 where billing metrics are collected (optional, default disabled)
resource "aws_sns_topic" "billing_alerts" {
  count    = var.enable_billing_alerts ? 1 : 0
  provider = aws.us_east_1
  name     = "${var.project_name}-${var.environment}-billing-alerts"
}

# Optional email subscription to the billing alert SNS topic
resource "aws_sns_topic_subscription" "billing_email" {
  count     = var.enable_billing_alerts && var.billing_alert_email != "" ? 1 : 0
  provider  = aws.us_east_1
  topic_arn = aws_sns_topic.billing_alerts[0].arn
  protocol  = "email"
  endpoint  = var.billing_alert_email
}

# CloudWatch metric alarm triggering when total estimated charges reach budget threshold
resource "aws_cloudwatch_metric_alarm" "monthly_billing_alarm" {
  count               = var.enable_billing_alerts ? 1 : 0
  provider            = aws.us_east_1
  alarm_name          = "${var.project_name}-${var.environment}-monthly-budget-exceeded"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600 # 6 hours
  statistic           = "Maximum"
  threshold           = var.monthly_billing_threshold
  alarm_description   = "Triggered when estimated monthly AWS spend exceeds $${var.monthly_billing_threshold} USD."
  alarm_actions       = [aws_sns_topic.billing_alerts[0].arn]

  dimensions = {
    Currency = "USD"
  }
}
