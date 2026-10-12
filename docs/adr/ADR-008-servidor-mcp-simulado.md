# ADR-008: Servidor MCP simulado

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 4.6.2, 9.1

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Desarrollar contra los servidores reales exige VPN y hace las pruebas no deterministas.

## Decisión

Existe un servidor MCP simulado y determinista, conforme al contrato.

## Consecuencias

Asciende al Prompt 9 y comparte la batería de contrato con los servidores reales. CI nunca usa VigIA real.
