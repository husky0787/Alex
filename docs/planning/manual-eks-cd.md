# Manual EKS delivery extension

The operator selects **Run workflow** on `Release to temporary EKS` on `main`.
Only an exact-commit, successful main-branch `ci.yml` run from this repository is
eligible. The release consumes its verified image archives without rebuilding.

## Acceptance

- No deployment on a push, PR, or failed/in-progress CI run.
- Separate OIDC roles: deployment can publish only its dedicated ECR images and
  operate one CloudFormation stack; CloudFormation can provision the bounded EKS
  environment using pre-created cluster/node roles. No application secrets or
  original Aurora, Lambda, CloudFront, or EC2 modification permissions.
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

Implementation in progress. Do not claim this extension ran on AWS until a real
manual Actions run and an independent absence check are recorded.
