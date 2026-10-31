# Manual release to temporary EKS

After one-time bootstrap, open **Actions → Release to temporary EKS → Run workflow**
on **main**. The workflow finds successful CI for exactly that revision, downloads
its tested images, creates real EKS, verifies release/rollback, saves safe evidence,
and deletes the temporary stack and this run's image tags. Pushing/merging code
only runs CI. Expired image artifacts require a new complete CI run first.

This is a disposable **API delivery acceptance environment**. PostgreSQL, JWT and
AWS transport fixtures are isolated in EKS. It does not deploy the frontend, move
production traffic, access original Aurora/agent secrets, run paid agents, or
perform schema migrations. Real application integrations have separate Task 9/11
evidence; do not combine those claims into a full production CD run.

## One-time bootstrap

1. Verify the current AWS account, credits/expiry/service eligibility and the cost
   window below. Preserve the existing default AWS CLI identity. Use the operator's
   short-lived credentials to plan `terraform/12_cd`; never save static keys in
   GitHub. Reuse the existing GitHub OIDC provider ARN. Existing EKS and managed-node
   service-linked roles from Task 9 are prerequisites; verify they exist.
2. Run `terraform init`, `terraform test`, and review `terraform plan` for only this
   module, then apply the reviewed plan. Keep this module's state in private backup.
   It creates IAM roles/policies and one empty ECR repository, not a running cluster.
3. Create GitHub environment `alex-eks-cd`, restrict deployment branches to `main`,
   and copy `terraform output -json github_variables` values into that environment.
   Confirm the actual immutable repository OIDC subject against GitHub's API. A fork
   needs its own identity in the Terraform trust policy.
4. Set repository variable `ALEX_CD_RECOVERY_ENABLED=true`. Ensure both workflows
   are on the default branch before enabling releases. Recovery must run without
   a human approval wait so an interrupted cluster is not left billing.
5. After current billing review, set environment variable `ALEX_CD_APPROVED_UNTIL`
   to a UTC ISO timestamp between two and 24 hours from the release start. This is
   an operator-reviewed window, **not an AWS-enforced spending limit**. Keep it unset
   when not actively demonstrating releases. Recovery does not require this window.

The deploy role only publishes/deletes images in `alex-cd-api`, operates stack
`alex-cd-window`, passes its dedicated CloudFormation role and describes its EKS
cluster. CloudFormation may create tagged network resources and the named EKS
cluster, and pass the fixed node/cluster roles. It cannot create arbitrary IAM
roles. Node roles use standard EKS worker/CNI/ECR policies. These infrastructure
permissions are broader than namespace-only app deployment; review them as such.
In particular, the standard CNI policy permits account-wide ENI operations. The
worker launch template requires IMDSv2 and hop limit 1, and application Pods use
neither host networking nor service-account tokens, to prevent ordinary Pods from
obtaining node credentials. A node/privileged CNI compromise still has this broader
permission; this setup does not claim VPC-scoped CNI least privilege.

## Release evidence and failure behavior

- The gate checks repository, main branch, event, workflow path, full Git SHA,
  overall success, each required job and non-expired artifact identity. Docker
  archive checksums, image IDs and source labels are checked before provisioning.
- Kubernetes API allows only the runner IPv4 /32; nodes also use the private
  endpoint. Workloads expose only ClusterIP; the runner uses a reconnecting
  loopback port-forward. No load balancer, NAT gateway or persistent volumes exist.
- Healthy candidate, authenticated cross-user/error smoke, deliberately missing
  digest, recovered candidate and unchanged fixture database schema are checked.
  The failed rollout itself remains nonzero even when rollback succeeds. Only the
  explicitly expected fault drill can treat that result as successful acceptance.
- `eks-cd-acceptance` and `eks-cd-cleanup` artifacts contain public JSON summaries
  only, retained 14 days. The GitHub run links the exact source CI run. Private
  kubeconfig, fixture passwords, signer and raw diagnostics stay on the runner.
- Cleanup is a separate job with fresh OIDC credentials. A `workflow_run` recovery
  handles canceled/failed runs, and an hourly schedule handles expired ownership.
  All three paths serialize via one concurrency group and refuse foreign ownership.
  CloudFormation state survives runner loss. EKS absence is checked independently.
- GitHub schedules may be delayed/disabled and cloud deletion can fail. This is
  automatic cleanup with recovery, not a guaranteed deadline. Inspect any failed
  cleanup immediately. Do not disable recovery while a stack remains.

## Recovery

First inspect **Recover temporary EKS** and CloudFormation events for the exact
`alex-cd-window` stack. A manual recovery workflow cleans only an expired stack.
An authorized operator can recover a known completed run from a trusted checkout:

```text
uv run --no-project deploy/cd/lifecycle.py recover --completed-run GITHUB_RUN_ID --completed-attempt RUN_ATTEMPT
```

Set `ALEX_CD_CF_ROLE_ARN` and `ALEX_CD_REPOSITORY` from private bootstrap output,
and use the scoped role credentials. Do not run recovery concurrently with Actions.
Do not manually erase ownership tags or force-delete original application data.
If the stack is absent but the named EKS cluster exists, the helper reports an
orphan and refuses to delete without ownership evidence. Inspect it manually.
ECR has a one-day lifecycle fallback for orphan image artifacts; this is not instant.

Bootstrap IAM/OIDC references and an empty ECR repository remain reusable. Removing
bootstrap requires a separate reviewed Terraform destroy after all runtime resources
are absent. The shared existing OIDC provider is never owned by this module.

## Cost window

Budget one short run with a two-hour resource expiry marker and a three-hour cost
scenario including cleanup/recovery buffer. Standard-support EKS is US$0.10/hour;
two t3.medium nodes, 40 GiB EBS, two public IPv4s, registry storage, transfer and
possible burst CPU charges must also be counted. There is no NAT/LB or paid-model
usage. Refresh regional EC2/EBS prices and existing account consumption before
first execution; use a US$5 investigation threshold, not a spending guarantee.
The 2026-10-31 regional API check priced t3.medium at US$0.0416/hour. A three-hour
scenario is about US$0.60 for control plane, nodes, public IPv4 and 40 GiB gp3;
allow US$2 total for registry, transfer and burst/buffer costs. Existing account
services continue billing separately. A stuck environment or repeated runs can
exceed this scenario; the two-hour expiry tag does not stop billing by itself.

Sources: [EKS pricing](https://aws.amazon.com/eks/pricing/),
[public IPv4 pricing](https://aws.amazon.com/vpc/pricing/),
[EKS deletion](https://docs.aws.amazon.com/eks/latest/userguide/delete-cluster.html),
[GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

## Local checks

```text
uv run --no-project -m unittest discover -s deploy/cd -p 'test_*.py' -v
uv run --no-project deploy/ci/test_release.py
terraform -chdir=terraform/12_cd init
terraform -chdir=terraform/12_cd test
```

Cloud acceptance is pending until a real Actions run and independent cleanup check
are linked in the verification record. Unit tests and template validation alone
do not establish that live IAM, EKS provisioning or networking works.
