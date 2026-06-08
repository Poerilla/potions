# Terraform Bootstrap

This creates one small Ubuntu EC2 host for the first MNQ v2b paper container.

Default sizing:

- `t4g.small`
- Ubuntu 24.04 ARM64
- 64 GB encrypted gp3 root volume
- Docker + Docker Compose plugin installed by `user_data`

Example:

```bash
cd potions/live/deploy/terraform
terraform init
terraform apply \
  -var 'key_name=YOUR_EC2_KEYPAIR' \
  -var 'admin_cidr=YOUR_PUBLIC_IP/32'
```

After the host is up, place the repo/tarball under `/opt/potions`, put runtime
state under `/opt/potions-state`, and run the Compose stack from
`potions/live/deploy`.

Do not open the health port publicly. The compose file binds it to localhost;
use SSH forwarding if you need to inspect it:

```bash
ssh -L 8765:127.0.0.1:8765 ubuntu@HOST
curl http://127.0.0.1:8765/healthz
```
