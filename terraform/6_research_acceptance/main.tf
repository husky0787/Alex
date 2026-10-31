terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name = "alex-reporter-acceptance"
  tags = { Project = "alex", Purpose = "task-06-acceptance" }
}

resource "aws_cloudwatch_log_group" "reporter" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 7
  tags              = local.tags
}

resource "aws_iam_role" "reporter" {
  name = "${local.name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "reporter" {
  name = local.name
  role = aws_iam_role.reporter.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "WriteOwnLogs", Effect = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.reporter.arn}:*"
      },
      {
        Sid      = "ReadWriteAcceptanceJob", Effect = "Allow"
        Action   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement", "rds-data:BeginTransaction", "rds-data:CommitTransaction", "rds-data:RollbackTransaction"]
        Resource = var.aurora_cluster_arn
      },
      {
        Sid    = "ReadDatabaseCredential", Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"], Resource = var.aurora_secret_arn
      },
      {
        Sid    = "RetrieveResearch", Effect = "Allow"
        Action = ["s3vectors:QueryVectors", "s3vectors:GetVectors"], Resource = var.vector_index_arn
      },
      {
        Sid    = "EmbedQuery", Effect = "Allow"
        Action = ["sagemaker:InvokeEndpoint"], Resource = var.sagemaker_endpoint_arn
      },
      {
        Sid      = "GenerateReport", Effect = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = var.bedrock_model_arns
      }
      ], var.secret_kms_key_arn == null ? [] : [{
        Sid    = "DecryptDatabaseCredential", Effect = "Allow"
        Action = ["kms:Decrypt"], Resource = var.secret_kms_key_arn
        Condition = {
          StringEquals = { "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com" }
        }
    }])
  })
}

resource "aws_lambda_function" "reporter" {
  function_name                  = local.name
  role                           = aws_iam_role.reporter.arn
  filename                       = var.reporter_zip_path
  source_code_hash               = filebase64sha256(var.reporter_zip_path)
  handler                        = "lambda_handler.lambda_handler"
  runtime                        = "python3.12"
  architectures                  = ["x86_64"]
  memory_size                    = 1024
  timeout                        = 300
  reserved_concurrent_executions = var.reserved_concurrency
  tags                           = local.tags

  environment {
    variables = {
      DEFAULT_AWS_REGION            = var.aws_region
      AURORA_CLUSTER_ARN            = var.aurora_cluster_arn
      AURORA_SECRET_ARN             = var.aurora_secret_arn
      AURORA_DATABASE               = var.aurora_database
      RESEARCH_AWS_REGION           = var.aws_region
      VECTOR_BUCKET                 = var.vector_bucket_name
      INDEX_NAME                    = var.vector_index_name
      SAGEMAKER_ENDPOINT            = var.sagemaker_endpoint_name
      BEDROCK_REGION                = var.aws_region
      BEDROCK_MODEL_ID              = "us.amazon.nova-pro-v1:0"
      OPENAI_AGENTS_DISABLE_TRACING = "1"
    }
  }

  depends_on = [aws_iam_role_policy.reporter]
}

output "reporter_function_name" {
  value = aws_lambda_function.reporter.function_name
}
