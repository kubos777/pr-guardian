# PR Guardian - Levantamiento de Requerimientos v1.0

## 1. Objetivo del Proyecto
Desarrollar un agente AI autónomo que realice Code Reviews preliminares en Pull Requests de GitHub, reduciendo el tiempo de revisión humana en un 40% y previniendo bugs críticos antes del merge.

## 2. Alcance del MVP (Hackathon)
### IN Scope ✅
- Trigger automático vía webhook en PR open/sync.
- Análisis de estilo basado en config files del repo.
- Detección de 5 patrones críticos (N+1, Secrets, NullRefs, TypeLeaks, Perf).
- Comentarios inline en GitHub con referencias históricas.
- Dashboard web básico con estado de análisis.
- Soporte exclusivo para TypeScript/Node.js.

### OUT Scope ❌
- Auto-fix / Refactorizado automático.
- Soporte multi-lenguaje.
- Integración Slack/Jira.
- Análisis de cobertura de tests.
- Autenticación OAuth personalizada.

## 3. Actores y Roles
| Actor | Descripción |
|-------|-------------|
| Dev Junior | Abre PRs, recibe feedback del agente |
| Dev Senior | Valida feedback del agente, aprueba PR |
| PR Guardian Agent | Analiza código, valida hallazgos genera comentarios,Analiza código, valida hallazgos y recupera ejemplos históricos aprobados del repo (no aprende automáticamente en el MVP) |
| GitHub Platform | Provee webhooks, API de PRs, hosting de código |

## 4. Criterios de Aceptación
- [ ] El webhook válido responde en <2 segundos y encola el job (ACK asíncrono).
- [ ] p95 de revisión <30 segundos para PRs TypeScript con <=500 líneas modificadas.
- [ ] Ningún evento repetido produce comentarios duplicados (dedupe por X-GitHub-Delivery y por repo + PR + head_sha).
- [ ] Solo se publican hallazgos cuya ruta y línea existen en el diff actual.
- [ ] El agente nunca comenta líneas de un head_sha obsoleto.
- [ ] Precision >=90% sobre el benchmark versionado de la demo.
- [ ] Recall >=70% para los cinco patrones sembrados en el benchmark.
- [ ] Formato markdown correcto en comentarios inline.
- [ ] El dashboard muestra los estados: queued, analyzing, posting, completed, failed.
- [ ] Una firma de webhook inválida siempre es rechazada.
- [ ] La demo end-to-end funciona tres veces consecutivas sin intervención manual.


## 5. Riesgos y Mitigación
| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Alucinaciones del LLM | Alto | Temperature=0.2 + Double-check prompt + Structured JSON output |
| Latencia API GitHub | Medio | Cachear contexto de repo + Async processing |
| Webhook failures | Alto | Retry logic + Manual trigger button en dashboard |
| Scope creep | Alto | Tech Lead veto power + Daily scope review |

## 6. Contrato del Hallazgo (Finding Schema)

Todo hallazgo generado por el agente debe cumplir esta estructura antes de publicarse:

```json
{
  "rule_id": "secret_exposure",
  "severity": "high",
  "confidence": 0.96,
  "path": "src/config/secrets.ts",
  "line": 3,
  "side": "RIGHT",
  "evidence": "Se asigna un literal tipo credential a API_KEY.",
  "message": "Mover esta credencial a una variable de entorno.",
  "suggestion": "export const API_KEY = process.env.API_KEY;",
  "historical_reference": { "pr": 42, "reason": "Mismo patrón corregido antes." }
}
```

## 7. Stack Tecnológico

### 7.1 Lenguaje principal

**Python >3.10** — decisión ya tomada, sin discusión. Es el lenguaje de todo `agent-core/`, `github-integration/` y del worker.

### 6.2 Framework del agente: LangGraph (no LangChain puro)

**Confirmado: LangGraph**, con un matiz importante para el equipo:

- El ciclo de vida de una revisión (`Idle → Received → FetchingContext → Analyzing → GeneratingComments → PostingToGitHub → Completed/Failed`, ver `ARCHITECTURE_DIAGRAMS.md`) es un grafo de estados. LangGraph lo modela de forma nativa (nodos + edges condicionales + estado tipado compartido), evitando reinventar esa lógica a mano como cadenas secuenciales de LangChain puro.
- Usar solo lo básico de LangGraph alcanza: un nodo por etapa, un `TypedDict`/Pydantic como estado, y edges condicionales para retry/fail. No se necesitan subgrafos, streaming avanzado ni human-in-the-loop para el MVP.
- **Nota de alineación con el código ya existente:** la rama `ft/async-review-pipeline` implementó la orquestación de etapas con **Celery** (colas durables + reintentos por etapa vía `store/stages.py` y `worker/tasks.py`), no con LangGraph. Celery resuelve algo que LangGraph no da out-of-the-box: persistencia durable de jobs y colas distribuidas. Para no duplicar orquestadores, el equipo debe decidir explícitamente uno de estos dos caminos antes de seguir avanzando:
  1. **Celery como orquestador de pipeline** (ya implementado) + **LangGraph solo dentro del nodo `Analyzing`**, para coordinar las 3 llamadas al LLM (style/security/history) en paralelo y fusionar sus resultados.
  2. **LangGraph como orquestador único**, migrando la lógica de reintentos por etapa desde Celery hacia edges condicionales de LangGraph, y usando Celery únicamente como cola de entrada (webhook → job encolado → un solo task que ejecuta el grafo completo).
  
  Opción 1 es la de menor esfuerzo dado el trabajo ya invertido en `worker/tasks.py`. Recomendada para no perder lo ya construido y testeado (`tests/test_pr_guardian.py`).

