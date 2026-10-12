# ADR-031: Ejecución en proceso tras AgentRunnerPort

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 5.13.3

## Contexto

Un sub-agente con bucle propio multiplica las llamadas al modelo, y hoy hay un solo sistema conectado.

## Decisión

Los agentes se ejecutan en el mismo proceso tras AgentRunnerPort, cada uno con su propia llamada de planificación y solo su catálogo. El modo separado se activa al superar el umbral.

## Consecuencias

Simple hoy, separable mañana sin reescribir.
