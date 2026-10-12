# ADR-024: El supervisor no tiene cliente MCP

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 5.14.6, 5.3

## Contexto

La v3.0 inyectaba McpClientPort en el orquestador, lo que convertía a Carmen en un agente más con acceso a todas las herramientas.

## Decisión

McpClientPort no forma parte del grafo de dependencias del supervisor; vive en el ejecutor de agente. La única salida del supervisor hacia los datos es AgentRunnerPort.

## Consecuencias

Separa decidir a quién preguntar de acceder a datos. Lo verifica la prueba de arquitectura (api/tests/architecture/test_layer_rules.py).
