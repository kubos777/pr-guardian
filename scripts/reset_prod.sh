#!/usr/bin/env bash
# Resetea el estado de prod (RDS jobs + cola Redis) para una demo/grabación
# fresca — así el siguiente webhook corre el pipeline en vivo desde cero.
set -euo pipefail

HOST="${1:-ec2-user@54.90.206.50}"
KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" '
  cd /opt/pr-guardian
  set -a; source .env; set +a
  (redis6-cli FLUSHALL 2>/dev/null || redis-cli FLUSHALL 2>/dev/null) && echo "redis purgado"
  /usr/local/bin/uv run python - <<PY
import sys
sys.path.insert(0, ".")
from sqlalchemy import text
from store import db
db.init_db()
with db.session() as s:
    for q in ("DELETE FROM job_events", "DELETE FROM findings", "DELETE FROM jobs"):
        s.execute(text(q))
    s.commit()
print("RDS jobs reseteados")
PY
'
echo "✅ prod limpio — listo para grabar"
