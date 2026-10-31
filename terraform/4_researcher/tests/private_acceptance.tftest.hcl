mock_provider "aws" {}

variables {
  aws_region           = "us-east-1"
  openai_api_key       = ""
  alex_api_endpoint    = "https://example.invalid/ingest"
  alex_api_key         = "test-only"
  researcher_image_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/alex-researcher:test"
}

run "private_manual_acceptance" {
  command = plan
  variables { public_url_enabled = false }
  assert {
    condition     = length(aws_lambda_function.researcher) == 1 && length(aws_lambda_function_url.researcher) == 0 && length(aws_lambda_permission.allow_public_function_url_invoke) == 0 && length(aws_lambda_function.scheduler_lambda) == 0
    error_message = "Private acceptance must deploy the researcher without a public URL, public permission or scheduler."
  }
}

run "reject_http_scheduler_without_url" {
  command = plan
  variables {
    public_url_enabled = false
    scheduler_enabled  = true
  }
  expect_failures = [aws_ecr_repository.researcher]
}
