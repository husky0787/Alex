# Manual EKS delivery extension

Tracking: [issue #26](https://github.com/husky0787/Alex/issues/26),
[PR #27](https://github.com/husky0787/Alex/pull/27).

The operator selects **Run workflow** on `Release to temporary EKS` on `main`.
Only an exact-commit, successful main-branch `ci.yml` run from this repository is
eligible. The release consumes its verified image archives without rebuilding.

## Acceptance

- No deployment on a push, PR, or failed/in-progress CI run.
- Separate OIDC roles: deployment can publish only its dedicated ECR images and
  operate one CloudFormation stack; CloudFormation can provision the bounded EKS
  environment using pre-created cluster/node roles. Deployment/CloudFormation
  permissions exclude application secrets and original Aurora/Lambda/CloudFront
  changes; their direct EC2 mutations require owned resource tags. The standard
  node CNI policy is a documented exception: it has account-wide ENI operations.
  IMDSv2 with response hop limit 1 prevents ordinary application Pods from obtaining
  node credentials. This is not a claim of fully VPC-scoped CNI permissions.
- CloudFormation owns a temporary VPC, public subnets, routing, EKS control plane,
  managed two-node group and EKS access entry. Kubernetes endpoint permits only the
  current runner IPv4 /32. No SSH, NAT gateway, load balancer or persistent volume.
- Deploy the tested baseline digest, then the candidate digest, run authenticated
  API ownership/error checks, and exercise an unavailable digest with recovery to
  the exact candidate. Record Git SHA, CI run, images, results and cleanup.
- PostgreSQL, JWT signer and AWS transport **fixtures** run in the isolated
  cluster. This verifies real EKS delivery; it does not repeat Task 9's Aurora/
  ingestion integrations or Task 11's real Clerk/paid-agent acceptance. No frontend
  production cutover or data migration occurs.
- Always attempt cleanup after deployment. An independent completion/expiry
  workflow recovers interrupted runs from durable CloudFormation ownership tags.
  All lifecycle jobs share concurrency. Failed cleanup remains an explicit failure.
- Public artifacts contain summaries only. No kubeconfig, state, JWT signing key,
  credentials, resource configuration or account billing details are uploaded.
- Initial bootstrap needs an operator-reviewed IAM plan and current credit/cost
  check. Bootstrap IAM and an empty ECR repository remain for later releases.
  Runtime stack and release images are deleted; tags/timeouts are not hard cost caps.

## Verification status

Implementation and local review are complete; follow PR #27 for live CI state.
Do not claim this extension ran on AWS until a real manual Actions run and an
independent absence check are recorded.
