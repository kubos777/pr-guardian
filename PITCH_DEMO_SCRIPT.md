# PR Guardian — Guión de Pitch y Demo (Issue #16)

Preparado para la entrega del hackathon. Todo el contenido aquí está anclado en
lo que el proyecto realmente hace hoy — nada de esto es aspiracional.

**Fuentes usadas:** `EXECUTIVE_SUMMARY.md`, `github-integration/ARCHITECTURE_DIAGRAMS.md`,
`scripts/e2e_trigger.py`, y el PR real de prueba en `kubos777/pr-guardian-demo#1`.

---

## Qué necesita el humano vs. qué ya está listo aquí

| Checklist item | Estado |
|---|---|
| Coordinar con PM la estructura del pitch | ⏳ Estructura propuesta abajo — falta tu confirmación con el PM |
| Script de la demo en vivo | ✅ Completo, con comandos reales (ver abajo) |
| Grabar screen recording | ⏳ Requiere que tú lo grabes (OBS/Loom) — guía abajo |
| Editar video | ⏳ Requiere edición manual — checklist abajo |
| Exportar a MP4 ≤5 min | ⏳ Manual, según tu editor |
| Slides con 3 diagramas Mermaid | ✅ Diagramas localizados y corregidos (ver abajo) — falta exportarlos de mermaid.live |
| Compartir borrador con PM | ⏳ Acción tuya |
| Respuestas a preguntas de jueces | ✅ Completo abajo |

---

## 1. Estructura del Pitch (3–5 min)

Propuesta de timing para 4 minutos — ajustable según lo que acuerdes con el PM:

| Sección | Tiempo | Contenido |
|---|---|---|
| **Problema** | 30s | Equipos pierden 15-20h/semana en code review repetitivo. Juniors repiten errores, seniors se queman revisando estilo en vez de arquitectura. |
| **Solución** | 30s | PR Guardian: reviewer AI que entiende tu código, tu estilo y tu historial de PRs aprobados — no un linter genérico. |
| **Demo** | 2 min | Ver sección 2 abajo — el flujo completo en vivo. |
| **Arquitectura** | 45s | 3 diagramas (sección 3): pipeline asíncrono, componentes, máquina de estados. |
| **Diferenciador** | 30s | Retrieval sobre historial curado propio, no reglas genéricas. Ver sección 4 (Q&A) para el detalle. |

Texto base para Problema/Solución/Diferenciador ya está escrito en `EXECUTIVE_SUMMARY.md`
— léelo en voz alta tal cual, ya está calibrado para pitch ejecutivo.

---

## 2. Script de la Demo en Vivo

### Setup previo (hacer ANTES de grabar, no durante)

```bash
# 1. Backend corriendo
cd pr-guardian
docker compose up -d
docker compose ps    # confirmar postgres, redis, webhook, worker = Up

# 2. Reiniciar el worker SIEMPRE justo antes de grabar (ver advertencia abajo)
docker compose restart worker

# 3. Dashboard corriendo (otra terminal)
cd dashboard
npm run dev          # http://localhost:3000

# 4. Verificar que el dashboard está en estado limpio antes de grabar
curl http://localhost:3000/api/status
# Si devuelve un job viejo de un test anterior, ignóralo —
# el paso 3 de la demo va a crear uno nuevo de todas formas.
```

> ⚠️ **Bug real encontrado en ensayo (2026-07-26), confirmado y con workaround:**
> si el worker lleva rato corriendo sin procesar nada, el primer job que le
> llega puede quedarse pegado en `QUEUED` para siempre — el task se marca
> "succeeded" en los logs de Celery pero no hizo nada (probablemente el pool
> de conexión de SQLAlemy a Postgres se establece antes del fork de Celery,
> quedando en un estado inconsistente en el proceso hijo). **Reiniciar el
> worker (`docker compose restart worker`) justo antes de grabar lo arregla.**
> Vale la pena reportarlo al equipo para un fix real (ej. recrear el engine
> en un signal `worker_process_init` de Celery) — esto no es parte de este
> ticket, pero si no se soluciona puede arruinar la demo en vivo el día de
> la entrega.
>
> ⚠️ **Riesgo de rate limit — probar UNA vez, no varias, antes de grabar:**
> en el ensayo de hoy, Groq devolvió resultados reales (2 de 3 prompts)
> pero llegó a su límite de 12,000 tokens/min de free tier tras varias
> corridas seguidas de prueba — y el fallback a Gemini también falló con
> `limit: 0` en su cuota free tier (revisar si esa API key tiene el free
> tier realmente habilitado en Google AI Studio, no solo agotado). **No
> ensayes el flujo completo más de una vez seguida en la ventana de un
> minuto antes de la toma final** — el pipeline funciona, pero el free
> tier de Groq es angosto (30 RPM / 12k TPM) y se agota rápido si lo
> pruebas repetidamente.

### Paso 1 — Mostrar el PR con bugs en GitHub

Abre en el navegador: **https://github.com/kubos777/pr-guardian-demo/pull/1**

