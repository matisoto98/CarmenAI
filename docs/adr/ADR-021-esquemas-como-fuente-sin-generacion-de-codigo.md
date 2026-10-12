# ADR-021: Esquemas como fuente, sin generación de código

- Estado: Aceptado
- Origen: Revisión v2.0
- Referencia: Documento Maestro v4.8, sección 6.5, 8.1

## Contexto

Los contratos se usan desde Python y TypeScript y pueden divergir.

## Decisión

Los esquemas de contracts/ son la fuente única. Python y TypeScript se verifican contra ellos con pruebas; no se genera código.

## Consecuencias

Misma garantía que un generador sin acoplar las cadenas de construcción entre lenguajes.
