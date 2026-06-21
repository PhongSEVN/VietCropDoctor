output "cluster_arn" {
  description = "MSK cluster ARN"
  value       = aws_msk_cluster.this.arn
}

output "bootstrap_brokers_sasl_scram" {
  description = "SASL/SCRAM bootstrap broker string (TLS)"
  value       = aws_msk_cluster.this.bootstrap_brokers_sasl_scram
  sensitive   = true
}

output "zookeeper_connect_string" {
  description = "ZooKeeper connection string"
  value       = aws_msk_cluster.this.zookeeper_connect_string
}

output "credentials_secret_arn" {
  description = "Secrets Manager ARN containing SASL/SCRAM credentials"
  value       = aws_secretsmanager_secret.msk_credentials.arn
}

output "security_group_id" {
  description = "ID of the MSK security group"
  value       = aws_security_group.msk.id
}
