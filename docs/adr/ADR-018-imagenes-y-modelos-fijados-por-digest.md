# ADR-018: Imágenes y modelos fijados por digest

- Estado: Aceptado
- Origen: Revisión v2.0 (C6)
- Referencia: Documento Maestro v4.8, sección 2.6, 4.3

## Contexto

La v1.0 fijaba una imagen con la etiqueta latest en una infraestructura que se declara reproducible.

## Decisión

Todas las imágenes y modelos se fijan por digest en ops/versions.env, con procedimiento documentado de actualización.

## Consecuencias

El perfil prod no arranca con marcadores sin fijar. Carmen compara al arrancar el digest servido con MODEL_DIGEST.
