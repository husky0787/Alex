terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.28.0" }
  }
}
provider "aws" { region = var.region }
data "aws_caller_identity" "current" {}
data "aws_vpc" "existing" { id = var.vpc_id }
data "aws_security_group" "aurora" { id = var.aurora_security_group_id }
data "aws_subnet" "nodes" {
  for_each = toset(var.public_subnet_ids)
  id       = each.value
}
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}
locals {
  name      = "alex-task09"
  tags      = { Project = "alex", Purpose = "task-09-acceptance", ExpiresAt = var.expires_at }
  namespace = "alex-cloud"
  addons = {
    vpc-cni                = "v1.23.2-eksbuild.8"
    kube-proxy             = "v1.35.3-eksbuild.62"
    coredns                = "v1.14.7-eksbuild.22"
    eks-pod-identity-agent = "v1.4.1-eksbuild.3"
    metrics-server         = "v0.9.0-eksbuild.14"
  }
}
resource "aws_subnet" "origin" {
  for_each          = var.private_subnets
  vpc_id            = var.vpc_id
  availability_zone = each.value.az
  cidr_block        = each.value.cidr
  tags              = merge(local.tags, { Name = "${local.name}-origin-${each.key}" })
}
resource "aws_route_table" "origin" {
  vpc_id = var.vpc_id
  tags   = local.tags
}
resource "aws_route_table_association" "origin" {
  for_each       = aws_subnet.origin
  subnet_id      = each.value.id
  route_table_id = aws_route_table.origin.id
}
resource "aws_iam_role" "cluster" {
  name = "${local.name}-cluster"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "eks.amazonaws.com" }
  }] })
  tags = local.tags
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_cloudwatch_log_group" "cluster" {
  name              = "/aws/eks/${local.name}/cluster"
  retention_in_days = 3
  tags              = local.tags
}
resource "aws_eks_cluster" "this" {
  name     = local.name
  role_arn = aws_iam_role.cluster.arn
  version  = "1.35"
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  upgrade_policy { support_type = "STANDARD" }
  vpc_config {
    subnet_ids              = var.public_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.operator_cidrs
  }
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
  tags                      = local.tags
  depends_on                = [aws_iam_role_policy_attachment.cluster, aws_cloudwatch_log_group.cluster]
  lifecycle {
    precondition {
      condition     = data.aws_security_group.aurora.vpc_id == var.vpc_id
      error_message = "Aurora and the workers must share the verified VPC. Verify existing TCP5432 ingress in the read-only preflight."
    }
    precondition {
      condition     = alltrue([for s in data.aws_subnet.nodes : s.vpc_id == var.vpc_id && s.map_public_ip_on_launch]) && length(toset([for s in data.aws_subnet.nodes : s.availability_zone])) == 2
      error_message = "Nodes require two public subnets in this VPC and distinct AZs."
    }
  }
}
resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = var.operator_principal_arn
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}
resource "aws_iam_user_policy" "operator" {
  name = "${local.name}-describe"
  user = var.operator_user_name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["eks:DescribeCluster"], Resource = aws_eks_cluster.this.arn
  }] })
}
resource "aws_iam_role" "nodes" {
  name = "${local.name}-nodes"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" }
  }] })
  tags = local.tags
}
resource "aws_iam_role_policy_attachment" "nodes" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_security_group" "nodes" {
  name   = "${local.name}-nodes"
  vpc_id = var.vpc_id
  tags   = local.tags
}
resource "aws_vpc_security_group_ingress_rule" "node_internal" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "-1"
}
resource "aws_vpc_security_group_ingress_rule" "control_to_nodes" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "-1"
}
resource "aws_vpc_security_group_ingress_rule" "nodes_to_control" {
  security_group_id            = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.nodes.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}
