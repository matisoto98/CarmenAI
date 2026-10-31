# ADR-013: Parcialidad en el protocolo, no en el código HTTP

- Estado: Aceptado
- Origen: Revisión v2.0 (C1)
- Referencia: Documento Maestro v4.8, sección 2.6, 6.5

## Contexto

La v1.0 definía la respuesta parcial como HTTP 206, pero el código de estado ya se ha enviado al abrir el stream.

## Decisión

La parcialidad se expresa en el protocolo: eventos warning durante el stream y campos partial y missing_systems en done. El HTTP es siempre 200 si el stream llegó a abrirse.

## Consecuencias

El frontend interpreta la parcialidad desde los eventos.
