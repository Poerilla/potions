variable "aws_region" {
  description = "AWS region for the paper/live runtime instance."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name tag prefix."
  type        = string
  default     = "potions-mnq-v2b-paper"
}

variable "instance_type" {
  description = "Small ARM instance is enough for one MNQ v2b paper container."
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root volume size."
  type        = number
  default     = 64
}

variable "key_name" {
  description = "Existing EC2 SSH key pair name."
  type        = string
}

variable "admin_cidr" {
  description = "Operator IP/CIDR allowed to SSH, e.g. 203.0.113.10/32."
  type        = string
}
