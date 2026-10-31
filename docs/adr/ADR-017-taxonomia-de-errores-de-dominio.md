# ADR-017: Taxonomía de errores de dominio

- Estado: Aceptado
- Origen: Revisión v2.0 (C5)
- Referencia: Documento Maestro v4.8, sección 2.6, 6.6

## Contexto

Los servicios de aplicación devolvían códigos HTTP, lo que los acoplaba a presentación.

## Decisión

Taxonomía única de errores de dominio. La traducción a HTTP y a SSE vive exclusivamente en presentación.

## Consecuencias

presentation/errors es el único sitio que traduce a HTTP.
