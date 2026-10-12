"""Prompt 0: la capa domain se puede importar."""

import importlib

import pytest

pytestmark = pytest.mark.domain


def test_domain_package_imports() -> None:
    module = importlib.import_module("carmen.domain")
    assert module.__name__ == "carmen.domain"
