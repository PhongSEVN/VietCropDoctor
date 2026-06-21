output "datasets_bucket_id" {
  description = "Datasets S3 bucket name"
  value       = aws_s3_bucket.this["datasets"].id
}

output "datasets_bucket_arn" {
  description = "Datasets S3 bucket ARN"
  value       = aws_s3_bucket.this["datasets"].arn
}

output "models_bucket_id" {
  description = "Models S3 bucket name"
  value       = aws_s3_bucket.this["models"].id
}

output "models_bucket_arn" {
  description = "Models S3 bucket ARN"
  value       = aws_s3_bucket.this["models"].arn
}

output "dvc_bucket_id" {
  description = "DVC S3 bucket name"
  value       = aws_s3_bucket.this["dvc"].id
}

output "dvc_bucket_arn" {
  description = "DVC S3 bucket ARN"
  value       = aws_s3_bucket.this["dvc"].arn
}

output "bucket_ids" {
  description = "Map of purpose → bucket name for all three buckets"
  value       = { for k, b in aws_s3_bucket.this : k => b.id }
}
