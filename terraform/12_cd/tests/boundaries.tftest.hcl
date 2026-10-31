mock_provider "aws" {}
override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "123456789012" }
}
variables {
  github_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
}
run "bounded_delivery_roles" {
  command = apply
  assert {
    condition     = aws_ecr_repository.cd.name == "alex-cd-api" && !aws_ecr_repository.cd.force_delete
    error_message = "Only a dedicated non-force-deletable release repository is permitted."
  }
  assert {
    condition     = jsondecode(aws_iam_role.release.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:husky0787@180300086/Alex@1355610076:environment:alex-eks-cd"
    error_message = "OIDC trust must bind the immutable repository identity and CD environment."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.release.policy, "secretsmanager:") && !strcontains(aws_iam_role_policy.release.policy, "rds:") && !strcontains(aws_iam_role_policy.release.policy, "lambda:")
    error_message = "Deployment must not access existing application credentials or workers."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.cloudformation.policy, "iam:CreateRole") && !strcontains(aws_iam_role_policy.cloudformation.policy, "iam:PutRolePolicy")
    error_message = "CloudFormation must only pass pre-created roles, not create or expand IAM privileges."
  }
  assert {
    condition     = alltrue([for statement in jsondecode(aws_iam_role_policy.cloudformation.policy).Statement : statement.Resource == "*" ? contains(keys(statement), "Condition") || alltrue([for action in statement.Action : startswith(action, "ec2:Describe")]) : true])
    error_message = "Wildcard infrastructure mutation requires tag conditions."
  }
}
