# ADR-042: Acceso por directorio activo editable con salvaguardas

- Estado: Aceptado
- Origen: v4.4
- Referencia: Documento Maestro v4.8, sección 5.18.6, 7.8.1

## Contexto

La correspondencia grupo→rol pasa a editarse en el panel, y un error puede dejar a todos fuera.

## Decisión

El acceso se configura en el panel con salvaguardas: probar antes de guardar, doble confirmación de ADMIN, versiones con vuelta atrás y sin rol por defecto.

## Consecuencias

Un error de configuración no puede dejar a todos fuera.
