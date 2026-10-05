"""Utilidades compartidas para los tests de pdf2notas."""

from __future__ import annotations

from pathlib import Path

import pytest

_DATOS = Path(__file__).parent / "datos"


def requiere_datos(*nombres: str):
    """Decorador de salto: omite el test si alguno de los archivos no existe.

    Los archivos de partitura (victoria.pdf, dulce.pdf, etc.) están excluidos
    del repositorio por copyright. En un clone limpio no estarán presentes,
    y los tests que los necesitan se omiten automáticamente.

    Uso::

        from helpers import requiere_datos

        @requiere_datos("victoria.pdf", "victoria_omr.mxl")
        def test_algo():
            ...
    """
    rutas_faltantes = [n for n in nombres if not (_DATOS / n).exists()]
    if rutas_faltantes:
        return pytest.mark.skip(
            reason="Partitura de prueba no disponible (solo en local): "
            + ", ".join(rutas_faltantes)
        )
    # Todos los archivos existen: no-op identity decorator
    return lambda f: f
