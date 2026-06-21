# Core

variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-1"
}

variable "cluster_name" {
  description = "Name prefix shared by all resources"
  type        = string
  default     = "vietcropdoctor"
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

# EKS

variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.29"
}

variable "cpu_node_count" {
  description = "Number of CPU worker nodes (t3.medium default)"
  type        = number
  default     = 2
}

variable "cpu_instance_type" {
  description = "EC2 instance type for the CPU node group"
  type        = string
  default     = "t3.medium"
}

variable "gpu_node_count" {
  description = "Number of GPU worker nodes; set to 0 to disable the GPU node group"
  type        = number
  default     = 1
}

variable "gpu_instance_type" {
  description = "EC2 instance type for the GPU node group"
  type        = string
  default     = "g4dn.xlarge"
}

# RDS

variable "rds_instance_class" {
  description = "RDS PostgreSQL instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "vcdadmin"
}

variable "db_password" {
  description = "RDS master password — provide via TF_VAR_db_password or -var flag; never commit"
  type        = string
  sensitive   = true
}

#  ElastiCache

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

# MSK

variable "kafka_version" {
  description = "Apache Kafka version for MSK"
  type        = string
  default     = "3.5.1"
}

variable "kafka_broker_instance_type" {
  description = "EC2 instance type for MSK brokers"
  type        = string
  default     = "kafka.t3.small"
}

variable "kafka_topics" {
  description = "Kafka topic names (auto-create is disabled; provision via init script)"
  type        = list(string)
  default     = ["disease.detected", "chat.requested", "retrain.requested"]
}

variable "msk_username" {
  description = "SASL/SCRAM username for MSK"
  type        = string
  default     = "vcdkafka"
}

variable "msk_password" {
  description = "SASL/SCRAM password for MSK — provide via TF_VAR_msk_password"
  type        = string
  sensitive   = true
}

#  ECR

variable "ecr_repositories" {
  description = "Container image repositories to create in ECR"
  type        = list(string)
  default     = ["vision-ai", "rag-engine", "analytics", "gateway"]
}
