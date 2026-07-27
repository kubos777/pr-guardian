# RUNBOOK — Deploy de PR Guardian a AWS

Guía paso a paso para desplegar producción y destruirla al terminar.
Tiempo estimado: ~15 min de setup + ~5 min de bootstrap automático.

---

## 0. Prerrequisitos (una sola vez)

```bash
# Instalar herramientas (macOS)
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
brew install awscli

# Verificar
terraform version
aws --version
```

Necesitas también:
- Una cuenta AWS **con Free Tier vigente** (verifícalo en Billing → Free Tier)
- Tu llave SSH pública en `~/.ssh/id_ed25519.pub` (ya la tienes)

---

## 1. Crear alarma de billing (2 min, hazlo SIEMPRE)

AWS Console → **Billing** → **Budgets** → Create budget:
- Tipo: Cost budget
- Monto: **$1**
- Alerta: email al 80%

Esto te avisa si algo se sale del Free Tier. Cero sorpresas.

---

## 2. Crear usuario IAM con acceso programático

AWS Console → **IAM** → **Users** → Create user:
1. Nombre: `pr-guardian-deployer`
2. Marca **Access key - Programmatic access**
3. Permisos: `AdministratorAccess` (simple para el hackathon)
4. Guarda el **Access Key ID** y **Secret Access Key**

---

## 3. Configurar credenciales locales

```bash
aws configure
# AWS Access Key ID:     <tu-access-key>
# AWS Secret Access Key: <tu-secret-key>
# Default region name:   us-east-1
# Default output format: json

# Verificar que funciona
aws sts get-caller-identity
```

---

## 4. Revisar el tfvars (ya generado)

`terraform/terraform.tfvars` ya está listo con tus secretos, tu llave SSH y
SSH restringido a tu IP. Verifica solo estos dos campos:

```bash
grep -E "ssh_allowed_cidr|aws_region" terraform/terraform.tfvars
```

Si tu IP cambió (es IP de casa), actualízala:

```bash
curl -4 ifconfig.me   # tu IPv4 actual
# edita ssh_allowed_cidr = "NUEVA_IP/32" en terraform.tfvars
```

---

## 5. Desplegar

```bash
cd terraform

terraform init      # descarga el provider de AWS (~1 min)
terraform plan      # revisa qué va a crear: 1 EC2, 1 RDS, 2 SGs, etc.
terraform apply     # escribe 'yes' para confirmar
```

`apply` tarda ~3-5 min (crea RDS + EC2). Al terminar imprime:

```
public_url  = "https://<ip>.nip.io"
webhook_url = "https://<ip>.nip.io/webhook"
ssh_command = "ssh ec2-user@<ip>"
rds_endpoint = "..."
```

---

## 6. Esperar el bootstrap (~3-5 min más)

El EC2 corre `user_data` (instala deps, buildea el dashboard, arranca servicios,
Caddy pide el certificado HTTPS). Sigue el progreso:

```bash
ssh ec2-user@<ip> 'sudo tail -f /var/log/cloud-init-output.log'
# espera la línea: "PR Guardian bootstrap complete"
```

Verifica que los servicios estén arriba:

```bash
ssh ec2-user@<ip> 'sudo systemctl status pr-guardian-webhook pr-guardian-worker pr-guardian-mcp pr-guardian-dashboard caddy --no-pager'
```

Abre el dashboard en el navegador: **`public_url`** (el `https://<ip>.nip.io`).

---

## 7. Configurar el webhook de GitHub

Repo del demo (`pr-guardian-demo`) → **Settings → Webhooks → Add webhook**:
- **Payload URL:** el `webhook_url` del output
- **Content type:** `application/json`
- **Secret:** el mismo `GITHUB_WEBHOOK_SECRET` de tu `.env`
- **Events:** "Let me select individual events" → solo **Pull requests**
- Add webhook

GitHub enviará un `ping`; debe responder 200 (lo ves en "Recent Deliveries").

---

## 8. Probar end-to-end en producción

1. En el demo-repo, cierra y reabre el PR #1 (o haz un push a la branch para
   disparar un `synchronize`).
2. Observa el dashboard: el job pasa por las stages en vivo.
3. En <30s aparecen los comentarios inline del agente en el PR.

Si algo falla, revisa logs:

```bash
ssh ec2-user@<ip> 'journalctl -u pr-guardian-worker -n 100 --no-pager'
```

---

## 9. Compartir con los jueces

Comparte la URL pública: **`public_url`** (dashboard) y el PR del demo-repo con
los comentarios ya publicados. Documenta ambas en el pitch.

---

## 10. Destruir al terminar (IMPORTANTE — vuelve a $0)

```bash
cd terraform
terraform destroy   # escribe 'yes'
```

Después, en AWS Console:
- Borra el usuario IAM `pr-guardian-deployer` (o al menos sus access keys)
- Verifica en Billing que no quede nada corriendo

---

## Troubleshooting rápido

| Problema | Solución |
|----------|----------|
| `terraform apply` falla con "not authorized" | El usuario IAM necesita más permisos (usa AdministratorAccess) |
| No puedo hacer SSH | Tu IP cambió; actualiza `ssh_allowed_cidr` y `terraform apply` |
| HTTPS no carga | Espera 1-2 min más (Caddy tramitando el cert de Let's Encrypt) |
| Webhook responde 401 | El secret de GitHub no coincide con `GITHUB_WEBHOOK_SECRET` |
| Comentarios no aparecen | Revisa `journalctl -u pr-guardian-worker`; verifica GITHUB_TOKEN con permiso de escritura |
| `502` en el dashboard | El servicio `pr-guardian-dashboard` no arrancó; revisa su journalctl |
