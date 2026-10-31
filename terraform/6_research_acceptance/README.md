# Isolated Reporter acceptance function

This directory prepares task 6 cloud acceptance without replacing `alex-reporter`, changing its role or attaching to the live queue/API. The user authorized AWS acceptance on 2026-10-31. See the verification record for actual deployment results.

It owns exactly four resources: `alex-reporter-acceptance`, its dedicated IAM role/inline policy and seven-day log group. It uses existing Aurora, database secret, research index, embedding endpoint and Bedrock inference profile; it does not own or destroy them. IAM scopes access to those supplied resources. **Database access is cluster-scoped, not row-scoped**: only invoke it with a dedicated test job/user, never an existing customer's job. There is no scheduler, public URL or event source. Reserved concurrency defaults to one; check account concurrency quota before deployment.

Use Terraform 1.7+ and run these commands from this directory:

```text
terraform init
terraform fmt -check
terraform validate
terraform test
```

The tests use a mocked AWS provider and a harmless local file as a hash fixture. They do not upload code, contact AWS or validate the real ZIP. Provider installation needs network access on the first `init`.

Before any later deployment:

1. Copy the real Reporter ZIP from the builder to the deployment machine, check SHA256 against the [verification record](../../docs/verification/task-06-research-chain.md), and set its absolute `reporter_zip_path` in ignored `terraform.tfvars`.
2. Supply `aurora_cluster_arn`, `aurora_secret_arn`, `vector_bucket_name`, `vector_index_arn`, `sagemaker_endpoint_arn` from verified outputs. Names and ARNs must reference the same resources. Keep the database/endpoint/index defaults only when they match those outputs. If the secret uses a customer-managed KMS key, also set `secret_kms_key_arn`.
3. Use `aws bedrock get-inference-profile --inference-profile-identifier us.amazon.nova-pro-v1:0 --region us-east-1` to obtain its profile ARN and every `models[].modelArn`; supply them in `bedrock_model_arns`. A provider mock does not establish IAM or model availability.
4. Check that the acceptance function, role and log group names are unused. Run `terraform plan -out=acceptance.tfplan`; expect only four creates, zero updates/deletes. Keep the plan/state private. Check the current budget before apply. If the account cannot reserve concurrency (the acceptance account currently has only 10 total), set `reserved_concurrency = -1` and invoke synchronously one job at a time. This uses the shared pool and is **not** a function-level concurrency cap. Otherwise keep the default reservation of one.
5. After deployment, invoke only this function synchronously with the dedicated job's `job_id`. The job must contain a real verified task 5 price snapshot. Check the Lambda FunctionError and payload as well as the saved report; a successful Invoke HTTP response alone does not prove success.
6. For unavailable-research testing, temporarily set this module's endpoint name to a nonexistent acceptance endpoint, review/apply that isolated change, and invoke a separate dedicated job. Verify the saved explicit-unavailable report, then restore the real endpoint. Do not modify the live workers.
7. When the authorized acceptance window finishes, review a destroy plan from **this directory only**. It must remove only the four owned resources. Deleting the log group removes its logs, so retain redacted/private evidence first. Test job rows are not managed by Terraform and require separate, explicitly scoped cleanup.

The [cloud window](../../docs/verification/task-06-cloud-window.md) defines the rest of the end-to-end acceptance and cost reconciliation. Passing these offline tests does not complete issue #8.
