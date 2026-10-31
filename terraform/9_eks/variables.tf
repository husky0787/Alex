variable "region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = var.region == "us-east-1"
    error_message = "This bounded acceptance is costed only for us-east-1."
  }
}
variable "vpc_id" { type = string }
variable "public_subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.public_subnet_ids) == 2
    error_message = "Supply two existing public subnets in different supported AZs."
  }
}
variable "private_subnets" {
  type = map(object({ az = string, cidr = string }))
  validation {
    condition     = length(var.private_subnets) == 2
    error_message = "Supply two unused CIDRs in the existing VPC for private ALB subnets."
  }
}
variable "operator_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.operator_cidrs) > 0 && alltrue([for c in var.operator_cidrs : can(cidrhost(c, 0)) && endswith(c, "/32")])
    error_message = "Restrict the public Kubernetes endpoint to explicit operator IPv4 /32 addresses."
  }
}
variable "operator_user_name" { type = string }
variable "operator_principal_arn" { type = string }
variable "aurora_cluster_arn" { type = string }
variable "aurora_admin_secret_arn" { type = string }
variable "aurora_security_group_id" { type = string }
variable "expires_at" {
  type = string
  validation {
    condition     = can(formatdate("YYYY-MM-DD", var.expires_at))
    error_message = "Supply an explicit UTC RFC3339 cleanup deadline; tags do not enforce shutdown."
  }
}
variable "estimated_total_usd" {
  type = number
  validation {
    condition     = var.estimated_total_usd > 0 && var.estimated_total_usd <= 80
    error_message = "Reviewed total estimate must stay within the USD80 project planning allocation."
  }
}
variable "reporter_zip" {
  type = string
  validation {
    condition     = fileexists(var.reporter_zip)
    error_message = "Supply the locally verified, snapshot-aware Reporter ZIP, including the SQS adapter."
  }
}
