"""PDF «raros» que antes daban «No se detectaron cabezas de nota»:

- páginas giradas con /Rotate (PDFCreator/Ghostscript),
- fuente musical codificada como fuente de símbolos (U+F0xx),
- pentagramas con espaciado irregular por redondeo,
- pentagramas escritos con la fuente (glifo «=») en vez de con líneas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf
import pytest

from atril.superponer import (
    _agrupar_lineas_equiespaciadas,
    _normalizar_codepoint,
    _pentagramas_de_glifos,
    detectar_cabezas,
    detectar_pentagramas,
    pdf_derecho,
)

_DATOS = Path(__file__).parent / "datos"
_DESCARGAS = Path.home() / "Downloads"


def test_codepoint_de_fuente_de_simbolos():
    assert _normalizar_codepoint(0xF0CF) == ord("œ")   # negra
    assert _normalizar_codepoint(0xF0FA) == ord("˙")   # blanca
    assert _normalizar_codepoint(0xF023) == ord("#")
    assert _normalizar_codepoint(ord("œ")) == ord("œ")  # lo normal no cambia


def test_pentagrama_con_espaciado_redondeado():
    ys = [124.1, 127.9, 131.9, 135.7, 139.7, 182.2, 186.1, 190.0, 193.9, 197.8]
    grupos = _agrupar_lineas_equiespaciadas(ys)
    assert grupos == [ys[:5], ys[5:]]


def test_pdf_sin_girar_no_se_copia():
    pdf = _DATOS / "sintetica.pdf"
    assert pdf_derecho(pdf) == pdf


def _girado(tmp_path: Path) -> Path:
    """Copia de sintetica.pdf guardada en vertical con /Rotate 90 (mismo aspecto)."""
    src = pymupdf.open(str(_DATOS / "sintetica.pdf"))
    out = pymupdf.open()
    for pg in src:
        r = pg.rect
        nueva = out.new_page(width=r.height, height=r.width)
        nueva.set_rotation(90)
        # El contenido se dibuja girado -90° para que, al mostrarse girado 90°, quede derecho.
        nueva.show_pdf_page(nueva.rect, src, pg.number, rotate=-90)
    ruta = tmp_path / "girada.pdf"
    out.save(str(ruta))
    return ruta


def test_pdf_girado_se_endereza(tmp_path):
    girada = _girado(tmp_path)
    original = pymupdf.open(str(girada))
    assert original[0].rotation == 90
    assert detectar_pentagramas(original[0], 0) == []          # de lado: no se ve nada

    derecha_ruta = pdf_derecho(girada)
    assert derecha_ruta != girada
    derecha = pymupdf.open(str(derecha_ruta))
    assert derecha[0].rotation == 0
    assert derecha[0].rect == original[0].rect

    a = np.frombuffer(original[0].get_pixmap().samples, dtype=np.uint8)
    b = np.frombuffer(derecha[0].get_pixmap().samples, dtype=np.uint8)
    assert a.shape == b.shape and np.abs(a.astype(int) - b.astype(int)).mean() < 1.0

    pents = detectar_pentagramas(derecha[0], 0)
    ref = pymupdf.open(str(_DATOS / "sintetica.pdf"))
    assert len(pents) == len(detectar_pentagramas(ref[0], 0))
    assert len(detectar_cabezas(derecha[0], pents)) > 0


# --- Partituras reales del usuario (solo en local) ---------------------------

@pytest.mark.parametrize("nombre, pentagramas", [
    ("Alma de Dios Bdno 1º Sib.pdf", 8),      # girada + Opus como fuente de símbolos
    ("Cerca de Ti Bdno Sib.pdf", 8),          # girada + pentagramas con la fuente Anastasia
])
def test_pdfs_reales(nombre, pentagramas):
    ruta = _DESCARGAS / nombre
    if not ruta.exists():
        pytest.skip(f"No está {nombre}")
    page = pymupdf.open(str(pdf_derecho(ruta)))[0]
    pents = detectar_pentagramas(page, 0)
    assert len(pents) == pentagramas
    assert len(detectar_cabezas(page, pents)) > 50


def test_pentagramas_de_glifos_sin_fuente_musical():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "=" * 40, fontsize=24)       # Helvetica: no es fuente musical
    assert _pentagramas_de_glifos(page, 0) == []
