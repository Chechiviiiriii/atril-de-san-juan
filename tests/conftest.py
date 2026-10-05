"""Configuración global de pytest para pdf2notas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Añadir la raíz del proyecto y el directorio tests al path de Python
_RAIZ = Path(__file__).parent.parent
_TESTS = Path(__file__).parent
for _p in (_RAIZ, _TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def pytest_configure(config):
    """Registra marcadores personalizados."""
    config.addinivalue_line(
        "markers",
        "lento: tests que requieren Audiveris y/o MuseScore (tardan minutos).",
    )
