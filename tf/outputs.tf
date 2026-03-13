output "lambda_function_arn" {
  description = "The ARN of the Lambda function"
  value       = aws_lambda_function.snapshot_cleaner.arn
}

output "vpc_id" {
  description = "The ID of the created Main VPC"
  value       = aws_vpc.main.id
}