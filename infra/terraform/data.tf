resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.medium"
  allocated_storage      = 50
  storage_type           = "gp3"
  db_name                = "forex"
  username               = "forex"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.data_layer.id]
  multi_az               = var.environment == "production"
  backup_retention_period = 7
  deletion_protection    = var.environment == "production"
  skip_final_snapshot    = var.environment != "production"

  tags = { Name = "${var.project_name}-postgres" }
}

# TimescaleDB isn't an RDS engine — the standard managed path is either Timescale's
# own cloud offering or self-managed on EC2/ECS with the timescaledb extension. This
# repo runs it as a plain RDS Postgres instance with the extension enabled via
# parameter group, which supports the extension but not Timescale's full continuous
# aggregates/compression policy tooling — acceptable for this project's scale, not a
# drop-in replacement for Timescale Cloud at high tick volume.
resource "aws_db_parameter_group" "timescale" {
  name   = "${var.project_name}-timescale-params"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "timescaledb"
  }
}

resource "aws_db_instance" "timescale" {
  identifier              = "${var.project_name}-timescale"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t4g.large"  # larger than the app DB — tick data is write-heavy
  allocated_storage       = 200
  storage_type            = "gp3"
  db_name                 = "forex_ticks"
  username                = "forex"
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.data_layer.id]
  parameter_group_name    = aws_db_parameter_group.timescale.name
  backup_retention_period = 7
  deletion_protection     = var.environment == "production"
  skip_final_snapshot     = var.environment != "production"

  tags = { Name = "${var.project_name}-timescale" }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project_name}-redis"
  description           = "Redis for Celery broker/result backend + rate limiting + caching"
  engine                = "redis"
  engine_version        = "7.1"
  node_type             = "cache.t4g.small"
  num_cache_clusters    = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"
  subnet_group_name     = aws_elasticache_subnet_group.main.name
  security_group_ids    = [aws_security_group.data_layer.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}
