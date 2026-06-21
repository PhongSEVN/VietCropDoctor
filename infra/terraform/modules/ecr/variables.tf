variable "repository_names" {
  description = "List of ECR repository names to create"
  type        = list(string)
  default     = ["vision-ai", "rag-engine", "analytics", "gateway"]
}

variable "image_tag_mutability" {
  description = "Image tag mutability: MUTABLE or IMMUTABLE"
  type        = string
  default     = "MUTABLE"
}

variable "scan_on_push" {
  description = "Enable image scanning on push"
  type        = bool
  default     = true
}

variable "lifecycle_keep_count" {
  description = "Number of tagged images to retain per repository"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
