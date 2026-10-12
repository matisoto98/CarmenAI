"""Prompt 1: los ADR están indexados, numerados sin colisión y sin huecos."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

ADR_DIR = Path(__file__).resolve().parents[3] / "docs" / "adr"
ADR_FILE = re.compile(r"^ADR-(\d{3})-[a-z0-9-]+\.md$")
RESERVED = {34, 35}


def _adr_files() -> list[Path]:
    return sorted(p for p in ADR_DIR.glob("ADR-*.md"))


def test_adr_file_names_follow_the_pattern() -> None:
    bad = [p.name for p in _adr_files() if not ADR_FILE.match(p.name)]
    assert not bad


def test_adr_numbers_are_unique_and_consecutive() -> None:
    numbers = [int(p.name[4:7]) for p in _adr_files()]
    assert len(numbers) == len(set(numbers)), "dos ADR comparten número"
    assert numbers == list(range(1, len(numbers) + 1)), "hay huecos en la numeración"


def test_every_adr_is_in_the_index_and_every_link_exists() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((ADR-\d{3}-[a-z0-9-]+\.md)\)", index))
    files = {p.name for p in _adr_files()}
    assert linked == files


def test_each_adr_title_matches_its_number() -> None:
    for path in _adr_files():
        number = path.name[4:7]
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith(f"# ADR-{number}: "), path.name


def test_reserved_adrs_are_marked() -> None:
    for path in _adr_files():
        number = int(path.name[4:7])
        text = path.read_text(encoding="utf-8")
        assert ("Estado: RESERVADO" in text) == (number in RESERVED), path.name
