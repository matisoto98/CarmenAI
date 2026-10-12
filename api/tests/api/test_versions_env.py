"""Prompt 0: versions.env no admite marcadores en prod; en dev sí."""

from pathlib import Path

import pytest

from carmen.bootstrap.versions import (
    Profile,
    UnpinnedVersionError,
    ensure_pinned,
    load_versions,
    parse_versions,
)

pytestmark = pytest.mark.bootstrap

REPO_VERSIONS = Path(__file__).resolve().parents[3] / "ops" / "versions.env"

PINNED = "MODEL_ID=qwen3.5:9b\nOLLAMA_IMAGE=ollama/ollama@sha256:" + "a" * 64 + "\n"


@pytest.mark.parametrize("marker", ["<digest>", "<commit>", "<digest de ollama show>"])
def test_prod_rejects_placeholder(marker: str) -> None:
    versions = parse_versions(f"MODEL_DIGEST={marker}\nMODEL_ID=qwen3.5:9b\n")
    with pytest.raises(UnpinnedVersionError) as excinfo:
        ensure_pinned(versions, Profile.PROD)
    assert excinfo.value.keys == ["MODEL_DIGEST"]


@pytest.mark.parametrize("profile", [Profile.DEV, Profile.DEV_OLLAMA])
def test_dev_profiles_accept_placeholder(profile: Profile) -> None:
    ensure_pinned(parse_versions("MODEL_DIGEST=<digest>\n"), profile)


def test_prod_accepts_fully_pinned_versions() -> None:
    ensure_pinned(parse_versions(PINNED), Profile.PROD)


def test_inline_comments_and_blank_lines_are_ignored() -> None:
    versions = parse_versions("# cabecera\n\nMODEL_NUM_CTX=16384 # Ollama trunca\n")
    assert versions == {"MODEL_NUM_CTX": "16384"}


def test_line_without_equals_is_rejected() -> None:
    with pytest.raises(ValueError, match="sin '='"):
        parse_versions("MODEL_ID qwen3.5:9b\n")


def test_repository_versions_env_loads_in_dev() -> None:
    versions = load_versions(REPO_VERSIONS)
    assert versions["MODEL_ID"] == "qwen3.5:9b"
    assert versions["EMBED_DIM"] == "1024"
    ensure_pinned(versions, Profile.DEV)
