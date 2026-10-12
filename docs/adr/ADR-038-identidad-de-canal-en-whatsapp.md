# ADR-038: Identidad de canal en WhatsApp

- Estado: Propuesto (pendiente P17)
- Origen: v4.3
- Referencia: Documento Maestro v4.8, sección 5.17.5

## Contexto

WhatsApp no entrega identidad de Entra: Meta da un número y, en grupos, un identificador de grupo. El invariante 2 no se puede cumplir tal cual.

## Decisión

Excepción acotada: el Principal es el número (1:1) o el grupo; el acceso a VigIA usa una identidad técnica del canal, de solo lectura, que solo ejecuta planes de preguntas ACTIVAS del catálogo. Un plan que no procede de una plantilla activa se rechaza antes de salir.

## Consecuencias

Requiere aprobación de Dirección y del responsable de VigIA (P17). Sin ella no se responde con datos de VigIA por WhatsApp.
