"""Puente stdio → HTTP para probar el transporte stdio de la batería sin el MCP real (Prompt 10).

Hace con mcp-mock lo que vigia-mcp-bridge.mjs hace con VigIA (4.6.6): lee mensajes JSON-RPC por
stdin, uno por línea, los reenvía por HTTP transmitible poniendo él la credencial y escribe las
respuestas por stdout, una por línea. El cliente nunca ve el token: el puente lo toma de
MCP_BRIDGE_TOKEN y no lo escribe en ninguna parte.

    MCP_BRIDGE_TOKEN=sim:ADMIN:usr_contract python stdio_bridge.py http://127.0.0.1:8765/vigia/mcp

Solo biblioteca estándar y ningún import del repositorio: se lanza como proceso aparte.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from http import HTTPStatus

PROTOCOL_VERSION = "2025-11-25"
BRIDGE_HTTP_ERROR = -32001


class Bridge:
    def __init__(self, url: str, token: str | None) -> None:
        self.url = url
        self.token = token
        self.session_id: str | None = None

    def headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def forward(self, line: str) -> list[str]:
        """Reenvía un mensaje y devuelve las líneas que hay que escribir por stdout."""
        message = json.loads(line)
        message_id = message.get("id") if isinstance(message, dict) else None
        request = urllib.request.Request(
            self.url, data=line.encode(), method="POST", headers=self.headers()
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.session_id = session
                if response.status == HTTPStatus.ACCEPTED:
                    return []
                content_type = response.headers.get("Content-Type", "")
                text = response.read().decode()
        except urllib.error.HTTPError as error:
            with error:
                detail = error.read().decode(errors="replace")[:200]
            if message_id is None:
                return []
            failure = {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": BRIDGE_HTTP_ERROR, "message": f"HTTP {error.code}: {detail}"},
            }
            return [json.dumps(failure, ensure_ascii=False)]
        if "text/event-stream" in content_type:
            return [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        return [json.dumps(json.loads(text), ensure_ascii=False)]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("uso: stdio_bridge.py <url-mcp>\n")
        return 2
    bridge = Bridge(argv[0], os.environ.get("MCP_BRIDGE_TOKEN"))
    for line in sys.stdin:
        if not line.strip():
            continue
        for reply in bridge.forward(line):
            sys.stdout.write(reply + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
