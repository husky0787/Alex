resource "aws_iam_role" "reporter" {
  name = "${local.name}-reporter"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" }
  }] })
  tags = local.tags
}
resource "aws_cloudwatch_log_group" "reporter" {
  name              = "/aws/lambda/${local.name}-reporter"
  retention_in_days = 3
  tags              = local.tags
}
resource "aws_iam_role_policy" "reporter" {
  role = aws_iam_role.reporter.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.reporter.arn}:*" },
    { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.jobs.arn },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.workload["api"].arn },
    { Effect = "Allow", Action = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"], Resource = var.aurora_cluster_arn }
  ] })
}
resource "aws_lambda_function" "reporter" {
  function_name    = "${local.name}-reporter"
  role             = aws_iam_role.reporter.arn
  filename         = var.reporter_zip
  source_code_hash = filebase64sha256(var.reporter_zip)
  handler          = "sqs_handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 300
  memory_size      = 1024
  environment {
    variables = {
      DEFAULT_AWS_REGION            = var.region
      AURORA_CLUSTER_ARN            = var.aurora_cluster_arn
      AURORA_SECRET_ARN             = aws_secretsmanager_secret.workload["api"].arn
      AURORA_DATABASE               = "alex_task09"
      OPENAI_AGENTS_DISABLE_TRACING = "1"
    }
  }
  tags       = local.tags
  depends_on = [aws_iam_role_policy.reporter]
}
resource "aws_lambda_event_source_mapping" "reporter" {
  event_source_arn        = aws_sqs_queue.jobs.arn
  function_name           = aws_lambda_function.reporter.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 2 }
}
