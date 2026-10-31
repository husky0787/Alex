mock_provider "aws" {
  mock_data "aws_vpc" {
    defaults = { cidr_block = "172.31.0.0/16" }
  }
  mock_data "aws_security_group" {
    defaults = { vpc_id = "vpc-test" }
  }
  mock_resource "aws_launch_template" {
    defaults = { id = "lt-1234567890abcdef0", latest_version = 1 }
  }
  mock_data "aws_subnet" {
    defaults = { vpc_id = "vpc-test", map_public_ip_on_launch = true }
  }
  override_data {
    target = data.aws_subnet.nodes["subnet-a"]
    values = { vpc_id = "vpc-test", map_public_ip_on_launch = true, availability_zone = "us-east-1a" }
  }
  override_data {
    target = data.aws_subnet.nodes["subnet-b"]
    values = { vpc_id = "vpc-test", map_public_ip_on_launch = true, availability_zone = "us-east-1b" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test" }
  }
  mock_resource "aws_eks_cluster" {
    defaults = { arn = "arn:aws:eks:us-east-1:123456789012:cluster/alex-task09" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:us-east-1:123456789012:test" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:test" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-abcdef" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test/123" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/test/123" }
  }
  mock_resource "aws_eks_node_group" {
    defaults = { resources = [{ autoscaling_groups = [{ name = "task09-test-asg" }], remote_access_security_group_id = "" }] }
  }
}
variables {
  vpc_id                   = "vpc-test"
  public_subnet_ids        = ["subnet-a", "subnet-b"]
  private_subnets          = { a = { az = "us-east-1a", cidr = "172.31.160.0/24" }, b = { az = "us-east-1b", cidr = "172.31.161.0/24" } }
  operator_cidrs           = ["203.0.113.1/32"]
  operator_user_name       = "test"
  operator_principal_arn   = "arn:aws:iam::123456789012:user/test"
  aurora_cluster_arn       = "arn:aws:rds:us-east-1:123456789012:cluster:test"
  aurora_admin_secret_arn  = "arn:aws:secretsmanager:us-east-1:123456789012:secret:admin-abcdef"
  aurora_security_group_id = "sg-test"
  expires_at               = "2026-10-31T23:00:00Z"
  estimated_total_usd      = 20
  reporter_zip             = "main.tf"
}
run "bounded_isolated_deployment" {
  command = apply
  assert {
    condition     = aws_eks_cluster.this.upgrade_policy[0].support_type == "STANDARD" && aws_eks_node_group.this.scaling_config[0].max_size == 2
    error_message = "Bound node count and avoid extended-support charges."
  }
  assert {
    condition     = aws_lb.api.internal && aws_cloudfront_distribution.api.default_cache_behavior[0].viewer_protocol_policy == "https-only"
    error_message = "Only the HTTPS edge may expose the API."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.market.block_public_policy && !aws_s3_bucket.market.force_destroy && !aws_ecr_repository.api.force_delete
    error_message = "Do not expose market data or erase evidence implicitly on destroy."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.api.policy, "s3:") && !strcontains(aws_iam_role_policy.etl.policy, "rds-data:") && !strcontains(aws_iam_role_policy.api.policy, var.aurora_admin_secret_arn)
    error_message = "API/ETL identity permissions must remain distinct and omit admin credentials."
  }
  assert {
    condition     = aws_launch_template.nodes.metadata_options[0].http_tokens == "required" && aws_launch_template.nodes.metadata_options[0].http_put_response_hop_limit == 1 && aws_launch_template.nodes.credit_specification[0].cpu_credits == "standard"
    error_message = "Block pod IMDS access and unbounded T3 surplus credits."
  }
}
run "reject_open_control_plane" {
  command = plan
  variables { operator_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.operator_cidrs]
}
run "reject_over_budget" {
  command = plan
  variables { estimated_total_usd = 81 }
  expect_failures = [var.estimated_total_usd]
}
