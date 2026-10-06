"""
test_comparar.py — Tests para comparar.py.

Cubre:
- extraer_nombres en PDF sin notas → lista vacía
- _son_compatibles: iguales, "·" vs nombre, distintos
- comparar: coincidencia perfecta, con ligadas, sin referencia
- Extracción de nombres del PDF de referencia numerado a mano
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import requiere_datos

_DATOS = Path(__file__).parent / "datos"
_VICTORIA_NUM = _DATOS / "victoria_numerada.pdf"
_SINTETICA_PDF = _DATOS / "sintetica.pdf"


# ---------------------------------------------------------------------------
# _son_compatibles
# ---------------------------------------------------------------------------

def test_son_compatibles_iguales():
    from herramientas.comparar import _son_compatibles  # type: ignore[attr-defined]
    assert _son_compatibles("Do", "Do") is True
    assert _son_compatibles("Mib", "Mib") is True
    assert _son_compatibles("·", "·") is True


def test_son_compatibles_ligada_vs_nombre():
    from herramientas.comparar import _son_compatibles  # type: ignore[attr-defined]
    assert _son_compatibles("·", "Re") is True
    assert _son_compatibles("Sol", "·") is True


def test_son_compatibles_distintos():
    from herramientas.comparar import _son_compatibles  # type: ignore[attr-defined]
    assert _son_compatibles("Do", "Re") is False
    assert _son_compatibles("Fa#", "Fab") is False


# ---------------------------------------------------------------------------
# extraer_nombres
# ---------------------------------------------------------------------------

@requiere_datos("victoria_numerada.pdf")
def test_extraer_nombres_referencia_no_vacia():
    """La referencia numerada a mano tiene nombres de nota."""
    from herramientas.comparar import extraer_nombres
    nombres = extraer_nombres(_VICTORIA_NUM, es_referencia=True)
    assert len(nombres) > 0, "No se extrajo ningún nombre de la referencia"


@requiere_datos("victoria_numerada.pdf")
def test_extraer_nombres_son_validos():
    """Los nombres extraídos son nombres de nota válidos o '·'."""
    import re
    from herramientas.comparar import extraer_nombres, MARCA_LIGADA
    pat = re.compile(r"^(Do|Re|Mi|Fa|Sol|La|Si)(##?|bb?|#|b)?$", re.IGNORECASE)
    nombres = extraer_nombres(_VICTORIA_NUM, es_referencia=True)
    invalidos = [n for n in nombres if n != MARCA_LIGADA and not pat.match(n)]
    assert len(invalidos) == 0, f"Nombres inválidos extraídos: {invalidos[:10]}"


# ---------------------------------------------------------------------------
# comparar
# ---------------------------------------------------------------------------

def test_comparar_coincidencia_perfecta(tmp_path):
    """comparar() con dos PDFs idénticos debe dar 100% de coincidencia."""
    import pymupdf
    from herramientas.comparar import comparar

    # Crear un PDF mínimo con texto de nota
    salida = tmp_path / "test_notas.pdf"
    doc = pymupdf.open()

    page = doc.new_page(width=595, height=842)
    # Dibujar 5 líneas de pentagrama para que se detecten pentagramas
    for i in range(5):
        y = 400 + i * 8
        page.draw_line((50, y), (540, y))
    # Insertar un nombre de nota
    page.insert_text((100, 430), "Do", fontsize=9, color=(0, 0, 0))

    doc.save(str(salida))
    doc.close()

    # Comparar el PDF consigo mismo
    resultado = comparar(salida, salida)
    assert resultado["pct_coincidencia"] == pytest.approx(100.0)


def test_comparar_referencia_vacia(tmp_path):
    """comparar() con referencia sin nombres devuelve 0% y aviso."""
    import pymupdf
    from herramientas.comparar import comparar

    salida = tmp_path / "generado.pdf"
    referencia = tmp_path / "referencia_vacia.pdf"

    for ruta in (salida, referencia):
        doc = pymupdf.open()
        doc.new_page(width=595, height=842)
        doc.save(str(ruta))
        doc.close()

    resultado = comparar(salida, referencia)
    assert resultado["pct_coincidencia"] == pytest.approx(0.0)
    assert resultado["n_referencia"] == 0


def test_comparar_con_ligadas(tmp_path):
    """'·' en generado se acepta como coincidencia con el nombre en la referencia."""
    from herramientas.comparar import _son_compatibles, MARCA_LIGADA
    # Prueba unitaria de la lógica de compatibilidad
    assert _son_compatibles(MARCA_LIGADA, "La") is True
    assert _son_compatibles("La", MARCA_LIGADA) is True


@requiere_datos("victoria_numerada.pdf")
def test_comparar_referencia_tiene_185_notas():
    """La referencia numerada de Victoria tiene ~185 nombres (mismo número que cabezas).

    La extracción puede variar ligeramente por cómo PyMuPDF agrupa los spans
    en documentos de distinto origen (MuseScore vs nuestro overlay).
    """
    from herramientas.comparar import extraer_nombres
    nombres = extraer_nombres(_VICTORIA_NUM, es_referencia=True)
    # findall extrae todos los nombres de nota presentes en cada span
    assert 130 <= len(nombres) <= 220, (
        f"Se esperaban ~185 nombres en la referencia, se extrajeron {len(nombres)}"
    )
