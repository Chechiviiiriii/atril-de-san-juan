"""
Notas fuera del pentagrama: cada cabeza debe asignarse a SU pentagrama gracias a
las líneas adicionales, aunque los sistemas estén muy juntos y la nota quede más
cerca del pentagrama de arriba.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pymupdf
import pytest
from music21 import converter, layout

from atril import superponer as S
from atril.nombres import nombre_nota

_DATOS = Path(__file__).parent / "datos"
_AGUDAS_PDF = _DATOS / "agudas.pdf"
_AGUDAS_VERDAD = _DATOS / "agudas.musicxml"
_AGUDAS_OMR = _DATOS / "agudas_omr.mxl"


def _pentagrama(arriba: float, espacio: float = 5.0) -> S.Pentagrama:
    return S.Pentagrama(pagina=0, arriba=arriba, abajo=arriba + 4 * espacio, x0=50, x1=800)


def test_nota_aguda_con_lineas_adicionales_va_a_su_pentagrama():
    # Pentagrama A: 100–120; pentagrama B: 150–170 (sistemas muy juntos).
    pents = [_pentagrama(100.0), _pentagrama(150.0)]
    # Nota a y=130 con líneas adicionales en 145, 140, 135 y 130 (escalera hacia B).
    # Está más cerca del centro de A (110) que del de B (160), pero es de B.
    adicionales = [(y, 295.0, 305.0) for y in (145.0, 140.0, 135.0, 130.0)]
    assert S._pentagrama_de_cabeza(pents, adicionales, 300.0, 130.0) == 1


def test_nota_grave_con_lineas_adicionales_va_a_su_pentagrama():
    pents = [_pentagrama(100.0), _pentagrama(150.0)]
    # Nota grave de A a y=135, con líneas adicionales en 125, 130 y 135 (escalera hacia A)
    adicionales = [(y, 295.0, 305.0) for y in (125.0, 130.0, 135.0)]
    assert S._pentagrama_de_cabeza(pents, adicionales, 300.0, 135.0) == 0


def test_sin_lineas_adicionales_gana_el_mas_cercano():
    pents = [_pentagrama(100.0), _pentagrama(150.0)]
    assert S._pentagrama_de_cabeza(pents, [], 300.0, 126.0) == 0
    assert S._pentagrama_de_cabeza(pents, [], 300.0, 144.0) == 1


@pytest.mark.skipif(not _AGUDAS_PDF.exists(), reason="Falta tests/datos/agudas.pdf")
def test_agudas_cada_linea_recibe_sus_notas():
    page = pymupdf.open(_AGUDAS_PDF)[0]
    pents = S.detectar_pentagramas(page, 0)
    cabezas = S.detectar_cabezas(page, pents)
    por_linea = [sum(1 for h in cabezas if h.pent == i) for i in range(len(pents))]

    partitura = converter.parse(str(_AGUDAS_VERDAD))
    compases = list(partitura.parts[0].getElementsByClass("Measure"))
    inicios = [i for i, m in enumerate(compases)
               if i == 0 or m.getElementsByClass(layout.SystemLayout)] + [len(compases)]
    esperado = [sum(len(n.pitches) for m in compases[inicios[k]:inicios[k + 1]]
                    for n in m.recurse().notes) for k in range(len(inicios) - 1)]
    assert por_linea == esperado


@pytest.mark.skipif(not _AGUDAS_OMR.exists(), reason="Falta tests/datos/agudas_omr.mxl")
def test_agudas_todos_los_nombres_correctos():
    verdad = [nombre_nota(n.pitch) for n in converter.parse(str(_AGUDAS_VERDAD)).recurse().notes]
    analisis = S.analizar(_AGUDAS_PDF, converter.parse(str(_AGUDAS_OMR)))
    textos = [n.texto for n in sorted(analisis.notas, key=lambda n: (n.linea, n.cabeza[0]))]
    aciertos = sum(b.size for b in difflib.SequenceMatcher(a=verdad, b=textos, autojunk=False)
                   .get_matching_blocks())
    assert aciertos == len(verdad)


def test_segunda_desplazada_se_ordena_de_agudo_a_grave():
    # Acorde de segunda: la cabeza de arriba (paso 6) va a la derecha de la de abajo (paso 5).
    # Debe quedar primero la aguda, como da Audiveris, aunque su x sea mayor.
    def cabeza(x, y, paso):
        return S.Cabeza(pent=0, x=x, xc=x + 4, y=y, paso=paso, tam=19.0, bbox=(x, y - 4, x + 8, y + 4))
    grave = cabeza(100.0, 130.0, 5)
    aguda = cabeza(106.5, 127.5, 6)
    siguiente = cabeza(118.0, 125.0, 7)          # nota siguiente, no forma parte del acorde
    ordenadas = S._ordenar_por_columnas([grave, siguiente, aguda])
    assert [c.paso for c in ordenadas] == [6, 5, 7]
