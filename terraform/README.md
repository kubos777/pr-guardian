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

## Costos — ¿me van a cobrar? (7 días de prod)

Escenario: **cuenta AWS nueva** (elegible Free Tier 12 meses), corriendo ~7 días.

| Recurso | Free Tier | Uso 7 días (168 h) | Costo |
|---------|-----------|--------------------|-------|
| EC2 t2.micro | 750 h/mes | 168 h | **$0** |
| RDS db.t3.micro | 750 h/mes | 168 h | **$0** |
| RDS storage 20 GB gp2 | 20 GB | 20 GB | **$0** |
| EBS 30 GB gp3 (root EC2) | 30 GB | 30 GB | **$0** |
| IPv4 pública | 750 h/mes (cuentas nuevas) | 168 h | **$0** |
| Backups RDS (7 días) | hasta 20 GB | < 20 GB | **$0** |
| Egress de red | 100 GB/mes | mínimo | **$0** |
| **Total infra** | | | **~$0** |

Único costo real: **APIs de Groq/Gemini** — ambas en free tier, también $0.

### ⚠️ Cuándo SÍ te cobrarían

- **Cuenta con Free Tier ya vencido** (>12 meses): entonces ~$5–7 por los 7 días
  (EC2 ~$2 + RDS ~$2 + IPv4 ~$0.84 + storage ~$1). Verifica en Billing → Free Tier
  si aún eres elegible **antes** de aplicar.
- **Olvidar destruir** y dejarlo corriendo semanas → se acumula al pasar las 750 h/mes.
- Cambiar a instancias más grandes que t2.micro / db.t3.micro.

### Cómo NO pagar de más (obligatorio)

1. **Alarma de billing** antes de aplicar: AWS Console → Billing → Budgets →
   crea un budget de $1 con alerta por email. 2 minutos, te avisa si algo se sale.
2. **Destruir al terminar** el hackathon (lo más importante):
   ```bash
   terraform destroy
   ```
   Esto borra EC2, RDS (sin snapshot final, ya configurado), SGs y todo. Costo vuelve a $0.
3. Si quieres pausar sin destruir: no es necesario para 7 días; es más simple
   destruir y volver a `apply` (5 min) cuando lo necesites.

## Un solo entorno: local + prod (sin dev)

Este proyecto NO tiene ambiente `dev`. Solo dos:
- **Local**: `docker compose up` (Postgres + Redis + servicios) — para desarrollo.
- **Prod**: este Terraform (7 días para la demo, luego `terraform destroy`).

No hay `terraform workspace` ni variantes por entorno: un único stack, aplicado
cuando lo necesitas y destruido al terminar.

## ⚠️ Notas de seguridad

- **`ssh_allowed_cidr`**: por defecto `0.0.0.0/0`. **Restríngelo a tu IP** (`TU_IP/32`).
- **Secretos**: se inyectan al `.env` del instance vía `user_data`. Es visible desde
  la metadata del instance; para producción real usa **SSM Parameter Store** o
  **Secrets Manager** en lugar de `user_data`. Para el hackathon es aceptable.
- `terraform.tfvars` y el `*.tfstate` **nunca** se commitean (ya en `.gitignore`);
  el state puede contener los secretos en claro.
- Para destruir todo al terminar el hackathon: `terraform destroy`.
