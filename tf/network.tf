resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "Main"
  }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.subnet_a_cidr
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "Private Subnet A"
  }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.subnet_b_cidr
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "Private Subnet B"
  }
}

resource "aws_security_group" "lambda_sg" {
  name        = "lambda_ec2_cleaner_sg"
  description = "Security group for EC2 Snapshot Cleaner Lambda"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "Lambda Security Group"
  }
}

resource "aws_security_group" "vpc_endpoint_sg" {
  name        = "ec2_vpc_endpoint_sg"
  description = "Security group for VPC Interface Endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda_sg.id]
  }

  tags = {
    Name = "VPC Endpoint SG"
  }
}

resource "aws_vpc_endpoint" "ec2" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ec2"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  security_group_ids  = [aws_security_group.vpc_endpoint_sg.id]
  private_dns_enabled = true

  tags = {
    Name = "EC2 VPC Endpoint"
  }
}

resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  security_group_ids  = [aws_security_group.vpc_endpoint_sg.id]
  private_dns_enabled = true

  tags = {
    Name = "CloudWatch Logs VPC Endpoint"
  }
}