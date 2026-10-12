# ADR-003: Host MCP sin acceso a bases ajenas

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 2.1, 5.2 (invariante 3)

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Acceder directamente a las bases de datos de otros sistemas acumula privilegios en Carmen y duplica su lógica de negocio.

## Decisión

Carmen es host MCP. Cada sistema entrega un servidor MCP que agrega junto a sus datos y aplica su propio control de acceso. Carmen no tiene credenciales de ninguna base ajena.

## Consecuencias

Se refuerza con una prueba estática de dependencias. Toda agregación ocurre en el servidor propietario del dato.
