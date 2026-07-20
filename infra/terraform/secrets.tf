# Real secrets management for production: values are written once (out of band, via
# `aws secretsmanager put-secret-value` or the console — never committed to this
# repo or passed as a `-var` on the CLI where it'd land in shell history) and ECS
# task definitions reference them by ARN (see the `secrets` block in ecs.tf), so the
# plaintext value never appears in a task definition, CloudWatch log, or `terraform
# plan` output. This is the production replacement for this repo's `.env.example`
# pattern, which is fine for local dev but not for a real deployment.
#
# For a genuinely secrets-manager-agnostic app, HashiCorp Vault is the other common
# choice — the same substitution (env var -> secrets client) applies whether you're
# reading from AWS Secrets Manager, Vault, or GCP Secret Manager; only the SDK call
# in app/core/config.py's Settings loader would change.

resource "aws_secretsmanager_secret" "database_url" {
  name = "${var.project_name}/${var.environment}/database_url"
}

resource "aws_secretsmanager_secret" "redis_url" {
  name = "${var.project_name}/${var.environment}/redis_url"
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}/${var.environment}/jwt_secret"
}

resource "aws_secretsmanager_secret" "jwt_refresh_secret" {
  name = "${var.project_name}/${var.environment}/jwt_refresh_secret"
}

resource "aws_secretsmanager_secret" "fernet_key" {
  name = "${var.project_name}/${var.environment}/fernet_key"
}

resource "aws_secretsmanager_secret" "broker_api_keys" {
  name = "${var.project_name}/${var.environment}/broker_api_keys"
  description = "JSON blob: polygon_api_key, twelvedata_api_key, finnhub_api_key, metaapi_token, huggingface_token"
}

# Deliberately no aws_secretsmanager_secret_version resources here — that would
# mean committing secret values (even as terraform variables) into state/plan
# output. Populate actual values with:
#   aws secretsmanager put-secret-value --secret-id themarket-ai-quant-forex/production/jwt_secret \
#     --secret-string "$(openssl rand -base64 48)"
