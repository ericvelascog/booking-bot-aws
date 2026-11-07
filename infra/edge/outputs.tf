output "app_url" {
  description = "URL pública y permanente del bot, con HTTPS"
  value       = "https://${aws_cloudfront_distribution.app.domain_name}"
}
