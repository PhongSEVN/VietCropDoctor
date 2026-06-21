variable "cluster_name" {
  description = "MSK cluster name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for MSK brokers (one per broker)"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to connect to MSK"
  type        = list(string)
}

variable "kafka_version" {
  description = "Apache Kafka version"
  type        = string
  default     = "3.5.1"
}

variable "broker_instance_type" {
  description = "EC2 instance type for MSK brokers"
  type        = string
  default     = "kafka.t3.small"
}

variable "broker_count" {
  description = "Number of broker nodes (must equal number of AZs)"
  type        = number
  default     = 2
}

variable "broker_ebs_volume_size" {
  description = "EBS volume size per broker in GB"
  type        = number
  default     = 100
}

variable "msk_username" {
  description = "SASL/SCRAM username stored in Secrets Manager"
  type        = string
  default     = "vcdkafka"
}

variable "msk_password" {
  description = "SASL/SCRAM password stored in Secrets Manager"
  type        = string
  sensitive   = true
}

variable "kafka_topics" {
  description = "Topic names to document (MSK does not create topics; use init scripts)"
  type        = list(string)
  default     = ["disease.detected", "chat.requested", "retrain.requested"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
