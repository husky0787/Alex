mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/alex-reporter-acceptance-role" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/alex-reporter-acceptance" }
  }
}

variables {
  reporter_zip_path      = "README.md"
  aurora_cluster_arn     = "arn:aws:rds:us-east-1:123456789012:cluster:acceptance"
  aurora_secret_arn      = "arn:aws:secretsmanager:us-east-1:123456789012:secret:acceptance-abcdef"
  vector_bucket_name     = "acceptance-vectors"
  vector_index_arn       = "arn:aws:s3vectors:us-east-1:123456789012:bucket/acceptance-vectors/index/financial-research"
  sagemaker_endpoint_arn = "arn:aws:sagemaker:us-east-1:123456789012:endpoint/alex-embedding-endpoint"
  bedrock_model_arns = [
    "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-pro-v1:0",
    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"
  ]
}

run "isolated_reporter" {
  command = apply

  assert {
    condition     = aws_lambda_function.reporter.function_name == "alex-reporter-acceptance" && aws_iam_role.reporter.name == "alex-reporter-acceptance-role"
    error_message = "Acceptance must not replace the live Reporter or its role."
  }
  assert {
    condition     = aws_lambda_function.reporter.reserved_concurrent_executions == 1 && aws_lambda_function.reporter.timeout == 300
    error_message = "Acceptance execution must remain bounded."
  }
  assert {
    condition     = aws_lambda_function.reporter.environment[0].variables.BEDROCK_MODEL_ID == "us.amazon.nova-pro-v1:0" && aws_lambda_function.reporter.environment[0].variables.AURORA_CLUSTER_ARN == var.aurora_cluster_arn
    error_message = "Use the estimated model and explicitly supplied database."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.reporter.policy).Statement[3].Resource == var.vector_index_arn && jsondecode(aws_iam_role_policy.reporter.policy).Statement[4].Resource == var.sagemaker_endpoint_arn
    error_message = "Retrieval permissions must target the supplied index and endpoint."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role_policy.reporter.policy).Statement) == 6
    error_message = "Do not add unrelated permissions or KMS permissions by default."
  }
}

run "customer_managed_secret_key" {
  command = apply
  variables {
    secret_kms_key_arn = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000001"
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.reporter.policy).Statement[6].Resource == var.secret_kms_key_arn && jsondecode(aws_iam_role_policy.reporter.policy).Statement[6].Condition.StringEquals["kms:ViaService"] == "secretsmanager.us-east-1.amazonaws.com"
    error_message = "Optional decryption must be restricted to the selected secret key through Secrets Manager."
  }
}

run "reject_unbudgeted_region" {
  command = plan
  variables { aws_region = "eu-west-1" }
  expect_failures = [var.aws_region]
}

run "reject_wildcard_models" {
  command = plan
  variables { bedrock_model_arns = ["arn:aws:bedrock:*:*:*"] }
  expect_failures = [var.bedrock_model_arns]
}

run "low_quota_shared_pool" {
  command = apply
  variables { reserved_concurrency = -1 }
  assert {
    condition     = aws_lambda_function.reporter.reserved_concurrent_executions == -1 && aws_lambda_function.reporter.timeout == 300 && aws_lambda_function.reporter.function_name == "alex-reporter-acceptance"
    error_message = "The low-quota option must preserve isolation and timeout while using the shared pool."
  }
}
