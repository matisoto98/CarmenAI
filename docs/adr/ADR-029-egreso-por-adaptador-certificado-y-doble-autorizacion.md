# ADR-029: Egreso por adaptador certificado y doble autorización

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 5.15

## Contexto

Autorizar un agente no debe autorizar la exportación de información.

## Decisión

Ningún agente tiene acceso general a la red. Salir al exterior exige un adaptador certificado y dos autorizaciones independientes: sobre el agente y la acción, y sobre el dato y el destino.

## Consecuencias

Ningún dato sale sin dos permisos registrados. La denegación por defecto se prueba aunque en v1 no haya agentes externos.