Este PR real (`feat: add user features`) ya tiene bugs intencionales sembrados en:
- `src/config/secrets.ts` — secreto hardcodeado (finding de **seguridad**)
- `src/services/userService.ts` — patrón de query **N+1**
- `src/components/HeavyList.tsx` — problema de **estilo/performance**

Recorre el diff en pantalla 15-20 segundos, sin explicar los bugs todavía —
el punto es que el juez los vea "a simple vista" antes de que la IA los señale.

### Paso 2 — Mostrar el dashboard esperando

Cambia a `localhost:3000`. Si no hay job activo, se ve el **estado vacío**
(ilustración + "Sin PRs analizados todavía"). Narra: *"Esto es lo que ve el equipo
cuando no hay nada corriendo — apenas llegue un PR, aparece aquí solo."*

### Paso 3 — Push/sync del PR → el webhook se dispara

Este es el comando que realmente dispara el pipeline completo — firma HMAC real,
job real en la base de datos, worker real de Celery:

```bash
export GITHUB_WEBHOOK_SECRET=<el valor real de tu .env>

uv run python scripts/e2e_trigger.py \
    --repo kubos777/pr-guardian-demo \
    --repo-id 1310435951 \
    --pr 1 \
    --head-sha be616779374e8553c61472628fca098dd2b15e45 \
    --author kubos777 \
    --title "feat: add user features (orders, user service, shared types, list component)"
```

El script imprime cada transición de estado en la terminal — útil para narrar
en vivo lo que está pasando "por dentro" mientras el dashboard se actualiza.

> ⚠️ **Importante:** este comando publica una review real con comentarios inline
> en el PR de GitHub si llega a `COMPLETED`. Practícalo primero en un ensayo,
> no la primera vez sea en la grabación final — así sabes cuánto tarda y
> qué findings produce exactamente.

### Paso 4 — Dashboard muestra "Analyzing..." en vivo

Vuelve a `localhost:3000` (o déjalo en una ventana dividida junto a la terminal).
Vas a ver:
- El **PRCard** con el PR real, status "Analyzing"
- El **stepper de 4 etapas** avanzando: Fetching Context → Analyzing → Validating → Posting to GitHub
- El indicador "actualizando en vivo" junto a Findings

El dashboard hace polling cada 5s — no hace falta refrescar manualmente.

### Paso 5 — Los findings aparecen (security, style, N+1)

Cuando el job llega a `COMPLETED`, los 3 findings aparecen en el dashboard con
animación de entrada escalonada. Señala en pantalla:
- El de **severidad crítica** (`src/config/secrets.ts`) — secreto hardcodeado
- El de **N+1** (`src/services/userService.ts`)
- El de **estilo** (`src/components/HeavyList.tsx`)

Narra: *"Cada uno de estos tiene su severidad, su archivo y línea exacta, y una
sugerencia concreta — no un comentario genérico."*

### Paso 6 — Ir a GitHub y ver los comments inline

Vuelve a la pestaña del PR en GitHub, refresca. Los comentarios ahora están
publicados **inline**, en la línea exacta del diff. Este es el cierre del loop:
*"El developer nunca tuvo que salir de GitHub para recibir el review."*

---

## 3. Slides — Diagramas Mermaid

Los 3 diagramas viven en `github-integration/ARCHITECTURE_DIAGRAMS.md` — ya
corregidos para reflejar el stack real (antes decían "Claude" y "SQLite" a
secas; ahora dicen Groq+Gemini y Postgres/SQLite, que es lo que corre hoy).

Para exportarlos:
1. Abre **https://mermaid.live**
2. Copia el bloque ` ```mermaid ` a ` ``` ` de cada uno de los 3 diagramas del archivo
3. Exporta como PNG/SVG desde el botón de descarga

Los 3, en orden de aparición en el archivo:
1. **Diagrama de Secuencia** (línea ~13) — el flujo temporal completo, webhook a review publicada
2. **Diagrama de Componentes** (línea ~87) — los módulos del sistema y las 3 capas de persistencia
3. **Diagrama de Estados** (línea ~157) — el ciclo de vida de un job, con reintentos

Cada diagrama en el `.md` ya trae su sección "💡 Por qué importa para ganar" —
son buenas líneas para narrar sobre el diagrama en las slides.

---

## 4. Respuestas Preparadas para Jueces

Escritas para **decirlas en voz alta**, no para leerlas. Practícalas hasta que
te salgan como si te las estuvieran preguntando en una conversación, no como
si estuvieras recitando documentación.

### "¿Cómo evitan alucinaciones?"

> "De dos formas. Primero, cuando le mandamos el diff al modelo, se lo
> marcamos explícitamente como 'esto es información, no son instrucciones' —
> para que no lo confunda con algo que tiene que obedecer. Pero la parte
> importante es la segunda: después de que el modelo responde, nosotros
> mismos revisamos que cada cosa que dice encontrar realmente exista en el
> diff — el archivo, la línea, todo. Si el modelo se inventa algo que no
> está ahí, simplemente lo descartamos antes de que llegue a GitHub. Y esa
> revisión no se reintenta — si falla, falla, no le damos una segunda
> oportunidad al modelo de 'alucinar mejor'."

