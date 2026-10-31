"""Errores del simulado y cómo llegan al cliente.

- InvalidParamsError: error JSON-RPC -32602 (argumentos que no cumplen el inputSchema, herramienta
  desconocida, periodo fuera del tope).
- ToolError: resultado de tools/call con isError=true; la herramienta existe y falló.
- ForbiddenError: HTTP 403; el rol del token no permite la herramienta o el recurso.
- UnauthorizedError: HTTP 401; falta el token o no es uno de los simulados.
"""


class MockError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidParamsError(MockError):
    code = -32602


class ToolError(MockError):
    pass


class ForbiddenError(MockError):
    status = 403


class UnauthorizedError(MockError):
    status = 401
