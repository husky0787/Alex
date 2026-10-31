terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28.0"
    }
  }
}

provider "aws" { region = "us-east-1" }
data "aws_caller_identity" "current" {}

variable "cluster_arn" { type = string }
variable "database_secret_arn" {
  type = string
  validation {
    condition     = strcontains(var.database_secret_arn, ":secret:alex-task11/database-") && !strcontains(var.database_secret_arn, "*")
    error_message = "Use only the dedicated showcase database secret ARN."
  }
}
variable "vector_index_arn" { type = string }
variable "vector_bucket" { type = string }
variable "sagemaker_endpoint_arn" { type = string }
variable "bedrock_model_arns" {
  type = list(string)
  validation {
    condition     = length(var.bedrock_model_arns) >= 2 && alltrue([for arn in var.bedrock_model_arns : startswith(arn, "arn:aws:bedrock:") && strcontains(arn, "nova-pro-v1:0") && !strcontains(arn, "*")])
    error_message = "Use explicit Nova Pro profile and destination model ARNs."
  }
}
variable "worker_directory" { type = string }

locals {
  workers = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  prefix  = "alex-task11"
  tags    = { Project = "alex", Purpose = "task-11-showcase" }
}

resource "aws_cloudwatch_log_group" "worker" {
  for_each          = local.workers
  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = 7
  tags              = local.tags
}

resource "aws_iam_role" "worker" {
  for_each = local.workers
  name     = "${local.prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "worker" {
  for_each = local.workers
  name     = "${local.prefix}-${each.key}"
  role     = aws_iam_role.worker[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.worker[each.key].arn}:*" },
      { Effect = "Allow", Action = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"], Resource = var.cluster_arn },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.database_secret_arn },
      { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = var.bedrock_model_arns }
      ], each.key == "reporter" ? [
      { Effect = "Allow", Action = ["s3vectors:QueryVectors", "s3vectors:GetVectors"], Resource = var.vector_index_arn },
      { Effect = "Allow", Action = ["sagemaker:InvokeEndpoint"], Resource = var.sagemaker_endpoint_arn }
      ] : [], each.key == "planner" ? [
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.analysis.arn] },
      { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [for name in ["reporter", "charter", "retirement"] : "arn:aws:lambda:us-east-1:${data.aws_caller_identity.current.account_id}:function:${local.prefix}-${name}"] }
    ] : [])
  })
}

resource "aws_lambda_function" "worker" {
  for_each         = local.workers
  function_name    = "${local.prefix}-${each.key}"
  role             = aws_iam_role.worker[each.key].arn
  filename         = "${var.worker_directory}/${each.key}.zip"
  source_code_hash = filebase64sha256("${var.worker_directory}/${each.key}.zip")
  handler          = each.key == "planner" ? "planner_queue.lambda_handler" : "lambda_handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  memory_size      = 1024
  timeout          = 300
  tags             = local.tags
  environment {
    variables = {
      DEFAULT_AWS_REGION            = "us-east-1"
      AURORA_CLUSTER_ARN            = var.cluster_arn
      AURORA_SECRET_ARN             = var.database_secret_arn
      AURORA_DATABASE               = "alex_task11"
      RESEARCH_AWS_REGION           = "us-east-1"
      VECTOR_BUCKET                 = var.vector_bucket
      INDEX_NAME                    = "financial-research"
      SAGEMAKER_ENDPOINT            = "alex-embedding-endpoint"
      BEDROCK_REGION                = "us-east-1"
      BEDROCK_MODEL_ID              = "us.amazon.nova-pro-v1:0"
      REPORTER_FUNCTION             = "${local.prefix}-reporter"
      CHARTER_FUNCTION              = "${local.prefix}-charter"
      RETIREMENT_FUNCTION           = "${local.prefix}-retirement"
      OPENAI_AGENTS_DISABLE_TRACING = "1"
    }
  }
  depends_on = [aws_iam_role_policy.worker]
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.prefix}-dead-letter"
  message_retention_seconds = 86400
  sqs_managed_sse_enabled   = true
  tags                      = local.tags
}

resource "aws_sqs_queue" "analysis" {
  name                       = "${local.prefix}-analysis"
  visibility_timeout_seconds = 1800
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead_letter.arn, maxReceiveCount = 1 })
  tags                       = local.tags
}

resource "aws_lambda_event_source_mapping" "analysis" {
  event_source_arn        = aws_sqs_queue.analysis.arn
  function_name           = aws_lambda_function.worker["planner"].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 2 }
}

output "queue_url" { value = aws_sqs_queue.analysis.url }
output "workers" { value = { for name, worker in aws_lambda_function.worker : name => worker.function_name } }
