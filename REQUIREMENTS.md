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
| PR Guardian Agent | Analiza código, genera comentarios, aprende del repo |
| GitHub Platform | Provee webhooks, API de PRs, hosting de código |

## 4. Criterios de Aceptación
- [ ] Agente responde en <30 segundos promedio.
- [ ] 90% de comentarios son relevantes (no genéricos).
- [ ] Formato markdown correcto en comentarios inline.
- [ ] Dashboard muestra estado en tiempo real.
- [ ] Demo funciona end-to-end sin errores críticos.

## 5. Riesgos y Mitigación
| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Alucinaciones del LLM | Alto | Temperature=0.2 + Double-check prompt + Structured JSON output |
| Latencia API GitHub | Medio | Cachear contexto de repo + Async processing |
| Webhook failures | Alto | Retry logic + Manual trigger button en dashboard |
| Scope creep | Alto | Tech Lead veto power + Daily scope review |