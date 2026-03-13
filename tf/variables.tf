variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-west-2"
}

variable "subnet_a_cidr" {
  type        = string
  description = "CIDR block for Private Subnet A"
}

variable "subnet_b_cidr" {
  type        = string
  description = "CIDR block for Private Subnet B"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for Main VPC"
  default     = "10.0.0.0/16"
}