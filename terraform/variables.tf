variable "region" {
  default = "us-east-1"
}

variable "db_password" {
  description = "Postgres password — set in terraform.tfvars, never commit it"
  sensitive   = true
}

variable "db_instance_class" {
  default = "db.t3.micro"
}

variable "s3_bucket_name" {
  description = "Globally unique S3 bucket name for CSV data files"
  # change this to something unique — S3 bucket names are global across all AWS accounts
  default = "sensor-pipeline-data-Ramakrishna"
}