### "¿Qué pasa si el LLM está caído?"

> "Usamos Groq como proveedor principal porque es rapidísimo y gratis, pero
> si se cae o nos rate-limitea, el sistema solo... cambia a Gemini
> automáticamente. No hay que tocar nada — es literalmente una variable de
> configuración distinta, no código diferente. Y si los dos fallan al mismo
> tiempo, el job no se queda colgado para siempre — se marca como fallido con
> el error guardado, y ya sabemos exactamente qué pasó."

### "¿Cómo escala?"

> "La parte que realmente importa escalar es el análisis, no la recepción
> del webhook — y esa ya está separada. Cuando llega un PR, el webhook
> responde en milisegundos y el trabajo pesado se va a una cola. Entonces
> si mañana nos llegan 100 PRs al mismo tiempo, la respuesta no es reescribir
> nada — es simplemente prender más workers para que jalen de esa cola. Cada
> etapa del análisis además reintenta por su cuenta, así que si falla
> publicar en GitHub no significa que hay que repetir el análisis del LLM
> desde cero."

### "¿Por qué no usar Copilot/CodeRabbit directamente?"

> "Porque esas herramientas revisan sintaxis genérica — las mismas reglas
> para cualquier repo del mundo. Nosotros en cambio buscamos en tus propios
> PRs aprobados y tu propio historial antes de opinar, entonces el feedback
> que te da está basado en cómo *tu equipo* ya decidió resolver ese tipo de
> problema antes, no en una regla de estilo universal. Y para ser honestos —
> esto no es que el sistema 'aprenda solo' con el tiempo, es retrieval sobre
> historial curado. No queremos prometer más de lo que realmente hace."

> ⚠️ **Nota:** no menciones una URL pública de AWS en el pitch a menos que
> esté confirmado funcionando ese mismo día — el deploy (issue #15) sigue en
> progreso y no es parte de lo que se demuestra aquí (ver la sección de
> "Otras cosas a revisar" más abajo).

---

## 5. Grabación — Guía Práctica

No puedo grabar por ti, pero esto es lo que importa tener listo:

- **Herramienta:** OBS Studio (gratis, más control) o Loom (más simple, sube directo).
- **Resolución:** 1920x1080, grabar solo la ventana/pantalla relevante, no el escritorio completo.
- **Audio:** narra en vivo mientras grabas — es más natural que doblar después.
- **Ensaya el Paso 3 al menos una vez** antes de grabar la toma final — necesitas
  saber cuánto tarda el pipeline en tu conexión (típicamente <30s con Groq).
- **Ten un plan B grabado de antemano:** si el demo en vivo falla el día de la
  entrega, un video ya grabado del flujo completo cuenta como cumplimiento del
  criterio de éxito ("hay plan B si la demo en vivo falla").

## 6. Edición y Exportación

- Corta los tiempos muertos de espera del pipeline (el stepper avanzando se
  puede acelerar en edición si tarda más de unos segundos en cámara).
- Agrega overlay de texto solo donde algo no se explica solo en pantalla
  (por ejemplo, un texto fijo con "Findings: security, N+1, style" mientras
  aparecen, si van muy rápido para leerlos en voz).
- Exporta en MP4, verifica el límite de tiempo y tamaño exacto que pida las
  bases del hackathon antes de cortar a "menos de 5 min" a ciegas.

---

## 7. Otras Cosas a Revisar (no son parte del checklist de este issue)

### AWS (issue #15) — no es una dependencia de este demo

El deploy a AWS es un issue **separado**, asignado a kubos777, con criterio de
éxito propio: que los jueces puedan abrir un PR en una URL pública. Ya existe
una rama `ft/terraform-aws` con 3 commits (módulo de Terraform para EC2 + RDS,
documentación de costos) — no está mergeada ni desplegada todavía, pero no
está en cero.

**No dependen de que esa rama termine.** El demo de este script corre 100%
local (Docker Compose + `localhost:3000`) — no necesita ninguna URL pública
para funcionar en la grabación ni en un demo en vivo desde tu laptop. AWS
sería un plus si está listo (los jueces podrían probarlo ellos mismos después
de la presentación), pero no es requisito para nada de lo que está en este
documento.

### Dos bugs reales encontrados hoy que siguen sin arreglarse en código

Documentados como advertencias en la sección 2 de este archivo (con
workaround para grabar), pero vale la pena que alguien los arregle de
verdad después del hackathon, no solo los esquive el día de la demo:

1. **Worker con conexión obsoleta tras idle** — el pool de SQLAlchemy se
   establece antes del fork de Celery; el primer job después de un rato
   idle se pierde silenciosamente. Fix real: recrear el engine en un
   signal `worker_process_init` de Celery, o usar `NullPool`.
2. **Gemini free tier con `limit: 0`** — el fallback a Gemini no funcionó
   en el ensayo. Vale la pena confirmar en Google AI Studio que el free
   tier esté realmente habilitado para esa API key antes del día de la
   entrega — si Groq se satura durante el demo real (con jueces mirando),
   ahora mismo no hay red de seguridad.
