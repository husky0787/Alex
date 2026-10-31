mock_provider "aws" {}

run "release_identity_is_environment_scoped" {
  command = apply
  assert {
    condition     = jsondecode(aws_iam_role.release.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:husky0787@180300086/Alex@1355610076:environment:alex-acceptance"
    error_message = "OIDC must be scoped to the exact repository environment."
  }
  assert {
    condition     = jsondecode(aws_iam_role.release.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "Require the AWS STS audience."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role_policy.release.policy).Statement) == 2 && jsondecode(aws_iam_role_policy.release.policy).Statement[0].Action == ["ecr:GetAuthorizationToken"]
    error_message = "Only ECR registry authentication may use a wildcard resource."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.release.policy).Statement[1].Resource == aws_ecr_repository.release.arn && alltrue([for action in jsondecode(aws_iam_role_policy.release.policy).Statement[1].Action : startswith(action, "ecr:")])
    error_message = "Publishing must be limited to the owned ECR repository with no infrastructure or database permissions."
  }
  assert {
    condition     = aws_ecr_repository.release.image_tag_mutability == "IMMUTABLE" && !aws_ecr_repository.release.force_delete
    error_message = "Do not overwrite releases or silently delete retained images."
  }
}

run "reuse_existing_provider_without_owning_it" {
  command = plan
  variables {
    existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Existing shared providers must stay outside this state."
  }
}
