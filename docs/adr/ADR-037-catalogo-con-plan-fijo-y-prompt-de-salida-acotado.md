# ADR-037: Catálogo con plan fijo y prompt de salida acotado

- Estado: Aceptado
- Origen: v4.3
- Referencia: Documento Maestro v4.8, sección 5.17.7

## Contexto

Un modelo de 9B no garantiza respuestas reproducibles a pregunta libre por un canal externo.

## Decisión

En WhatsApp solo se responden preguntas de catálogo, cada una con plan fijo validado al guardar y prompt de salida de máximo 2.000 caracteres, configurables desde un CRUD.

## Consecuencias

Respuestas reproducibles y al alcance de un modelo de 9B. Altas sin tocar código.
