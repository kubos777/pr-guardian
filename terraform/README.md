# PR Guardian — Terraform (AWS Free Tier)

Provisiona toda la infraestructura de producción con un comando:

- **EC2** `t2.micro` (Amazon Linux 2023) con webhook + worker + MCP + dashboard
- **RDS** PostgreSQL `db.t3.micro` (20 GB), accesible **solo** desde el EC2
- **Security Groups**: EC2 (22/80/443), RDS (5432 solo desde EC2)
- **Caddy** con HTTPS automático (Let's Encrypt) vía dominio o `<ip>.nip.io`
- Bootstrap completo por `user_data`: instala deps, clona el repo, escribe `.env`,
  crea los servicios systemd y arranca todo

## Prerrequisitos

- Cuenta AWS con Free Tier
- `terraform` >= 1.5 y AWS CLI configurado (`aws configure`)
- Un par de llaves SSH (`ssh-keygen -t ed25519`)

## Uso

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edita terraform.tfvars con tus valores y secretos

terraform init
terraform plan
terraform apply
```

Al terminar, Terraform imprime:

```
public_url  = "https://<ip>.nip.io"
webhook_url = "https://<ip>.nip.io/webhook"
ssh_command = "ssh ec2-user@<ip>"
```

> El primer arranque tarda ~3-5 min (instala Node, uv, buildea el dashboard,
> Caddy pide el certificado). Sigue el progreso con:
> `ssh ec2-user@<ip> 'sudo journalctl -u cloud-final -f'`

## Configurar el webhook de GitHub

1. Repo del demo → Settings → Webhooks → Add webhook
2. **Payload URL:** el `webhook_url` del output
3. **Content type:** `application/json`
4. **Secret:** el mismo `github_webhook_secret` del tfvars
5. **Events:** solo *Pull requests*

## Verificar

```bash
ssh ec2-user@<ip>
sudo systemctl status 'pr-guardian-*' caddy
journalctl -u pr-guardian-worker -f
```

Abre un PR en el demo-repo → en <30s aparecen los comentarios inline.

## Costos

Todo dentro del Free Tier: EC2 t2.micro (750 h/mes), RDS db.t3.micro (750 h/mes),
30 GB EBS. Único costo variable: las APIs de Groq/Gemini (free tier también).

## ⚠️ Notas de seguridad

- **`ssh_allowed_cidr`**: por defecto `0.0.0.0/0`. **Restríngelo a tu IP** (`TU_IP/32`).
- **Secretos**: se inyectan al `.env` del instance vía `user_data`. Es visible desde
  la metadata del instance; para producción real usa **SSM Parameter Store** o
  **Secrets Manager** en lugar de `user_data`. Para el hackathon es aceptable.
- `terraform.tfvars` y el `*.tfstate` **nunca** se commitean (ya en `.gitignore`);
  el state puede contener los secretos en claro.
- Para destruir todo al terminar el hackathon: `terraform destroy`.
