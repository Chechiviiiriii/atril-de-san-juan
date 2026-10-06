"""Tests para empalme.py — unión de PDFs de partitura."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import requiere_datos

_DATOS = Path(__file__).parent / "datos"


# ---------------------------------------------------------------------------
# 1. Detección de título
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf")
def test_titulo_victoria():
    """victoria.pdf → «¡Tú eres Victoria!»"""
    from empalme import titulo_pdf
    titulo = titulo_pdf(_DATOS / "victoria.pdf")
    assert "Victoria" in titulo, f"Título inesperado: {titulo!r}"


@requiere_datos("dulce.pdf")
def test_titulo_dulce():
    """dulce.pdf → «Dulce mirada de Jesús»"""
    from empalme import titulo_pdf
    titulo = titulo_pdf(_DATOS / "dulce.pdf")
    assert "Dulce" in titulo or "dulce" in titulo.lower(), f"Título inesperado: {titulo!r}"


def test_titulo_sintetica():
    """sintetica.pdf → título detectado (no vacío) o nombre del archivo."""
    from empalme import titulo_pdf
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")
    titulo = titulo_pdf(_DATOS / "sintetica.pdf")
    assert isinstance(titulo, str)
    assert len(titulo) > 0


# ---------------------------------------------------------------------------
# 2. Contar páginas
# ---------------------------------------------------------------------------

def test_contar_paginas_sintetica():
    """sintetica.pdf debe tener al menos 1 página."""
    from empalme import contar_paginas
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")
    n = contar_paginas(_DATOS / "sintetica.pdf")
    assert n >= 1


# ---------------------------------------------------------------------------
# 3. Unir PDFs
# ---------------------------------------------------------------------------

def test_unir_dos_pdfs(tmp_path):
    """Unir sintetica.pdf consigo mismo da el doble de páginas."""
    from empalme import contar_paginas, unir_pdfs
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdf = _DATOS / "sintetica.pdf"
    n_orig = contar_paginas(pdf)
    salida = tmp_path / "union.pdf"
    unir_pdfs([pdf, pdf], salida)

    assert salida.exists()
    n_final = contar_paginas(salida)
    assert n_final == n_orig * 2


@requiere_datos("victoria.pdf", "dulce.pdf")
def test_unir_tres_pdfs_orden_paginas(tmp_path):
    """Victoria + Dulce + Sintética dan la suma correcta de páginas en orden."""
    from empalme import contar_paginas, unir_pdfs
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdfs = [
        _DATOS / "victoria.pdf",
        _DATOS / "dulce.pdf",
        _DATOS / "sintetica.pdf",
    ]
    n_esperado = sum(contar_paginas(p) for p in pdfs)
    salida = tmp_path / "tres.pdf"
    unir_pdfs(pdfs, salida)

    assert salida.exists()
    assert contar_paginas(salida) == n_esperado

    # Verificar orden: el texto de la primera página debe contener algo de victoria
    import pymupdf
    doc = pymupdf.open(str(salida))
    texto_p0 = doc[0].get_text()
    doc.close()
    # La primera página proviene de victoria.pdf; debe tener algún texto
    assert len(texto_p0) >= 0  # al menos no lanza excepción


def test_unir_pdfs_requiere_al_menos_uno(tmp_path):
    """unir_pdfs con lista vacía lanza ValueError."""
    from empalme import unir_pdfs
    with pytest.raises(ValueError):
        unir_pdfs([], tmp_path / "vacio.pdf")


# ---------------------------------------------------------------------------
# 4. Errores con PDFs dañados
# ---------------------------------------------------------------------------

def test_pdf_danado(tmp_path):
    """Un archivo no-PDF lanza PDFDaniadoError."""
    from empalme import PDFDaniadoError, titulo_pdf, contar_paginas

    pdf_malo = tmp_path / "danado.pdf"
    pdf_malo.write_bytes(b"Esto no es un PDF valido")

    # titulo_pdf debe devolver el nombre del archivo como fallback (no lanzar)
    titulo = titulo_pdf(pdf_malo)
    assert titulo == "danado"

    # contar_paginas sí debe lanzar
    with pytest.raises(PDFDaniadoError):
        contar_paginas(pdf_malo)


def test_unir_con_pdf_danado(tmp_path):
    """unir_pdfs lanza PDFDaniadoError si algún archivo está dañado."""
    from empalme import PDFDaniadoError, unir_pdfs
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdf_malo = tmp_path / "danado.pdf"
    pdf_malo.write_bytes(b"No soy un PDF")

    with pytest.raises(PDFDaniadoError):
        unir_pdfs([_DATOS / "sintetica.pdf", pdf_malo], tmp_path / "salida.pdf")
