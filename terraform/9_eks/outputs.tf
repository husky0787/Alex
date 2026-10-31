output "deployment" {
  value = {
    cluster_name            = aws_eks_cluster.this.name
    namespace               = local.namespace
    region                  = var.region
    repository_url          = aws_ecr_repository.api.repository_url
    api_secret_arn          = aws_secretsmanager_secret.workload["api"].arn
    etl_secret_arn          = aws_secretsmanager_secret.workload["etl"].arn
    aurora_cluster_arn      = var.aurora_cluster_arn
    aurora_admin_secret_arn = var.aurora_admin_secret_arn
    database                = "alex_task09"
    bucket                  = aws_s3_bucket.market.id
    jobs_queue_url          = aws_sqs_queue.jobs.url
    alerts_queue_url        = aws_sqs_queue.alerts.url
    alerts_topic_arn        = aws_sns_topic.alerts.arn
    endpoint                = "https://${aws_cloudfront_distribution.api.domain_name}"
    alarm_name              = aws_cloudwatch_metric_alarm.unhealthy.alarm_name
    expires_at              = var.expires_at
  }
}
