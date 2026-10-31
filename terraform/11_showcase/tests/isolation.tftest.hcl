mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/alex-task11-mock" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:us-east-1:123456789012:function:alex-task11-mock" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:us-east-1:123456789012:alex-task11-mock" }
  }
}

run "worker_permissions_and_queue_bounds" {
  command = apply
  assert {
    condition     = alltrue([for name, fn in aws_lambda_function.worker : fn.environment[0].variables.AURORA_DATABASE == "alex_task11" && startswith(fn.function_name, "alex-task11-")])
    error_message = "Every worker must use the dedicated database and function prefix."
  }
  assert {
    condition     = alltrue([for name, policy in aws_iam_role_policy.worker : length([for statement in jsondecode(policy.policy).Statement : statement if contains(statement.Action, "lambda:InvokeFunction")]) == (name == "planner" ? 1 : 0)])
    error_message = "Only Planner may invoke the analysis workers."
  }
  assert {
    condition     = alltrue([for name, policy in aws_iam_role_policy.worker : length([for statement in jsondecode(policy.policy).Statement : statement if contains(statement.Action, "s3vectors:QueryVectors")]) == (name == "reporter" ? 1 : 0)])
    error_message = "Only Reporter may retrieve research vectors."
  }
  assert {
    condition     = jsondecode(aws_sqs_queue.analysis.redrive_policy).maxReceiveCount == 1 && aws_lambda_event_source_mapping.analysis.batch_size == 1 && contains(aws_lambda_event_source_mapping.analysis.function_response_types, "ReportBatchItemFailures")
    error_message = "Acceptance queue must bound retries and report individual failures."
  }
}

run "reject_existing_application_secret" {
  command = plan
  variables { database_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:alex-database-original" }
  expect_failures = [var.database_secret_arn]
}

run "reject_unbounded_models" {
  command = plan
  variables { bedrock_model_arns = ["arn:aws:bedrock:us-east-1::foundation-model/*", "*"] }
  expect_failures = [var.bedrock_model_arns]
}
