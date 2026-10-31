# ADR-020: El arnés de evaluación fuera del runtime

- Estado: Aceptado
- Origen: Revisión v2.0
- Referencia: Documento Maestro v4.8, sección 5.5, 7.3

## Contexto

Acoplar la aplicación a la persistencia de evaluaciones contamina el núcleo con infraestructura de pruebas.

## Decisión

El arnés de evaluación vive en eval/, con su propio esquema y acceso a datos, fuera de api/src/.

## Consecuencias

No hay EvaluationRepository en el runtime.
