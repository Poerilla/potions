terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_ami" "ubuntu_arm64" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "potions_live" {
  name        = "${var.name}-sg"
  description = "Potions live runtime bootstrap access"

  ingress {
    description = "SSH from operator IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-sg"
  }
}

resource "aws_instance" "potions_live" {
  ami                         = data.aws_ami.ubuntu_arm64.id
  instance_type               = var.instance_type
  key_name                    = var.key_name
  vpc_security_group_ids      = [aws_security_group.potions_live.id]
  associate_public_ip_address = true

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-EOF
    #!/usr/bin/env bash
    set -euxo pipefail
    apt-get update
    apt-get install -y ca-certificates curl docker.io docker-compose-v2 unzip
    systemctl enable --now docker
    usermod -aG docker ubuntu
    mkdir -p /opt/potions /opt/potions-state
    chown -R ubuntu:ubuntu /opt/potions /opt/potions-state
  EOF

  tags = {
    Name = var.name
  }
}
