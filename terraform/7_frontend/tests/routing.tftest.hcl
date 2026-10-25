# Mocked plan only: no AWS credentials, state files or deployments required.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { name = "us-east-1" }
  }
}

override_data {
  target = data.terraform_remote_state.database
  values = {
    outputs = {
      aurora_cluster_arn = "arn:aws:rds:us-east-1:123456789012:cluster:test"
      aurora_secret_arn  = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
      database_name      = "alex"
    }
  }
}

override_data {
  target = data.terraform_remote_state.agents
  values = {
    outputs = {
      sqs_queue_arn = "arn:aws:sqs:us-east-1:123456789012:test"
      sqs_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test"
    }
  }
}

override_resource {
  target = aws_lambda_function.api
}

variables {
  clerk_jwks_url = "https://clerk.example.test/.well-known/jwks.json"
}

run "api_errors_preserve_origin_response" {
  command = plan

  assert {
    condition = alltrue([
      for error in aws_cloudfront_distribution.main.custom_error_response :
      !contains([403, 404], error.error_code) || (
        error.response_code == null && error.response_page_path == null
      )
    ])
    error_message = "API 403/404 responses must retain the origin status and body, not become an HTML success page."
  }

  assert {
    condition = alltrue([
      for error in aws_cloudfront_distribution.main.custom_error_response :
      error.error_caching_min_ttl == 0
    ])
    error_message = "Authorization and not-found errors must not be cached across requests."
  }

  assert {
    condition = toset([
      for behavior in aws_cloudfront_distribution.main.ordered_cache_behavior : behavior.path_pattern
    ]) == toset(["/api", "/api/*"])
    error_message = "Both the API root and child paths must reach API Gateway, never the static origin."
  }

  assert {
    condition = alltrue([
      for behavior in aws_cloudfront_distribution.main.ordered_cache_behavior :
      behavior.target_origin_id == "API-Gateway" &&
      behavior.min_ttl == 0 && behavior.default_ttl == 0 && behavior.max_ttl == 0 &&
      contains(behavior.forwarded_values[0].headers, "Authorization") &&
      length(behavior.function_association) == 0
    ])
    error_message = "API requests must forward credentials without caching or static-page rewriting."
  }

  assert {
    condition = length(aws_cloudfront_distribution.main.default_cache_behavior[0].function_association) == 1 && alltrue([
      for association in aws_cloudfront_distribution.main.default_cache_behavior[0].function_association :
      association.event_type == "viewer-request"
    ])
    error_message = "Static pages require viewer-request routing to their actual exported HTML files."
  }
}
