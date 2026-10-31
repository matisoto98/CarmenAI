# ADR-004: Identidad delegada por llamada

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 5.2 (invariante 2), 7.8.1

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Si Carmen consultara con una identidad propia privilegiada, cualquiera vería a través de ella lo que no puede ver directamente.

## Decisión

Carmen propaga la identidad del usuario final en cada llamada (on-behalf-of) y cada servidor decide qué puede ver.

## Consecuencias

Se añade la separación entre rol observado y autorización efectiva. La batería por rol verifica el invariante 2. La excepción de WhatsApp se trata aparte (ADR-038).
