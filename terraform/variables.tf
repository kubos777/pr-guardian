variable "aws_region" {
  description = "AWS region to deploy into (pick one with Free Tier eligibility)."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "pr-guardian"
}

variable "instance_type" {
  description = "EC2 instance type (t2.micro is Free Tier)."
  type        = string
  default     = "t2.micro"
}

variable "db_instance_class" {
  description = "RDS instance class (db.t3.micro is Free Tier)."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB (20 GB is Free Tier)."
  type        = number
  default     = 20
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key (e.g. ~/.ssh/id_ed25519.pub). Used to create the EC2 key pair."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = <<-EOT
    CIDR allowed to SSH (port 22). SECURITY: set this to YOUR_IP/32, not
    0.0.0.0/0. Find your IP with `curl ifconfig.me`.
  EOT
  type        = string
  default     = "0.0.0.0/0"
}

variable "domain" {
  description = <<-EOT
    Custom domain for HTTPS (e.g. pr-guardian.example.com) pointed at the
    EC2 public IP via an A record. Leave empty to use <public-ip>.nip.io,
    which gives real Let's Encrypt HTTPS with no domain purchase needed.
  EOT
  type        = string
  default     = ""
}

variable "repo_url" {
  description = "Git URL of the PR Guardian repo to clone on the instance."
  type        = string
  default     = "https://github.com/kubos777/pr-guardian.git"
}

variable "repo_branch" {
  description = "Branch to deploy."
  type        = string
  default     = "main"
}

# ---------------------------------------------------------------------------
# Secrets — pass via terraform.tfvars or TF_VAR_* env vars. Never commit them.
# ---------------------------------------------------------------------------

variable "db_password" {
  description = "Master password for the RDS PostgreSQL instance."
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub token with Pull requests: Read/Write on the demo repo."
  type        = string
  sensitive   = true
}

variable "github_webhook_secret" {
  description = "Shared secret configured in the GitHub webhook."
  type        = string
  sensitive   = true
}

variable "groq_api_key" {
  description = "Groq API key (primary LLM)."
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Gemini API key (fallback LLM)."
  type        = string
  sensitive   = true
  default     = ""
}
