variable "region" {
  default = "us-east-1"
}

variable "db_password" {
  description = "Postgres password — set this in terraform.tfvars, never commit it"
  sensitive   = true
}

variable "db_instance_class" {
  default = "db.t3.micro"
}
