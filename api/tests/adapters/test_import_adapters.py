"""Prompt 0: la capa adapters se puede importar."""

import importlib

import pytest

pytestmark = pytest.mark.adapters


def test_adapters_package_imports() -> None:
    module = importlib.import_module("carmen.adapters")
    assert module.__name__ == "carmen.adapters"
