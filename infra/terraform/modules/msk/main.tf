resource "aws_security_group" "msk" {
  name        = "${var.cluster_name}-msk"
  description = "Allow Kafka access from within the VPC"
  vpc_id      = var.vpc_id

  ingress {
    description = "Kafka TLS (SASL/SCRAM)"
    from_port   = 9096
    to_port     = 9096
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "Kafka plaintext (inter-broker)"
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "ZooKeeper"
    from_port   = 2181
    to_port     = 2181
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.cluster_name}-msk-sg" })
}

# ── Broker configuration ──────────────────────────────────────────────────────

resource "aws_msk_configuration" "this" {
  name           = "${var.cluster_name}-config"
  kafka_versions = [var.kafka_version]
  description    = "VietCropDoctor MSK configuration"

  server_properties = <<-PROPS
    auto.create.topics.enable=false
    delete.topic.enable=true
    log.retention.hours=168
    num.partitions=3
    default.replication.factor=2
    min.insync.replicas=1
    compression.type=lz4
  PROPS
}

# ── SASL/SCRAM credentials in Secrets Manager ─────────────────────────────────
# Secret name MUST start with "AmazonMSK_" for MSK to access it.

resource "aws_secretsmanager_secret" "msk_credentials" {
  name                    = "AmazonMSK_${var.cluster_name}_credentials"
  description             = "SASL/SCRAM credentials for MSK cluster ${var.cluster_name}"
  recovery_window_in_days = 7

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "msk_credentials" {
  secret_id = aws_secretsmanager_secret.msk_credentials.id
  secret_string = jsonencode({
    username = var.msk_username
    password = var.msk_password
  })
}

data "aws_kms_alias" "secretsmanager" {
  name = "alias/aws/secretsmanager"
}

resource "aws_msk_cluster" "this" {
  cluster_name           = var.cluster_name
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type  = var.broker_instance_type
    client_subnets = slice(var.subnet_ids, 0, var.broker_count)
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.broker_ebs_volume_size
      }
    }
  }

  client_authentication {
    sasl {
      scram = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = ""   # use AWS-managed key
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  open_monitoring {
    prometheus {
      jmx_exporter  { enabled_in_broker = true }
      node_exporter { enabled_in_broker = true }
    }
  }

  logging {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/aws/msk/${var.cluster_name}"
      }
    }
  }

  tags = var.tags
}

resource "aws_msk_scram_secret_association" "this" {
  cluster_arn     = aws_msk_cluster.this.arn
  secret_arn_list = [aws_secretsmanager_secret.msk_credentials.arn]

  depends_on = [aws_secretsmanager_secret_version.msk_credentials]
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/${var.cluster_name}"
  retention_in_days = 7

  tags = var.tags
}
