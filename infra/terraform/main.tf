terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Real deployments should use a remote backend (S3 + DynamoDB lock table) instead
  # of local state — left as a placeholder block since bucket/table names are
  # account-specific and shouldn't be hardcoded into a shared repo.
  # backend "s3" {
  #   bucket         = "themarket-ai-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "themarket-ai-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "project_name" {
  type    = string
  default = "themarket-ai-quant-forex"
}

variable "db_password" {
  type      = string
  sensitive = true
  # No default — must be supplied via TF_VAR_db_password or a tfvars file that's
  # gitignored. Never commit real secrets to this repo.
}

variable "container_image_backend" {
  type        = string
  description = "ECR image URI for the backend service, e.g. <account>.dkr.ecr.<region>.amazonaws.com/themarket-backend:latest"
}

variable "container_image_ai_engine" {
  type = string
}

variable "container_image_frontend" {
  type = string
}
