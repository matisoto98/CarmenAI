"""Prompt 0: la capa application se puede importar."""

import importlib

import pytest

pytestmark = pytest.mark.application


def test_application_package_imports() -> None:
    module = importlib.import_module("carmen.application")
    assert module.__name__ == "carmen.application"
