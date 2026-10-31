terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.28.0" }
  }
}
provider "aws" { region = "us-east-1" }

variable "existing_oidc_provider_arn" {
  description = "Reuse an existing GitHub provider rather than taking ownership of it."
  type        = string
  default     = ""
}

locals {
  tags         = { Project = "alex", Purpose = "task-10-cicd" }
  provider_arn = var.existing_oidc_provider_arn != "" ? var.existing_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.existing_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  tags           = local.tags
}

resource "aws_ecr_repository" "release" {
  name                 = "alex-ci-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration { encryption_type = "AES256" }
  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "release" {
  repository = aws_ecr_repository.release.name
  policy = jsonencode({ rules = [{ rulePriority = 1, description = "Keep the latest ten release images",
    selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 },
    action    = { type = "expire" }
  }] })
}

resource "aws_iam_role" "release" {
  name                 = "alex-ci-release"
  max_session_duration = 3600
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
    Principal = { Federated = local.provider_arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:husky0787/Alex:environment:alex-acceptance"
    } }
  }] })
  tags = local.tags
}

resource "aws_iam_role_policy" "release" {
  name = "publish-only-alex-ci-api"
  role = aws_iam_role.release.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Resource = aws_ecr_repository.release.arn, Action = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"
    ] }
  ] })
}

output "release_role_arn" { value = aws_iam_role.release.arn }
output "repository_url" { value = aws_ecr_repository.release.repository_url }
