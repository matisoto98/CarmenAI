"""Prompt 0: el escáner de secretos de pre-commit y CI bloquea claves con forma de token.

Los secretos de prueba se construyen en tiempo de ejecución para que este fichero
no contenga ninguno literal.
"""

import base64
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE = REPO_ROOT / ".secrets.baseline"


def _b64url(data: dict[str, str | int]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _fake_jwt() -> str:
    header = _b64url({"alg": "HS256", "typ": "JWT"})
    payload = _b64url({"sub": "carmen-test", "iat": 1760000000})
    return f"{header}.{payload}.{'s' * 43}"


def _fake_github_token() -> str:
    return "ghp_" + "a1" * 18


def _fake_aws_key() -> str:
    return "AKIA" + "Z7" * 8


def _scan(path: Path) -> subprocess.CompletedProcess[str]:
    hook = shutil.which("detect-secrets-hook")
    assert hook is not None, "detect-secrets no está instalado en el entorno de desarrollo"
    return subprocess.run(
        [hook, "--baseline", str(BASELINE), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "secret_factory",
    [_fake_jwt, _fake_github_token, _fake_aws_key],
    ids=["jwt", "github-token", "aws-key"],
)
def test_scanner_blocks_token_shaped_secret(
    tmp_path: Path, secret_factory: Callable[[], str]
) -> None:
    leaked = tmp_path / "carmen.env"
    leaked.write_text(f"WHATSAPP_ACCESS_TOKEN={secret_factory()}\n", encoding="utf-8")
    result = _scan(leaked)
    assert result.returncode == 1, result.stdout + result.stderr


def test_scanner_accepts_secret_names_without_values(tmp_path: Path) -> None:
    example = tmp_path / "secrets.example.env"
    example.write_text("AEMET_API_KEY=\nWHATSAPP_APP_SECRET=\n", encoding="utf-8")
    result = _scan(example)
    assert result.returncode == 0, result.stdout + result.stderr
