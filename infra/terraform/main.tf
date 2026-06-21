terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Bootstrap this backend manually before running terraform init.
  # See infra/terraform/README-bootstrap.md for instructions.
  backend "s3" {
    bucket         = "vietcropdoctor-terraform-state"
    key            = "vietcropdoctor/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "vietcropdoctor-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "vietcropdoctor"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  common_tags = {
    Project     = "vietcropdoctor"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── VPC ───────────────────────────────────────────────────────────────────────

module "vpc" {
  source = "./modules/vpc"

  name         = var.cluster_name
  vpc_cidr     = "10.0.0.0/16"
  cluster_name = var.cluster_name
  tags         = local.common_tags
}

# ── EKS ───────────────────────────────────────────────────────────────────────

module "eks" {
  source = "./modules/eks"

  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.vpc.private_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  security_group_ids = [module.vpc.intra_cluster_sg_id]
  cpu_node_count     = var.cpu_node_count
  cpu_instance_type  = var.cpu_instance_type
  gpu_node_count     = var.gpu_node_count
  gpu_instance_type  = var.gpu_instance_type
  tags               = local.common_tags
}

# ── RDS ───────────────────────────────────────────────────────────────────────

module "rds" {
  source = "./modules/rds"

  name                = "${var.cluster_name}-db"
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  instance_class      = var.rds_instance_class
  db_name             = "vietcropdoctor"
  db_username         = var.db_username
  db_password         = var.db_password
  multi_az            = var.environment == "prod"
  deletion_protection = var.environment == "prod"
  tags                = local.common_tags
}

# ── ElastiCache (Redis) ───────────────────────────────────────────────────────

module "elasticache" {
  source = "./modules/elasticache"

  name                = "${var.cluster_name}-redis"
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  node_type           = var.redis_node_type
  tags                = local.common_tags
}

# ── MSK (Kafka) ───────────────────────────────────────────────────────────────

module "msk" {
  source = "./modules/msk"

  cluster_name        = "${var.cluster_name}-kafka"
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  kafka_version       = var.kafka_version
  broker_instance_type = var.kafka_broker_instance_type
  kafka_topics        = var.kafka_topics
  msk_username        = var.msk_username
  msk_password        = var.msk_password
  tags                = local.common_tags
}

# ── ECR ───────────────────────────────────────────────────────────────────────

module "ecr" {
  source = "./modules/ecr"

  repository_names = var.ecr_repositories
  tags             = local.common_tags
}

# ── S3 ────────────────────────────────────────────────────────────────────────

module "s3" {
  source = "./modules/s3"

  name_prefix   = var.cluster_name
  environment   = var.environment
  force_destroy = var.environment != "prod"
  tags          = local.common_tags
}

# ── IAM (IRSA roles for application service accounts) ────────────────────────

module "iam" {
  source = "./modules/iam"

  cluster_name           = var.cluster_name
  oidc_provider_arn      = module.eks.oidc_provider_arn
  oidc_issuer_url        = module.eks.oidc_issuer_url
  s3_datasets_bucket_arn = module.s3.datasets_bucket_arn
  s3_models_bucket_arn   = module.s3.models_bucket_arn
  s3_dvc_bucket_arn      = module.s3.dvc_bucket_arn
  msk_cluster_arn        = module.msk.cluster_arn
  tags                   = local.common_tags
}
