output "instance_id" {
  value = aws_instance.potions_live.id
}

output "public_ip" {
  value = aws_instance.potions_live.public_ip
}

output "ssh_command" {
  value = "ssh ubuntu@${aws_instance.potions_live.public_ip}"
}
