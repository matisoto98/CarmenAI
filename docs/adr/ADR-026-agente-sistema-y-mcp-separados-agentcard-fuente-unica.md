# ADR-026: Agente, sistema y MCP separados; AgentCard fuente única

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 5.14

## Contexto

La v3.0 trataba agente, sistema y servidor MCP como la misma entidad.

## Decisión

Son tres entidades distintas: un agente es un dominio; un sistema posee datos; un servidor MCP es un mecanismo de integración. La AgentCard es la fuente única.

## Consecuencias

Registro, ayuda y política salen del mismo sitio. Un agente puede usar varios MCP y un sistema puede publicar varios.
