"""Tests para el módulo verificacion.py."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from helpers import requiere_datos

# ---------------------------------------------------------------------------
# Datos de prueba simulados (sin PDF)
# ---------------------------------------------------------------------------

DATOS = Path(__file__).parent / "datos"


def _victoria_partitura():
    """Devuelve la partitura OMR de Victoria parseada."""
    warnings.filterwarnings("ignore")
    from music21 import converter  # type: ignore[import]
    return converter.parse(str(DATOS / "victoria_omr.mxl"))


def _dulce_partitura():
    """Devuelve la partitura OMR de Dulce parseada."""
    warnings.filterwarnings("ignore")
    from music21 import converter  # type: ignore[import]
    return converter.parse(str(DATOS / "dulce_omr.mxl"))


def _sintetica_partitura():
    """Devuelve la partitura sintética parseada."""
    warnings.filterwarnings("ignore")
    from music21 import converter  # type: ignore[import]
    return converter.parse(str(DATOS / "sintetica.musicxml"))


# ---------------------------------------------------------------------------
# Tests unitarios con datos simulados (no necesitan PDF)
# ---------------------------------------------------------------------------

class TestVerificacionSimulada:
    """Tests unitarios del módulo de comparación con datos simulados."""

    def test_sin_diferencias(self):
        """Sin diferencias entre PDF y OMR no debe haber avisos."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [21, 26, 22]
            v.contar_notas_omr = lambda p: [21, 26, 22]
            v.rango_compases_sistema = lambda p: [(1, 10), (11, 20), (21, 30)]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert resultado.comprobado is True
            assert resultado.avisos == []
            assert resultado.total_pdf == 69
            assert resultado.total_omr == 69
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango

    def test_con_diferencias(self):
        """Diferencias en sistemas individuales generan avisos correctos."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [23, 30, 34, 42, 29, 34, 34, 26]
            v.contar_notas_omr = lambda p: [23, 30, 33, 40, 25, 30, 34, 26]
            v.rango_compases_sistema = lambda p: [
                (0, 17), (18, 28), (29, 37), (38, 45),
                (46, 55), (56, 64), (65, 71), (72, 77)
            ]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert resultado.comprobado is True
            assert len(resultado.avisos) == 4
            # Sistema 3 (índice 2): 34 vs 33 → falta 1
            assert any("Línea 3" in a and "falta 1" in a for a in resultado.avisos)
            # Sistema 4 (índice 3): 42 vs 40 → faltan 2
            assert any("Línea 4" in a and "faltan 2" in a for a in resultado.avisos)
            # Sistema 5 (índice 4): 29 vs 25 → faltan 4
            assert any("Línea 5" in a and "faltan 4" in a for a in resultado.avisos)
            # Sistema 6 (índice 5): 34 vs 30 → faltan 4
            assert any("Línea 6" in a and "faltan 4" in a for a in resultado.avisos)
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango

    def test_sobra_nota(self):
        """Cuando hay más notas en OMR que en el PDF, el mensaje dice 'sobra'."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [10, 5]
            v.contar_notas_omr = lambda p: [10, 8]
            v.rango_compases_sistema = lambda p: [(1, 5), (6, 10)]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert len(resultado.avisos) == 1
            assert "sobra" in resultado.avisos[0] or "sobran" in resultado.avisos[0]
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango

    def test_sistemas_diferentes_aviso_general(self):
        """Si el número de sistemas difiere, un aviso general y comprobado=True."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [20, 30, 25]  # 3 sistemas
            v.contar_notas_omr = lambda p: [20, 30, 25, 15]  # 4 sistemas
            v.rango_compases_sistema = lambda p: [(1, 5), (6, 10), (11, 15), (16, 20)]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert resultado.comprobado is True
            assert len(resultado.avisos) == 1
            assert "3" in resultado.avisos[0] and "4" in resultado.avisos[0]
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango

    def test_pdf_no_vectorial_comprobado_falso(self):
        """Si el PDF no es vectorial, comprobado=False y sin avisos."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr

        try:
            v.contar_cabezas_pdf = lambda p: None
            v.contar_notas_omr = lambda p: [20, 30]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert resultado.comprobado is False
            assert resultado.avisos == []
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr

    def test_aviso_falta_una_nota_singular(self):
        """El mensaje usa 'falta 1 nota' en singular."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [10]
            v.contar_notas_omr = lambda p: [9]
            v.rango_compases_sistema = lambda p: [(1, 8)]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert len(resultado.avisos) == 1
            assert "falta 1" in resultado.avisos[0]
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango

    def test_aviso_sobra_una_nota_singular(self):
        """El mensaje usa 'sobra 1 nota' en singular."""
        import atril.verificacion as v
        original_pdf = v.contar_cabezas_pdf
        original_omr = v.contar_notas_omr
        original_rango = v.rango_compases_sistema

        try:
            v.contar_cabezas_pdf = lambda p: [9]
            v.contar_notas_omr = lambda p: [10]
            v.rango_compases_sistema = lambda p: [(1, 8)]
            resultado = v.verificar(Path("fake.pdf"), None)
            assert len(resultado.avisos) == 1
            assert "sobra 1" in resultado.avisos[0]
        finally:
            v.contar_cabezas_pdf = original_pdf
            v.contar_notas_omr = original_omr
            v.rango_compases_sistema = original_rango


def _make_measures(n, note_counts):
    """Helper: crea medidas falsas para tests simulados."""
    return []


# ---------------------------------------------------------------------------
# Tests con PDFs y MXL reales
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl", "dulce.pdf", "dulce_omr.mxl")
class TestConPDFsReales:
    """Tests de integración usando los PDFs reales de la raíz del proyecto."""

    def test_victoria_sin_avisos(self):
        """Victoria: todas las líneas coinciden → sin avisos."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import verificar, contar_cabezas_pdf, contar_notas_omr

        pdf = DATOS / "victoria.pdf"
        partitura = _victoria_partitura()

        cabezas = contar_cabezas_pdf(pdf)
        assert cabezas is not None, "Victoria debe ser vectorial con cabezas reconocibles"

        notas = contar_notas_omr(partitura)
        assert len(cabezas) == len(notas), (
            f"Victoria: sistemas PDF={len(cabezas)} vs OMR={len(notas)}"
        )

        resultado = verificar(pdf, partitura)
        assert resultado.comprobado is True
        assert resultado.avisos == [], (
            f"Victoria no debe tener avisos, pero tiene: {resultado.avisos}"
        )

    def test_victoria_cabezas_por_sistema(self):
        """Victoria: conteos por sistema exactos."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import contar_cabezas_pdf

        cabezas = contar_cabezas_pdf(DATOS / "victoria.pdf")
        assert cabezas == [21, 26, 22, 38, 36, 24, 18], (
            f"Victoria cabezas esperadas [21,26,22,38,36,24,18], obtenidas {cabezas}"
        )

    def test_dulce_con_avisos_en_lineas_correctas(self):
        """Dulce: avisos exactamente en las líneas 3, 4, 5 y 6."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import verificar

        pdf = DATOS / "dulce.pdf"
        partitura = _dulce_partitura()

        resultado = verificar(pdf, partitura)

        assert resultado.comprobado is True, "Dulce debe ser comprobable"
        lineas_con_aviso = []
        for aviso in resultado.avisos:
            for n in range(1, 9):
                if f"Línea {n}" in aviso:
                    lineas_con_aviso.append(n)
        assert sorted(lineas_con_aviso) == [3, 4, 5, 6], (
            f"Dulce debe tener avisos en líneas 3,4,5,6; got avisos: {resultado.avisos}"
        )

    def test_dulce_totales(self):
        """Dulce: total PDF > total OMR (Audiveris perdió notas)."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import verificar

        resultado = verificar(DATOS / "dulce.pdf", _dulce_partitura())
        assert resultado.total_pdf > resultado.total_omr

    def test_dulce_diferencias_por_linea(self):
        """Dulce: diferencias concretas en las líneas 3-6."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import contar_cabezas_pdf, contar_notas_omr

        cabezas = contar_cabezas_pdf(DATOS / "dulce.pdf")
        notas = contar_notas_omr(_dulce_partitura())

        assert cabezas is not None
        assert len(cabezas) == len(notas) == 8

        # Sistema 3 (índice 2): PDF=34 vs OMR=33
        assert cabezas[2] == 34
        assert notas[2] == 33
        # Sistema 4 (índice 3): PDF=42 vs OMR=40
        assert cabezas[3] == 42
        assert notas[3] == 40
        # Sistema 5 (índice 4): PDF=29 vs OMR=25
        assert cabezas[4] == 29
        assert notas[4] == 25
        # Sistema 6 (índice 5): PDF=34 vs OMR=30
        assert cabezas[5] == 34
        assert notas[5] == 30

    def test_sintetica_smufl_detecta_cabezas(self):
        """Sintética (Leland/SMuFL): contar_cabezas_pdf devuelve lista no None."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import contar_cabezas_pdf

        cabezas = contar_cabezas_pdf(DATOS / "sintetica.pdf")
        assert cabezas is not None, (
            "sintetica.pdf usa fuente Leland (SMuFL) y debe tener cabezas detectables"
        )
        assert isinstance(cabezas, list)
        assert len(cabezas) > 0

    def test_sintetica_total_cabezas(self):
        """Sintética: 109 cabezas en total (coincide con el musicxml)."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import contar_cabezas_pdf

        cabezas = contar_cabezas_pdf(DATOS / "sintetica.pdf")
        assert cabezas is not None
        total = sum(cabezas)
        assert total == 109, (
            f"sintetica.pdf debe tener 109 cabezas en total, got {total}"
        )

    def test_sintetica_verificar(self):
        """Sintética: verificar devuelve un resultado comprobado."""
        warnings.filterwarnings("ignore")
        from atril.verificacion import verificar

        resultado = verificar(DATOS / "sintetica.pdf", _sintetica_partitura())
        # El PDF tiene múltiples sistemas; el MXL tiene 1 → sistema mismatch
        assert resultado.comprobado is True
        # Debe haber al menos un aviso (diferencia en número de sistemas)
        assert len(resultado.avisos) >= 1
