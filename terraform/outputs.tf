output "public_ip" {
  description = "EC2 public IP."
  value       = aws_instance.this.public_ip
}

output "public_url" {
  description = "Public HTTPS URL of PR Guardian (share this with the judges)."
  value       = var.domain != "" ? "https://${var.domain}" : "https://${aws_instance.this.public_ip}.nip.io"
}

output "webhook_url" {
  description = "URL to configure in the GitHub webhook (Payload URL)."
  value       = var.domain != "" ? "https://${var.domain}/webhook" : "https://${aws_instance.this.public_ip}.nip.io/webhook"
}

output "ssh_command" {
  description = "Convenience SSH command."
  value       = "ssh ec2-user@${aws_instance.this.public_ip}"
}

output "rds_endpoint" {
  description = "RDS endpoint (reachable only from the EC2 security group)."
  value       = aws_db_instance.this.address
}
