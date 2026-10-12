# Registro de decisiones de arquitectura

Toda desviación del Documento Maestro se registra como un ADR nuevo, con el siguiente número libre.
Un ADR aceptado no se edita: se sustituye con otro que lo cite.

- ADR-001 a ADR-012: decisiones de la v1.0. **Texto reconstruido** en la v4.8 a partir de la matriz de
  trazabilidad (15.12); el original no está en el paquete de entrega.
- ADR-013 a ADR-021: revisión de la v2.0 (correcciones C1 a C6 de 2.6 y decisiones de capa).
- ADR-022 y ADR-023: identidad visual y contenido documental.
- ADR-024 a ADR-042: tabla de 5.19. ADR-034 y ADR-035 están RESERVADOS (pendientes P11 y P13).

| ADR | Decisión | Estado | Sección |
|---|---|---|---|
| [ADR-001](ADR-001-los-cinco-invariantes.md) | Los cinco invariantes | Aceptado | 5.2 |
| [ADR-002](ADR-002-carmen-como-sistema-independiente.md) | Carmen como sistema independiente | Aceptado | 2.1, 15.12 |
| [ADR-003](ADR-003-host-mcp-sin-acceso-a-bases-ajenas.md) | Host MCP sin acceso a bases ajenas | Aceptado | 2.1, 5.2 (invariante 3) |
| [ADR-004](ADR-004-identidad-delegada-por-llamada.md) | Identidad delegada por llamada | Aceptado | 5.2 (invariante 2), 7.8.1 |
| [ADR-005](ADR-005-enrutado-en-dos-etapas-con-un-modelo.md) | Enrutado en dos etapas con un modelo | Aceptado | 5.7 |
| [ADR-006](ADR-006-glosario-con-conflictos-declarados.md) | Glosario con conflictos declarados | Aceptado | 5.2 (invariante 4), 6.11 |
| [ADR-007](ADR-007-solo-lectura-y-cinco-puertas-de-escritura.md) | Solo lectura y cinco puertas de escritura | Aceptado | 2.2.2, 5.10 |
| [ADR-008](ADR-008-servidor-mcp-simulado.md) | Servidor MCP simulado | Aceptado | 4.6.2, 9.1 |
| [ADR-009](ADR-009-infraestructura-azure-y-dimensionado.md) | Infraestructura Azure y dimensionado | Aceptado | 4, 15.12 |
| [ADR-010](ADR-010-memoria-de-planes-no-de-resultados.md) | Memoria de planes, no de resultados | Aceptado | 6.10.6 |
| [ADR-011](ADR-011-propiedades-de-calidad-como-baterias-de-prueba.md) | Propiedades de calidad como baterías de prueba | Aceptado | 10.3, 10.5 |
| [ADR-012](ADR-012-k-de-n-inestabilidad-linea-base-y-modo-sombra.md) | k de N, inestabilidad, línea base y modo sombra | Aceptado | 10.2, 10.6, 10.7 |
| [ADR-013](ADR-013-parcialidad-en-el-protocolo-no-en-el-codigo-http.md) | Parcialidad en el protocolo, no en el código HTTP | Aceptado | 2.6, 6.5 |
| [ADR-014](ADR-014-dimension-del-embedding-fija-en-1024.md) | Dimensión del embedding fija en 1024 | Aceptado | 2.6, 4.3 |
| [ADR-015](ADR-015-queryplan-con-pasos-dependencias-y-paralelismo.md) | QueryPlan con pasos, dependencias y paralelismo | Aceptado | 2.6, 6.2 |
| [ADR-016](ADR-016-sobre-estructurado-con-hechos-identificables.md) | Sobre estructurado con hechos identificables | Aceptado | 2.6, 6.3, 6.4 |
| [ADR-017](ADR-017-taxonomia-de-errores-de-dominio.md) | Taxonomía de errores de dominio | Aceptado | 2.6, 6.6 |
| [ADR-018](ADR-018-imagenes-y-modelos-fijados-por-digest.md) | Imágenes y modelos fijados por digest | Aceptado | 2.6, 4.3 |
| [ADR-019](ADR-019-los-puertos-viven-en-application-ports.md) | Los puertos viven en application/ports | Aceptado | 5.3 |
| [ADR-020](ADR-020-el-arnes-de-evaluacion-fuera-del-runtime.md) | El arnés de evaluación fuera del runtime | Aceptado | 5.5, 7.3 |
| [ADR-021](ADR-021-esquemas-como-fuente-sin-generacion-de-codigo.md) | Esquemas como fuente, sin generación de código | Aceptado | 6.5, 8.1 |
| [ADR-022](ADR-022-identidad-visual-geometrica-sin-rostro.md) | Identidad visual geométrica, sin rostro | Aceptado | 5.12 |
| [ADR-023](ADR-023-contenido-documental-y-procedimental.md) | Contenido documental y procedimental | Aceptado | 6.9 |
| [ADR-024](ADR-024-el-supervisor-no-tiene-cliente-mcp.md) | El supervisor no tiene cliente MCP | Aceptado | 5.14.6, 5.3 |
| [ADR-025](ADR-025-modo-de-respuesta-antes-de-cualquier-plan.md) | Modo de respuesta antes de cualquier plan | Aceptado | 2.3.2 |
| [ADR-026](ADR-026-agente-sistema-y-mcp-separados-agentcard-fuente-unica.md) | Agente, sistema y MCP separados; AgentCard fuente única | Aceptado | 5.14 |
| [ADR-027](ADR-027-visibilidad-con-denegacion-por-defecto.md) | Visibilidad con denegación por defecto | Aceptado | 5.14.4, 7.9 |
| [ADR-028](ADR-028-delegationplan-y-queryplan-cruce-solo-con-mapa.md) | DelegationPlan y QueryPlan; cruce solo con mapa | Aceptado | 6.11, 6.12 |
| [ADR-029](ADR-029-egreso-por-adaptador-certificado-y-doble-autorizacion.md) | Egreso por adaptador certificado y doble autorización | Aceptado | 5.15 |
| [ADR-030](ADR-030-ciclo-de-vida-y-certificacion-previa.md) | Ciclo de vida y certificación previa | Aceptado | 7.11 |
| [ADR-031](ADR-031-ejecucion-en-proceso-tras-agentrunnerport.md) | Ejecución en proceso tras AgentRunnerPort | Aceptado | 5.13.3 |
| [ADR-032](ADR-032-aprobacion-humana-como-protocolo-un-salto-de-re-delegacion.md) | Aprobación humana como protocolo; un salto de re-delegación | Aceptado | 6.12.5, 6.12.6 |
| [ADR-033](ADR-033-qwen3-5-9b-q8-0-y-bge-m3-en-ollama-sobre-la-t4-compartida.md) | Qwen3.5-9B Q8_0 y bge-m3 en Ollama sobre la T4 compartida | Aceptado | 4.1 |
| [ADR-034](ADR-034-identidad-hacia-vigia.md) | Identidad hacia VigIA | RESERVADO | 7.8.1 |
| [ADR-035](ADR-035-host-de-la-aplicacion.md) | Host de la aplicación | RESERVADO | 4.2 |
| [ADR-036](ADR-036-whatsapp-solo-por-la-cloud-api-oficial.md) | WhatsApp solo por la Cloud API oficial | Aceptado | 5.17.2 |
| [ADR-037](ADR-037-catalogo-con-plan-fijo-y-prompt-de-salida-acotado.md) | Catálogo con plan fijo y prompt de salida acotado | Aceptado | 5.17.7 |
| [ADR-038](ADR-038-identidad-de-canal-en-whatsapp.md) | Identidad de canal en WhatsApp | Propuesto (pendiente P17) | 5.17.5 |
| [ADR-039](ADR-039-autorregistro-con-validacion.md) | Autorregistro con validación | Aceptado | 5.18.1 |
| [ADR-040](ADR-040-espejo-del-grupo-activo-por-defecto.md) | Espejo del grupo activo por defecto | Aceptado | 5.18.3 |
| [ADR-041](ADR-041-tiempo-solo-de-aemet-e-ipma.md) | Tiempo solo de AEMET e IPMA | Aceptado | 5.18.4 |
| [ADR-042](ADR-042-acceso-por-directorio-activo-editable-con-salvaguardas.md) | Acceso por directorio activo editable con salvaguardas | Aceptado | 5.18.6, 7.8.1 |
| [ADR-043](ADR-043-concreciones-del-dominio-nucleo.md) | Concreciones del dominio núcleo | Aceptado | 6.2, 6.3, 6.6, 6.9.2 |
