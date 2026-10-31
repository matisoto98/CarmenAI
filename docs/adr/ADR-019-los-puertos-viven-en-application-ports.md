# ADR-019: Los puertos viven en application/ports

- Estado: Aceptado
- Origen: Revisión v2.0
- Referencia: Documento Maestro v4.8, sección 5.3

## Contexto

La revisión proponía un paquete ports de primer nivel.

## Decisión

Se descarta: en arquitectura hexagonal el puerto lo define quien lo necesita. Los puertos viven en application/ports/.

## Consecuencias

Un paquete separado se convertiría en vertedero de interfaces sin dueño.
