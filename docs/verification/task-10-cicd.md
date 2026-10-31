# Task 10 CI/CD acceptance

Executed on 2026-10-31. [GitHub Actions run 41194304688](https://github.com/husky0787/Alex/actions/runs/41194304688) passed all four jobs, including real OIDC/ECR publication and Kubernetes release/rollback, for commit `28188e5208e5067c1fbb6c55e1fbdcecbe102dd9`. The automated deployment target is a disposable Kubernetes cluster on a standard GitHub-hosted runner; EKS integration was separately validated in Task 9. This task does not claim an automated EKS rollout.

## Observed results

| Boundary | Observed evidence |
| --- | --- |
| Test gates | 62 PostgreSQL market tests, 13 API contracts, 11 cloud-helper tests, 10 release tests and 10 frontend tests passed in GitHub Actions; lint, TypeScript and production static build passed. Two Terraform mock boundary tests passed locally. |
| Failure gating | Earlier runs failed on an incorrect database-test password, checksum filename parsing and public-registry rate limiting; dependent build/release jobs were skipped. No cloud publish bypass was used. |
| Immutable artifacts | Source commit and parent commit were built once, labelled, archived with SHA256 checksums, reloaded without rebuilding and checked by image ID/revision. ECR and local registry returned the same digests. |
| Short-lived AWS identity | The credentials action assumed `alex-ci-release` via OIDC for a requested 1,800-second session. Actual application-secret and other-repository reads both returned `AccessDeniedException`. |
| Healthy ECR release | Baseline → candidate digest rollout succeeded during **10:55:28–10:55:38 UTC**, followed by authenticated HTTP smoke. |
| Failed ECR release | An intentionally absent digest hit the deployment progress deadline; the release tool returned failure, restored the exact candidate template/digest and passed HTTP readiness during **10:55:40–10:56:41 UTC**. Authenticated smoke then passed again. |
| Database | No migration was executed; the same PostgreSQL fixture/schema remained in place. Before/after schema signatures matched. Future schema changes must follow the expand/contract policy in the runbook. |
| Cleanup | Runner logs confirm cluster deletion at **10:56:46 UTC** and the successful job completed its registry/logout cleanup. Private fixture credentials and kubeconfig were not uploaded. |

Baseline digest: `sha256:1bf1204b337c1cf04a703e2bda4271af2879ba0d633efaf54fea9b48d0f77ba3`.

Candidate digest: `sha256:2923ea68059dae1e56b57410ae513f573956f993e435ee32213ea54a780d654b`.

Both image entries reported 101,299,445 bytes. This is image metadata, not a measured bill; layers may be shared. The bad-release harness expects a nonzero release command exit, while the overall verification job passes only after confirming rollback. Ordinary failed releases still return failure to their caller.

## Budget and ownership preflight

AWS returned US$111.45 remaining credit. Cost Explorer returned October gross usage excluding credits/refunds of US$5.3664170124. Billing lags, so this is neither a final Task 9 bill nor a Task 10 charge. Previously confirmed expiry (2026-11-30) and ECR eligibility still apply.

The reviewed plan adds five resources and changes/deletes none: the absent GitHub OIDC provider, one release role, one scoped inline policy, one ECR repository and its lifecycle rule. No EKS/EC2/ALB/NAT/model resources are added. GitHub public standard runners execute the Kubernetes work. AWS pricing lists ECR storage at US$0.10/GB-month and example outbound transfer at US$0.09/GB. For this short window, allow 1 GB-month storage (US$0.10), up to 5 GB transfer (US$0.45), and US$0.45 retry/request margin: **US$1 incremental allowance**, not a measured bill or enforced cap. Keep the entire account window within the previous conservative US$20 allocation, including the US$5.37 existing baseline and remaining-resource/lag contingency. Inspect retained images and disable release after acceptance; no extra cash spending is authorized.

Sources checked 2026-10-31: [ECR pricing](https://aws.amazon.com/ecr/pricing/) and [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Findings during verification

- The first GitHub push was rejected because the existing OAuth token lacked `workflow` scope. The user completed GitHub's device authorization; no token was copied into the repository.
- First hosted backend run exposed a role-test fixture using the admin password when connecting as the API/ETL roles. Local trust authentication had masked it. The fixture now explicitly supplies each role's real test password; CI retains password authentication.
- Review found that kubectl errors lost diagnostics and concurrent deployments could be misreported as our success. Private diagnostics now preserve original output; public evidence records safe reasons. Both successful rollout and successful rollback verify the final expected template, with regression cases for concurrent replacements.
- One earlier rollout observed connection resets despite Kubernetes readiness. HTTP checks now allow ten bounded read-only attempts and retain each error; persistent failure remains failure. The successful run needed only the first attempt. The exact cause of the earlier reset was not established.
- ECR Public returned `429 Data limit exceeded`; the Docker official registry was verified to serve the exact same pinned Python manifest digest, then used by CI. No floating base-image fallback was added.
- GitHub's repository OIDC API reported immutable subject IDs. The exact owner/repository/environment subject was applied to the owned role before the successful OIDC run; legacy name-only examples were not accepted as evidence.

## Retained resources and limitations

At **10:59:54 UTC**, an ownership-tag check and manifest-hash verification preceded deletion of the two task ECR images. The repository is empty. The exact-commit release variable and temporary feature-branch environment permission were removed. The five reusable IAM/OIDC/ECR configuration resources remain in their own Terraform state; no task compute remains running. The 597,054,786-byte temporary Actions image archive was removed after verification; small public JSON evidence remains. Later releases retain compressed archives only for an explicitly selected release commit.

The final workflow narrows push execution to main, also supports manual dispatch, and checks PR updates. The first live controlled release used the explicitly allowed implementation branch; the final main-only environment rule intentionally removes that temporary exception. These trigger/retention refinements do not represent a second AWS release.

The Kubernetes database, JWT issuer and AWS transport are fixtures. This verifies delivery and authorization behavior, not a new real Clerk login or a new EKS/Aurora/agent integration. Actual AWS billing remains unreconciled. Task 6's billing item stays open; account-level totals cannot close it.

## Reproduction

See [delivery runbook](../../deploy/ci/README.md). Private billing responses, Terraform state/plan, full image manifests and intermediate diagnostics remain under ignored local paths. Rebuild and revalidate images for a later release; the acceptance digests above are historical evidence, not promises that the cleaned repositories still serve them.
