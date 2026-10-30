"""Persistencia en PostgreSQL por agregado (7.2): motor, tipos, migraciones y repositorios.

Cada agregado vive en su paquete con tres módulos: tables.py (tablas de SQLAlchemy Core),
mappers.py (tabla ⇄ dominio, explícito) y repository.py (implementa el puerto). Ningún
repositorio abre transacciones: las abre el caso de uso con la unidad de trabajo de engine.py.
"""
