variable "name_prefix" {
  description = "Prefix for all bucket names (e.g. 'vietcropdoctor')"
  type        = string
}

variable "environment" {
  description = "Environment suffix appended to bucket names in non-prod"
  type        = string
  default     = "prod"
}

variable "dataset_lifecycle_days" {
  description = "Days before transitioning dataset objects to Glacier"
  type        = number
  default     = 90
}

variable "force_destroy" {
  description = "Allow Terraform to destroy non-empty buckets (set true for dev only)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
