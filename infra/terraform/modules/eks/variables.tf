variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

variable "subnet_ids" {
  description = "Subnet IDs for the EKS control plane"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for worker nodes"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Additional security group IDs for the cluster"
  type        = list(string)
  default     = []
}

variable "cpu_node_count" {
  description = "Desired number of CPU nodes"
  type        = number
  default     = 2
}

variable "cpu_instance_type" {
  description = "EC2 instance type for the CPU node group"
  type        = string
  default     = "t3.medium"
}

variable "gpu_node_count" {
  description = "Desired number of GPU nodes (0 disables the GPU node group)"
  type        = number
  default     = 1
}

variable "gpu_instance_type" {
  description = "EC2 instance type for the GPU node group"
  type        = string
  default     = "g4dn.xlarge"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
