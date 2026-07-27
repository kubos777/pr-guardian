locals {
  name = var.project_name
  tags = {
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Network: use the account's default VPC + subnets (simplest for Free Tier).
# ---------------------------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI, resolved from the public SSM parameter.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---------------------------------------------------------------------------
# SSH key pair
# ---------------------------------------------------------------------------
resource "aws_key_pair" "this" {
  key_name   = "${local.name}-key"
  public_key = file(var.ssh_public_key_path)
  tags       = local.tags
}

# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------
resource "aws_security_group" "ec2" {
  name        = "${local.name}-ec2-sg"
  description = "PR Guardian EC2: SSH, HTTP, HTTPS"
  vpc_id      = data.aws_vpc.default.id
  tags        = local.tags

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "HTTP (Caddy redirects to HTTPS + ACME challenge)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (webhook + dashboard)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound (GitHub API, Groq/Gemini, package installs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds-sg"
  description = "PR Guardian RDS: Postgres from EC2 only"
  vpc_id      = data.aws_vpc.default.id
  tags        = local.tags

  ingress {
    description     = "Postgres from the EC2 instance only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------------------------------------------------------------------------
# RDS PostgreSQL (Free Tier: db.t3.micro, 20 GB, not publicly accessible)
# ---------------------------------------------------------------------------
resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids
  tags       = local.tags
}

resource "aws_db_instance" "this" {
  identifier             = "${local.name}-db"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage = var.db_allocated_storage
  # gp2 is the storage type covered by the RDS Free Tier (20 GB). gp3 can
  # incur charges, so we stay on gp2 for the hackathon.
  storage_type = "gp2"
  db_name      = "pr_guardian"
  username               = "pr_guardian"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible = false
  skip_final_snapshot = true
  # Free Tier no permite retención de backups > 0. Para la demo no hacen falta;
  # en una cuenta de pago puedes subirlo (p.ej. 7) para backups automáticos.
  backup_retention_period = 0
  tags                    = local.tags
}

# ---------------------------------------------------------------------------
# EC2 instance + bootstrap
# ---------------------------------------------------------------------------
resource "aws_instance" "this" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  key_name               = aws_key_pair.this.key_name
  vpc_security_group_ids = [aws_security_group.ec2.id]
  subnet_id              = data.aws_subnets.default.ids[0]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url              = var.repo_url
    repo_branch           = var.repo_branch
    domain                = var.domain
    database_url          = "postgresql://pr_guardian:${var.db_password}@${aws_db_instance.this.address}:5432/pr_guardian"
    github_token          = var.github_token
    github_webhook_secret = var.github_webhook_secret
    groq_api_key          = var.groq_api_key
    gemini_api_key        = var.gemini_api_key
  })

  # Re-run bootstrap if the script changes.
  user_data_replace_on_change = true

  tags = merge(local.tags, { Name = "${local.name}-server" })

  depends_on = [aws_db_instance.this]
}