### 6.3 LLM: Llama-3.1-70B 

Temperature=0.2 se mantiene como estándar en ambos casos (ya documentado en sección 5, Riesgos).

### 6.4 Frontend: Next.js 14 App Router + Tailwind + shadcn/ui

**Confirmado, sin cambios respecto al planteamiento original.** Next.js 14 + Tailwind ya están en `dashboard/package.json`. Se agrega **shadcn/ui** como capa de componentes:

- No es una dependencia opaca instalada vía npm: los componentes se copian al repo con `npx shadcn@latest add <componente>`, dando control total del código sin pelear con theming ajeno.
- Para el dashboard de estados (`queued/analyzing/posting/completed/failed`, ver sección 7) los componentes `Badge`, `Card`, `Table` y `Skeleton` cubren la mayoría de la UI necesaria sin curva de diseño adicional.

Setup pendiente en `dashboard/`:
```bash
cd dashboard
npx shadcn@latest init
npx shadcn@latest add badge card table skeleton button
```

### 6.5 MCP: servidor propio (FastMCP) — no el binario oficial `github-mcp-server` para el pipeline

**Aclaración importante antes de "confirmar":** el `github-mcp-server` oficial de GitHub es un binario Go pensado para **hosts de chat/IDE** (Claude Desktop, VS Code Copilot, Cursor, Kiro, etc.), que habla el protocolo MCP por stdio o HTTP. No es una librería que se importe dentro de un backend Python para servir un pipeline automatizado de webhooks.

El proyecto ya construyó la solución correcta para este caso de uso: un **servidor MCP propio en Python con FastMCP** (`github-integration/server.py`, dependencia `fastmcp` en `requirements.txt`), que expone tools específicas (`get_pr_files`, `get_repo_config`, `post_review`, etc.) y llama internamente a la GitHub REST API con un PAT propio. Este es el servidor que usa el pipeline en producción — **se mantiene, no se reemplaza por el binario oficial.**

El binario oficial `github-mcp-server` sí es útil como **herramienta de desarrollo** (para que el propio equipo, usando Kiro/Claude Desktop, pueda explorar el repo, PRs e issues por lenguaje natural mientras programa) pero **no forma parte del pipeline del agente**. Step-by-step si el equipo quiere usarlo con ese propósito:

1. **Prerrequisito:** Docker instalado y corriendo (`docker --version`).
2. **Crear un GitHub PAT (fine-grained)** con scopes mínimos: `repo`, `read:org`. Nunca commitear este token — usar variables de entorno.
   https://github.com/settings/personal-access-tokens/new
3. **Probar el servidor manualmente:**
   ```bash
   docker run -i --rm \
     -e GITHUB_PERSONAL_ACCESS_TOKEN=<tu_token> \
     -e GITHUB_TOOLSETS="repos,issues,pull_requests" \
     ghcr.io/github/github-mcp-server
   ```
4. **Configurarlo en el host MCP** (ej. Claude Desktop, o el cliente MCP de Kiro), agregando a su archivo de configuración:
   ```json
   {
     "mcpServers": {
       "github": {
         "command": "docker",
         "args": [
           "run", "-i", "--rm",
           "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
           "-e", "GITHUB_TOOLSETS",
           "ghcr.io/github/github-mcp-server"
         ],
         "env": {
           "GITHUB_PERSONAL_ACCESS_TOKEN": "<tu_token>",
           "GITHUB_TOOLSETS": "repos,issues,pull_requests"
         }
       }
     }
   }
   ```
5. Reiniciar el host MCP. Las tools de GitHub deben aparecer disponibles para el asistente.

## 7. Definition of Done — Fase 1

**DoD Fase 1:** *"El agente recibe webhook → lee diff → genera JSON válido → envía comentario."*

Criterios verificables para considerar la Fase 1 completa:

- [ ] El endpoint de webhook valida la firma HMAC-SHA256 (`X-Hub-Signature-256`) y rechaza firmas inválidas con 401.
- [ ] El webhook responde en <2 segundos (ACK asíncrono; el procesamiento real ocurre después, no bloquea la respuesta HTTP).
- [ ] Dado un evento `pull_request.opened` o `.synchronize` válido, el sistema obtiene el diff real del PR vía MCP (no un mock).
- [ ] El diff se envía al LLM (Claude 3.5 Sonnet primario / Llama-3.1-8B fallback) usando al menos uno de los prompts de `agent-core/prompts/` (style, security o history).
- [ ] La respuesta del LLM se parsea como JSON válido contra el esquema `Finding` (o los esquemas raw `StyleOutput`/`SecurityOutput`/`HistoryOutput`) sin excepciones.
- [ ] Si el JSON es inválido o no matchea el esquema, el sistema no publica nada y marca el job como fallo recuperable (retry) según la política de reintentos por etapa.
- [ ] Cada finding validado referencia un archivo y línea que existen realmente en el diff (chequeo anti-alucinación, ya implementado en `diff_utils.py`/`fingerprint.py` en `ft/async-review-pipeline`).
- [ ] Se publica al menos un comentario real en el PR de prueba (`demo-repo`) usando la GitHub API, visible en la UI de GitHub.
- [ ] El flujo completo (webhook → diff → LLM → JSON válido → comentario publicado) se ejecuta de punta a punta al menos 1 vez sin intervención manual, contra un PR real o simulado con `test_webhook.py` / la suite de `tests/`.
