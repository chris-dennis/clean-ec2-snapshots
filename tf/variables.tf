variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-west-2"
}

variable "vpc_id" {
  type        = string
  description = "ID of the existing Main VPC"
}

variable "subnet_ids" {
  type        = list(string)
  description = "IDs of the existing private subnets to attach the Lambda to"
}
