output "app_url" {
  value = "http://${aws_lb.main.dns_name}"
}

output "ecr_api" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_processor" {
  value = aws_ecr_repository.processor.repository_url
}

output "ecr_frontend" {
  value = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "s3_bucket" {
  value = aws_s3_bucket.data.bucket
}

output "processor_task_definition" {
  description = "Use this in CI/CD to run the processor as a one-off task"
  value       = aws_ecs_task_definition.processor.family
}