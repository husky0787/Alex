variable "aws_region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = var.aws_region == "us-east-1"
    error_message = "This acceptance configuration and cost estimate are for us-east-1."
  }
}

variable "reporter_zip_path" {
  type        = string
  description = "Absolute path to the verified Linux Reporter ZIP; never use a dummy artifact for apply."
}

variable "reserved_concurrency" {
  type        = number
  default     = 1
  description = "Use 1 where reservation is supported; -1 uses the shared pool for low-quota accounts and requires serial manual invocation."
  validation {
    condition     = contains([-1, 1], var.reserved_concurrency)
    error_message = "Choose 1 (reserved) or -1 (shared pool with serial manual acceptance)."
  }
}

variable "aurora_cluster_arn" {
  type = string
}

variable "aurora_secret_arn" {
  type = string
}

variable "aurora_database" {
  type    = string
  default = "alex"
}

variable "secret_kms_key_arn" {
  type        = string
  default     = null
  description = "Customer-managed key for the database secret, if any. Leave null for the AWS-managed key."
}

variable "vector_bucket_name" {
  type = string
}

variable "vector_index_name" {
  type    = string
  default = "financial-research"
}

variable "vector_index_arn" {
  type = string
}

variable "sagemaker_endpoint_name" {
  type    = string
  default = "alex-embedding-endpoint"
}

variable "sagemaker_endpoint_arn" {
  type = string
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "Exact inference-profile ARN and all destination foundation-model ARNs returned by GetInferenceProfile for us.amazon.nova-pro-v1:0."
  validation {
    condition     = length(var.bedrock_model_arns) >= 2 && alltrue([for arn in var.bedrock_model_arns : startswith(arn, "arn:aws:bedrock:") && !strcontains(arn, "*")])
    error_message = "Supply explicit Bedrock profile and destination model ARNs without wildcards."
  }
}