resource "aws_vpc_security_group_egress_rule" "nodes" {
  security_group_id = aws_security_group.nodes.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
resource "aws_launch_template" "nodes" {
  name_prefix            = "${local.name}-"
  vpc_security_group_ids = [aws_security_group.nodes.id]
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    http_endpoint               = "enabled"
  }
  credit_specification { cpu_credits = "standard" }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  tag_specifications {
    resource_type = "instance"
    tags          = local.tags
  }
  tags = local.tags
}
resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = local.name
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = var.public_subnet_ids
  instance_types  = ["t3.medium"]
  capacity_type   = "ON_DEMAND"
  ami_type        = "AL2023_x86_64_STANDARD"
  scaling_config {
    desired_size = 2
    min_size     = 2
    max_size     = 2
  }
  launch_template {
    id      = aws_launch_template.nodes.id
    version = aws_launch_template.nodes.latest_version
  }
  update_config { max_unavailable = 1 }
  tags       = local.tags
  depends_on = [aws_iam_role_policy_attachment.nodes]
}
resource "aws_eks_addon" "this" {
  for_each                    = local.addons
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.key
  addon_version               = each.value
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
  depends_on                  = [aws_eks_node_group.this]
  tags                        = local.tags
}
resource "aws_ecr_repository" "api" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}
resource "aws_s3_bucket" "market" {
  bucket        = "${local.name}-market-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
  tags          = local.tags
}
resource "aws_s3_bucket_public_access_block" "market" {
  bucket                  = aws_s3_bucket.market.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "market" {
  bucket = aws_s3_bucket.market.id
  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "market" {
  bucket = aws_s3_bucket.market.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.market.arn, "${aws_s3_bucket.market.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_secretsmanager_secret" "workload" {
  for_each                = toset(["api", "etl"])
  name                    = "${local.name}/${each.key}"
  recovery_window_in_days = 7
  tags                    = local.tags
}
resource "aws_sqs_queue" "jobs_dlq" {
  name                      = "${local.name}-jobs-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 86400
  tags                      = local.tags
}
resource "aws_sqs_queue" "jobs" {
  name                       = "${local.name}-jobs"
  visibility_timeout_seconds = 1800
  sqs_managed_sse_enabled    = true
  message_retention_seconds  = 86400
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn, maxReceiveCount = 2 })
  tags                       = local.tags
}
resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
  tags = local.tags
}
resource "aws_sqs_queue" "alerts" {
  name                      = "${local.name}-alerts"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 86400
  tags                      = local.tags
}
resource "aws_sqs_queue_policy" "alerts" {
  queue_url = aws_sqs_queue.alerts.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Principal = { Service = "sns.amazonaws.com" }, Action = "sqs:SendMessage",
    Resource = aws_sqs_queue.alerts.arn, Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.alerts.arn } }
  }] })
}
resource "aws_sns_topic_subscription" "alerts" {
  topic_arn            = aws_sns_topic.alerts.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.alerts.arn
  raw_message_delivery = true
}
resource "aws_iam_role" "workload" {
  for_each = toset(["api", "etl"])
  name     = "${local.name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "pods.eks.amazonaws.com" }, Action = ["sts:AssumeRole", "sts:TagSession"],
    Condition = { StringEquals = { "aws:RequestTag/kubernetes-namespace" = local.namespace,
    "aws:RequestTag/kubernetes-service-account" = each.key } }
  }] })
  tags = local.tags
}
resource "aws_eks_pod_identity_association" "workload" {
  for_each        = aws_iam_role.workload
  cluster_name    = aws_eks_cluster.this.name
  namespace       = local.namespace
  service_account = each.key
  role_arn        = each.value.arn
  depends_on      = [aws_eks_addon.this]
}
resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.workload["api"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.workload["api"].arn },
    { Effect = "Allow", Action = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"], Resource = var.aurora_cluster_arn },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.jobs.arn }
  ] })
}
resource "aws_iam_role_policy" "etl" {
  role = aws_iam_role.workload["etl"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.workload["etl"].arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["${aws_s3_bucket.market.arn}/raw/*", "${aws_s3_bucket.market.arn}/quarantine/*"] },
    { Effect = "Allow", Action = ["sns:Publish"], Resource = aws_sns_topic.alerts.arn }
  ] })
}
