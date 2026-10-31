# Temporary bootstrap identity. Its ServiceAccount/Job is removed after setup.
resource "aws_iam_role" "bootstrap" {
  name = "${local.name}-bootstrap"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "pods.eks.amazonaws.com" }, Action = ["sts:AssumeRole", "sts:TagSession"],
    Condition = { StringEquals = { "aws:RequestTag/kubernetes-namespace" = local.namespace,
    "aws:RequestTag/kubernetes-service-account" = "bootstrap" } }
  }] })
  tags = local.tags
}
resource "aws_iam_role_policy" "bootstrap" {
  role = aws_iam_role.bootstrap.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [var.aurora_admin_secret_arn,
    aws_secretsmanager_secret.workload["api"].arn, aws_secretsmanager_secret.workload["etl"].arn]
  }] })
}
resource "aws_eks_pod_identity_association" "bootstrap" {
  cluster_name    = aws_eks_cluster.this.name
  namespace       = local.namespace
  service_account = "bootstrap"
  role_arn        = aws_iam_role.bootstrap.arn
  depends_on      = [aws_eks_addon.this]
}
