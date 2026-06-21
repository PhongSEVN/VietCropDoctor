variable "cluster_name" {
  description = "EKS cluster name — used as prefix for IAM role names"
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS OIDC identity provider (for IRSA trust policies)"
  type        = string
}

variable "oidc_issuer_url" {
  description = "Issuer URL of the EKS OIDC provider (without https://)"
  type        = string
}

variable "s3_datasets_bucket_arn" {
  description = "ARN of the datasets S3 bucket"
  type        = string
}

variable "s3_models_bucket_arn" {
  description = "ARN of the models S3 bucket"
  type        = string
}

variable "s3_dvc_bucket_arn" {
  description = "ARN of the DVC S3 bucket"
  type        = string
}

variable "msk_cluster_arn" {
  description = "ARN of the MSK cluster"
  type        = string
}

variable "service_accounts" {
  description = "Map of service-account key → {namespace, name} used to build IRSA trust policies"
  type = map(object({
    namespace = string
    name      = string
  }))
  default = {
    "vision-ai"  = { namespace = "vietcropdoctor", name = "vision-ai" }
    "rag-engine" = { namespace = "vietcropdoctor", name = "rag-engine" }
    "mlops"      = { namespace = "vietcropdoctor", name = "mlops" }
    "analytics"  = { namespace = "vietcropdoctor", name = "analytics" }
  }
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
