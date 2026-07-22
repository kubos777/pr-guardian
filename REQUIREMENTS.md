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
