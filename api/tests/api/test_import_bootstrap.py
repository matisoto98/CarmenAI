"""Prompt 0: la capa bootstrap se puede importar."""

import importlib

import pytest

pytestmark = pytest.mark.bootstrap


def test_bootstrap_package_imports() -> None:
    module = importlib.import_module("carmen.bootstrap")
    assert module.__name__ == "carmen.bootstrap"
