locals {
  buckets = {
    datasets = "${var.name_prefix}-datasets"
    models   = "${var.name_prefix}-models"
    dvc      = "${var.name_prefix}-dvc"
  }
}

# ── Buckets ───────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = var.force_destroy

  tags = merge(var.tags, {
    Name    = each.value
    Purpose = each.key
  })
}

# ── Block all public access ───────────────────────────────────────────────────

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Versioning (all buckets) ──────────────────────────────────────────────────

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ── Server-side encryption ────────────────────────────────────────────────────

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# ── Lifecycle: datasets → Glacier after N days ────────────────────────────────

resource "aws_s3_bucket_lifecycle_configuration" "datasets" {
  bucket = aws_s3_bucket.this["datasets"].id

  rule {
    id     = "transition-to-glacier"
    status = "Enabled"

    filter {}   # applies to all objects

    transition {
      days          = var.dataset_lifecycle_days
      storage_class = "GLACIER"
    }

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}
