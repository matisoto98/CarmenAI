# ADR-041: Tiempo solo de AEMET e IPMA

- Estado: Aceptado
- Origen: v4.4
- Referencia: Documento Maestro v4.8, sección 5.18.4

## Contexto

El tiempo es información crítica para mantenimiento.

## Decisión

agent.meteo usa solo fuentes públicas oficiales: AEMET OpenData en España e IPMA en Portugal. Nunca agregadores ni webs, aunque no pidan clave.

## Consecuencias

La clave de AEMET caduca y tiene aviso automático (5.18.9).
