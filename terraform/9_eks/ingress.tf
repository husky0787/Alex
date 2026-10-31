resource "aws_security_group" "origin" {
  name   = "${local.name}-origin"
  vpc_id = var.vpc_id
  tags   = local.tags
}
resource "aws_vpc_security_group_ingress_rule" "cloudfront" {
  security_group_id = aws_security_group.origin.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}
resource "aws_vpc_security_group_egress_rule" "origin" {
  security_group_id            = aws_security_group.origin.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}
resource "aws_vpc_security_group_ingress_rule" "origin_to_nodes" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.origin.id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}
resource "aws_lb" "api" {
  name               = local.name
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.origin.id]
  subnets            = [for s in aws_subnet.origin : s.id]
  tags               = local.tags
}
resource "aws_lb_target_group" "api" {
  name                 = local.name
  vpc_id               = var.vpc_id
  port                 = 30080
  protocol             = "HTTP"
  target_type          = "instance"
  deregistration_delay = 15
  health_check {
    path                = "/ready"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 15
    timeout             = 5
  }
  tags = local.tags
}
resource "aws_autoscaling_attachment" "api" {
  autoscaling_group_name = aws_eks_node_group.this.resources[0].autoscaling_groups[0].name
  lb_target_group_arn    = aws_lb_target_group.api.arn
}
resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
resource "aws_cloudfront_vpc_origin" "api" {
  vpc_origin_endpoint_config {
    name                   = local.name
    arn                    = aws_lb.api.arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"
    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
  depends_on = [aws_lb_listener.api]
  tags       = local.tags
}
resource "aws_cloudfront_distribution" "api" {
  enabled         = true
  price_class     = "PriceClass_100"
  is_ipv6_enabled = true
  comment         = "Isolated Alex task09 API; original distribution remains untouched"
  origin {
    domain_name = aws_lb.api.dns_name
    origin_id   = "api"
    vpc_origin_config { vpc_origin_id = aws_cloudfront_vpc_origin.api.id }
  }
  default_cache_behavior {
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
  tags = local.tags
}
resource "aws_cloudwatch_metric_alarm" "unhealthy" {
  alarm_name          = "${local.name}-unhealthy-api"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 2
  period              = 60
  statistic           = "Minimum"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = local.tags
}
resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Principal = { Service = "cloudwatch.amazonaws.com" }, Action = "sns:Publish",
    Resource = aws_sns_topic.alerts.arn,
    Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
    ArnEquals = { "aws:SourceArn" = aws_cloudwatch_metric_alarm.unhealthy.arn } }
  }] })
}
