locals {
  oidc_issuer = var.oidc_issuer_url
}

# ── Reusable helper: IRSA trust policy ───────────────────────────────────────

data "aws_iam_policy_document" "irsa_trust" {
  for_each = var.service_accounts

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer}:sub"
      values   = ["system:serviceaccount:${each.value.namespace}:${each.value.name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# ── vision-ai: read models bucket ────────────────────────────────────────────

resource "aws_iam_role" "vision_ai" {
  name               = "${var.cluster_name}-vision-ai"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust["vision-ai"].json
  tags               = var.tags
}

data "aws_iam_policy_document" "vision_ai_s3" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.s3_models_bucket_arn, "${var.s3_models_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "vision_ai_s3" {
  name   = "s3-models-read"
  role   = aws_iam_role.vision_ai.id
  policy = data.aws_iam_policy_document.vision_ai_s3.json
}

# ── rag-engine: read datasets bucket ─────────────────────────────────────────

resource "aws_iam_role" "rag_engine" {
  name               = "${var.cluster_name}-rag-engine"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust["rag-engine"].json
  tags               = var.tags
}

data "aws_iam_policy_document" "rag_engine_s3" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.s3_datasets_bucket_arn, "${var.s3_datasets_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "rag_engine_s3" {
  name   = "s3-datasets-read"
  role   = aws_iam_role.rag_engine.id
  policy = data.aws_iam_policy_document.rag_engine_s3.json
}

# ── mlops: full S3 access + MSK describe ─────────────────────────────────────

resource "aws_iam_role" "mlops" {
  name               = "${var.cluster_name}-mlops"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust["mlops"].json
  tags               = var.tags
}

data "aws_iam_policy_document" "mlops_s3" {
  statement {
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [
      var.s3_datasets_bucket_arn, "${var.s3_datasets_bucket_arn}/*",
      var.s3_models_bucket_arn,   "${var.s3_models_bucket_arn}/*",
      var.s3_dvc_bucket_arn,      "${var.s3_dvc_bucket_arn}/*",
    ]
  }
  statement {
    effect    = "Allow"
    actions   = ["kafka:DescribeCluster", "kafka:GetBootstrapBrokers"]
    resources = [var.msk_cluster_arn]
  }
}

resource "aws_iam_role_policy" "mlops_s3" {
  name   = "s3-full-and-msk-describe"
  role   = aws_iam_role.mlops.id
  policy = data.aws_iam_policy_document.mlops_s3.json
}

# ── analytics: MSK consumer + read-only S3 ───────────────────────────────────

resource "aws_iam_role" "analytics" {
  name               = "${var.cluster_name}-analytics"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust["analytics"].json
  tags               = var.tags
}

data "aws_iam_policy_document" "analytics" {
  statement {
    effect  = "Allow"
    actions = ["kafka:DescribeCluster", "kafka:GetBootstrapBrokers", "kafka:ListTopics"]
    resources = [var.msk_cluster_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.s3_datasets_bucket_arn, "${var.s3_datasets_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "analytics" {
  name   = "msk-consume-s3-read"
  role   = aws_iam_role.analytics.id
  policy = data.aws_iam_policy_document.analytics.json
}
