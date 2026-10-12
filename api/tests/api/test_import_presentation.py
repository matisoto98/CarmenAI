"""Prompt 0: la capa presentation se puede importar."""

import importlib

import pytest

pytestmark = pytest.mark.api


def test_presentation_package_imports() -> None:
    module = importlib.import_module("carmen.presentation")
    assert module.__name__ == "carmen.presentation"
