# Task 10 CI/CD acceptance

Implementation and acceptance are in progress on 2026-10-31. Live results will be recorded before completion. The target for automated delivery is a disposable Kubernetes cluster on a standard GitHub-hosted runner; EKS integration was separately validated in Task 9. This task does not claim an automated EKS rollout.

## Budget and ownership preflight

AWS returned US$111.45 remaining credit. Cost Explorer returned October gross usage excluding credits/refunds of US$5.3664170124. Billing lags, so this is neither a final Task 9 bill nor a Task 10 charge. Previously confirmed expiry (2026-11-30) and ECR eligibility still apply.

The reviewed plan adds five resources and changes/deletes none: the absent GitHub OIDC provider, one release role, one scoped inline policy, one ECR repository and its lifecycle rule. No EKS/EC2/ALB/NAT/model resources are added. GitHub public standard runners execute the Kubernetes work. AWS pricing lists ECR storage at US$0.10/GB-month and example outbound transfer at US$0.09/GB. For this short window, allow 1 GB-month storage (US$0.10), up to 5 GB transfer (US$0.45), and US$0.45 retry/request margin: **US$1 incremental allowance**, not a measured bill or enforced cap. Keep the entire account window within the previous conservative US$20 allocation, including the US$5.37 existing baseline and remaining-resource/lag contingency. Inspect retained images and disable release after acceptance; no extra cash spending is authorized.

Sources checked 2026-10-31: [ECR pricing](https://aws.amazon.com/ecr/pricing/) and [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Findings during verification

- The first GitHub push was rejected because the existing OAuth token lacked `workflow` scope. The user completed GitHub's device authorization; no token was copied into the repository.
- First hosted backend run exposed a role-test fixture using the admin password when connecting as the API/ETL roles. Local trust authentication had masked it. The fixture now explicitly supplies each role's real test password; CI retains password authentication.
- Review found that kubectl errors lost diagnostics and concurrent deployments could be misreported as our success. Private diagnostics now preserve original output; public evidence records safe reasons. Both successful rollout and successful rollback verify the final expected template, with regression cases for concurrent replacements.

## Reproduction

See [delivery runbook](../../deploy/ci/README.md). Private billing responses, Terraform state/plan and intermediate diagnostics remain under ignored local paths. GitHub test/release run links and final cleanup evidence will be added after execution.
