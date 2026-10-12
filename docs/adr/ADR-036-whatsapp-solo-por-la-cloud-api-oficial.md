# ADR-036: WhatsApp solo por la Cloud API oficial

- Estado: Aceptado
- Origen: v4.3
- Referencia: Documento Maestro v4.8, sección 5.17.2

## Contexto

Automatizar WhatsApp Web expone sesiones de usuario y arriesga el bloqueo del número. El número de Carmen no puede entrar en el grupo IT-Mantenimiento actual por la vía oficial.

## Decisión

WhatsApp solo por la Cloud API oficial de Meta. Se crea un grupo nuevo por la API y se migra.

## Consecuencias

No se automatiza WhatsApp Web ni se conecta Carmen al grupo actual.
