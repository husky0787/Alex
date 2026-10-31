terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.28.0" }
  }
}
provider "aws" { region = "us-east-1" }
data "aws_caller_identity" "current" {}
variable "github_oidc_provider_arn" { type = string }

locals {
  account = data.aws_caller_identity.current.account_id
  tags    = { Project = "alex", Purpose = "manual-eks-cd" }
  stack   = "arn:aws:cloudformation:us-east-1:${local.account}:stack/alex-cd-window/*"
  eks = [
    "arn:aws:eks:us-east-1:${local.account}:cluster/alex-cd-window",
    "arn:aws:eks:us-east-1:${local.account}:nodegroup/alex-cd-window/*",
    "arn:aws:eks:us-east-1:${local.account}:access-entry/alex-cd-window/*"
  ]
}

resource "aws_ecr_repository" "cd" {
  name                 = "alex-cd-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  tags                 = local.tags
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_ecr_lifecycle_policy" "cd" {
  repository = aws_ecr_repository.cd.name
  policy = jsonencode({ rules = [{ rulePriority = 1, description = "Fallback expiry for interrupted release images",
    selection = { tagStatus = "any", countType = "sinceImagePushed", countUnit = "days", countNumber = 1 },
    action    = { type = "expire" }
  }] })
}
resource "aws_iam_role" "release" {
  name                 = "alex-cd-release"
  max_session_duration = 7200
  tags                 = local.tags
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
    Principal = { Federated = var.github_oidc_provider_arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:husky0787@180300086/Alex@1355610076:environment:alex-eks-cd"
    } }
  }] })
}
resource "aws_iam_role" "cloudformation" {
  name = "alex-cd-cloudformation"
  tags = local.tags
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Principal = { Service = "cloudformation.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role" "cluster" {
  name = "alex-cd-cluster"
  tags = local.tags
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_iam_role" "node" {
  name = "alex-cd-node"
  tags = local.tags
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "node" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_iam_role_policy" "release" {
  role = aws_iam_role.release.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Resource = aws_ecr_repository.cd.arn, Action = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
      "ecr:BatchDeleteImage", "ecr:DescribeImages", "ecr:ListTagsForResource"
    ] },
    { Effect = "Allow", Resource = local.stack, Action = [
      "cloudformation:CreateStack", "cloudformation:DeleteStack", "cloudformation:DescribeStacks",
      "cloudformation:DescribeStackEvents", "cloudformation:ListStackResources"
    ] },
    { Effect = "Allow", Action = "iam:PassRole", Resource = aws_iam_role.cloudformation.arn,
    Condition = { StringEquals = { "iam:PassedToService" = "cloudformation.amazonaws.com" } } },
    { Effect = "Allow", Action = "eks:DescribeCluster", Resource = local.eks[0] },
    { Effect = "Allow", Action = "ec2:DescribeAvailabilityZones", Resource = "*" }
  ] })
}
resource "aws_iam_role_policy" "cloudformation" {
  role = aws_iam_role.cloudformation.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["eks:CreateCluster", "eks:DeleteCluster", "eks:DescribeCluster",
      "eks:CreateNodegroup", "eks:DeleteNodegroup", "eks:DescribeNodegroup", "eks:ListNodegroups",
      "eks:CreateAccessEntry", "eks:DeleteAccessEntry", "eks:DescribeAccessEntry",
      "eks:AssociateAccessPolicy", "eks:DisassociateAccessPolicy", "eks:ListAssociatedAccessPolicies",
    "eks:TagResource", "eks:UntagResource", "eks:ListTagsForResource"], Resource = local.eks },
    { Effect = "Allow", Action = "iam:PassRole", Resource = [aws_iam_role.cluster.arn, aws_iam_role.node.arn],
    Condition = { StringEquals = { "iam:PassedToService" = ["eks.amazonaws.com", "ec2.amazonaws.com"] } } },
    { Effect = "Allow", Action = ["iam:GetRole"], Resource = [aws_iam_role.cluster.arn, aws_iam_role.node.arn] },
    { Effect = "Allow", Action = ["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeRouteTables",
      "ec2:DescribeInternetGateways", "ec2:DescribeAvailabilityZones", "ec2:DescribeVpcAttribute",
    "ec2:DescribeSecurityGroups", "ec2:DescribeNetworkInterfaces"], Resource = "*" },
    { Effect = "Allow", Action = ["ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateRouteTable", "ec2:CreateInternetGateway"],
    Resource = "*", Condition = { StringEquals = { "aws:RequestTag/Purpose" = "manual-eks-cd" } } },
    # CreateSubnet/CreateRouteTable also authorize their existing parent VPC.
    { Effect   = "Allow", Action = ["ec2:CreateSubnet", "ec2:CreateRouteTable"],
      Resource = "arn:aws:ec2:us-east-1:${local.account}:vpc/*",
    Condition = { StringEquals = { "ec2:ResourceTag/Purpose" = "manual-eks-cd" } } },
    { Effect = "Allow", Action = ["ec2:CreateTags"], Resource = "arn:aws:ec2:us-east-1:${local.account}:*/*",
    Condition = { StringEquals = { "ec2:CreateAction" = ["CreateVpc", "CreateSubnet", "CreateRouteTable", "CreateInternetGateway"] } } },
    { Effect = "Allow", Action = ["ec2:DeleteVpc", "ec2:DeleteSubnet", "ec2:DeleteRouteTable", "ec2:DeleteInternetGateway",
      "ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
      "ec2:CreateRoute", "ec2:DeleteRoute", "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
      "ec2:CreateTags", "ec2:DeleteTags"], Resource = "arn:aws:ec2:us-east-1:${local.account}:*/*",
    Condition = { StringEquals = { "ec2:ResourceTag/Purpose" = "manual-eks-cd" } } }
  ] })
}
output "github_variables" {
  value = {
    ALEX_CD_ROLE_ARN     = aws_iam_role.release.arn
    ALEX_CD_CF_ROLE_ARN  = aws_iam_role.cloudformation.arn
    ALEX_CD_CLUSTER_ROLE = aws_iam_role.cluster.arn
    ALEX_CD_NODE_ROLE    = aws_iam_role.node.arn
    ALEX_CD_REPOSITORY   = aws_ecr_repository.cd.repository_url
    ALEX_AWS_ACCOUNT_ID  = local.account
  }
}
