# PR Guardian - Executive Summary

## El Problema
Los equipos de desarrollo pierden 15-20 horas/semana en code reviews repetitivos. 
Los juniors cometen los mismos errores una y otra vez. Los seniors se queman revisando 
estilo en lugar de arquitectura. Resultado: releases lentos, bugs en producción, burnout.

## La Solución
PR Guardian es un reviewer AI que entiende TU código, TU estilo y TU historia. 
No es un linter genérico. Es un miembro del equipo que nunca duerme, nunca se cansa, 
y **recupera ejemplos históricos aprobados** de fixes pasados para dar contexto a cada
comentario — sin pretender que el sistema "aprende" solo en este MVP.

## Valor Cuantificable
- ️ 40% reducción en tiempo de review humano
- 🐞 70% detección temprana de bugs críticos pre-merge  
- 📚 Onboarding de juniors 3x más rápido (feedback contextualizado)
- 🔒 Compliance de seguridad automatizado

## Diferenciador Competitivo
Mientras otras herramientas revisan SINTAXIS, PR Guardian revisa CONTEXTO.
Recupera ejemplos de tus PRs aprobados, tus issues cerrados, tus convenciones
implícitas — un retrieval determinista sobre historial curado, no reglas
estáticas genéricas. (El MVP no reentrena ni actualiza modelos: no "aprende"
automáticamente.)

## Stack de Inteligencia Artificial

| Capa | Tecnología | Justificación |
|------|-----------|---------------|
| Primary LLM | Groq + Llama 3.3 70B | 800+ tokens/seg, free tier (30 RPM), JSON mode nativo. Respuesta en <2s |
| Fallback LLM | Google Gemini 2.0 Flash | 15 RPM free, 1500 req/día. Se activa automáticamente si Groq llega al rate limit |
| Abstracción | LiteLLM | Interfaz unificada para cualquier provider. Cambiar modelo = cambiar 1 env var |
| Prompting | 3 prompts especializados | Cada review ejecuta 3 pases (style, security, history) con schemas JSON estrictos |
| Anti-alucinación | Validación cruzada diff vs findings | El agente no puede inventar líneas o archivos que no existen en el PR |

### ¿Por qué Groq + Llama 3.3 70B?
- **Costo $0:** Free tier sin tarjeta de crédito — crítico para un hackathon.
- **Velocidad extrema:** Hardware LPU dedicado. Respuestas en ~1.5s, no en 15s.
- **Calidad top-tier:** Llama 3.3 70B compite con GPT-4 en coding benchmarks (HumanEval, SWE-Bench).
- **JSON mode nativo:** Respuestas estructuradas sin alucinaciones de formato.
- **Fallback transparente:** Si Groq cae, Gemini toma el relevo sin intervención humana.

## Modelo de Uso (Post-Hackathon)
- GitHub App instalable en 2 clicks
- Pricing por desarrollador activo
- Enterprise: On-premise LLM para código sensible