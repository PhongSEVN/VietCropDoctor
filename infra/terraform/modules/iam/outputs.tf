output "vision_ai_role_arn" {
  description = "IRSA role ARN for the vision-ai service account"
  value       = aws_iam_role.vision_ai.arn
}

output "rag_engine_role_arn" {
  description = "IRSA role ARN for the rag-engine service account"
  value       = aws_iam_role.rag_engine.arn
}

output "mlops_role_arn" {
  description = "IRSA role ARN for the mlops service account"
  value       = aws_iam_role.mlops.arn
}

output "analytics_role_arn" {
  description = "IRSA role ARN for the analytics service account"
  value       = aws_iam_role.analytics.arn
}
