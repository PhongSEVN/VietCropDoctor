# EKS

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_ca_data" {
  description = "Base64-encoded cluster CA certificate"
  value       = module.eks.cluster_ca_data
  sensitive   = true
}

output "oidc_provider_arn" {
  description = "EKS OIDC provider ARN (for IRSA)"
  value       = module.eks.oidc_provider_arn
}

# ECR

output "ecr_repository_urls" {
  description = "Map of service name → ECR repository URL"
  value       = module.ecr.repository_urls
}

# Networking

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "nat_gateway_ip" {
  description = "Public IP of the NAT Gateway (add to external allowlists)"
  value       = module.vpc.nat_gateway_ip
}

# Data stores

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.elasticache.endpoint
}

output "msk_bootstrap_brokers" {
  description = "MSK SASL/SCRAM bootstrap broker string"
  value       = module.msk.bootstrap_brokers_sasl_scram
  sensitive   = true
}

output "msk_credentials_secret_arn" {
  description = "Secrets Manager ARN for MSK SASL/SCRAM credentials"
  value       = module.msk.credentials_secret_arn
}

# S3

output "s3_buckets" {
  description = "Map of purpose → S3 bucket name"
  value       = module.s3.bucket_ids
}

# IAM (IRSA role ARNs)

output "irsa_vision_ai_role_arn" {
  description = "IRSA role ARN — annotate the vision-ai Kubernetes ServiceAccount with this"
  value       = module.iam.vision_ai_role_arn
}

output "irsa_rag_engine_role_arn" {
  description = "IRSA role ARN — annotate the rag-engine Kubernetes ServiceAccount with this"
  value       = module.iam.rag_engine_role_arn
}

output "irsa_mlops_role_arn" {
  description = "IRSA role ARN — annotate the mlops Kubernetes ServiceAccount with this"
  value       = module.iam.mlops_role_arn
}

output "irsa_analytics_role_arn" {
  description = "IRSA role ARN — annotate the analytics Kubernetes ServiceAccount with this"
  value       = module.iam.analytics_role_arn
}
