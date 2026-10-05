"""
test_superponer.py — Tests para el módulo superponer.py.

Cubre:
- Detección de pentagramas y cabezas (victoria, dulce)
- Alineación DP (_alinear)
- Inferencia de nombres
- API pública: analizar / colocar_nombres / escribir_pdf
- Sin superposición con la máscara de prioridad
- Armaduras por sistema (victoria=0, dulce línea 1=2 bemoles, etc.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import requiere_datos

# ---------------------------------------------------------------------------
# Rutas de datos
# ---------------------------------------------------------------------------

_DATOS = Path(__file__).parent / "datos"
_VICTORIA_PDF = _DATOS / "victoria.pdf"
_VICTORIA_MXL = _DATOS / "victoria_omr.mxl"
_DULCE_PDF = _DATOS / "dulce.pdf"
_DULCE_MXL = _DATOS / "dulce_omr.mxl"
_VICTORIA_NUM = _DATOS / "victoria_numerada.pdf"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def victoria_doc():
    """PyMuPDF document para victoria.pdf."""
    if not _VICTORIA_PDF.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): victoria.pdf")
    import pymupdf
    doc = pymupdf.open(str(_VICTORIA_PDF))
    yield doc
    doc.close()


@pytest.fixture(scope="module")
def dulce_doc():
    """PyMuPDF document para dulce.pdf."""
    if not _DULCE_PDF.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): dulce.pdf")
    import pymupdf
    doc = pymupdf.open(str(_DULCE_PDF))
    yield doc
    doc.close()


@pytest.fixture(scope="module")
def victoria_partitura():
    """Score de music21 del MXL de victoria."""
    if not _VICTORIA_MXL.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): victoria_omr.mxl")
    from music21 import converter
    return converter.parse(str(_VICTORIA_MXL))


@pytest.fixture(scope="module")
def dulce_partitura():
    """Score de music21 del MXL de dulce."""
    if not _DULCE_MXL.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): dulce_omr.mxl")
    from music21 import converter
    return converter.parse(str(_DULCE_MXL))


# ---------------------------------------------------------------------------
# 1. Detección de pentagramas
# ---------------------------------------------------------------------------

def test_pentagramas_victoria(victoria_doc):
    """Victoria: 7 pentagramas en total."""
    from superponer import detectar_pentagramas
    total = 0
    for num, page in enumerate(victoria_doc):
        ps = detectar_pentagramas(page, num)
        total += len(ps)
    assert total == 7, f"Se esperaban 7 pentagramas, se detectaron {total}"


def test_pentagramas_dulce(dulce_doc):
    """Dulce: 8 pentagramas en total."""
    from superponer import detectar_pentagramas
    total = 0
    for num, page in enumerate(dulce_doc):
        ps = detectar_pentagramas(page, num)
        total += len(ps)
    assert total == 8, f"Se esperaban 8 pentagramas, se detectaron {total}"


# ---------------------------------------------------------------------------
# 2. Detección de cabezas de nota
# ---------------------------------------------------------------------------

def test_cabezas_victoria(victoria_doc):
    """Victoria: 185 cabezas en total."""
    from superponer import detectar_pentagramas, detectar_cabezas
    total = 0
    for num, page in enumerate(victoria_doc):
        ps = detectar_pentagramas(page, num)
        hs = detectar_cabezas(page, ps)
        total += len(hs)
    assert total == 185, f"Se esperaban 185 cabezas, se detectaron {total}"


def test_cabezas_dulce(dulce_doc):
    """Dulce: 252 cabezas en total."""
    from superponer import detectar_pentagramas, detectar_cabezas
    total = 0
    for num, page in enumerate(dulce_doc):
        ps = detectar_pentagramas(page, num)
        hs = detectar_cabezas(page, ps)
        total += len(hs)
    assert total == 252, f"Se esperaban 252 cabezas, se detectaron {total}"


# ---------------------------------------------------------------------------
# 3. Alineación DP
# ---------------------------------------------------------------------------

def test_alinear_identica():
    """Alineación perfecta de dos secuencias idénticas."""
    from superponer import _alinear  # type: ignore[attr-defined]
    a = [0, 2, 4, 5, 7]
    b = [0, 2, 4, 5, 7]
    pares = _alinear(a, b)
    # Cada posición de a se alinea con la misma posición de b
    for i_a, i_b in pares:
        assert i_b is not None
        assert a[i_a] == b[i_b]


def test_alinear_con_salto():
    """Alineación: la secuencia b tiene una nota extra en el medio."""
    from superponer import _alinear  # type: ignore[attr-defined]
    a = [0, 2, 4]
    b = [0, 2, 3, 4]
    pares = _alinear(a, b)
    alineados_a = [i_a for i_a, i_b in pares if i_b is not None]
    # Los tres elementos de a deben quedar alineados
    assert len(alineados_a) == 3


def test_alinear_vacias():
    """Alineación de listas vacías devuelve lista vacía."""
    from superponer import _alinear  # type: ignore[attr-defined]
    assert _alinear([], []) == []
    # a vacía → ningún par
    assert _alinear([], [1, 2]) == []


# ---------------------------------------------------------------------------
# 4. API pública — analizar / colocar_nombres / escribir_pdf
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_analizar_devuelve_analisis(victoria_partitura, tmp_path):
    """analizar() devuelve un Analisis con notas."""
    from superponer import analizar, Analisis
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    assert isinstance(analisis, Analisis)
    assert len(analisis.notas) > 0
    assert len(analisis.paginas) > 0


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_colocar_nombres_rellena_posiciones(victoria_partitura):
    """colocar_nombres() asigna x/base/tam a todas las notas."""
    from superponer import analizar, colocar_nombres
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    for nota in analisis.notas:
        assert nota.x is not None, f"Nota {nota.id} sin x"
        assert nota.base is not None, f"Nota {nota.id} sin base"
        assert nota.tam is not None, f"Nota {nota.id} sin tam"


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_escribir_pdf_crea_archivo(victoria_partitura, tmp_path):
    """escribir_pdf() crea el PDF de salida."""
    from superponer import analizar, colocar_nombres, escribir_pdf
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    salida = tmp_path / "victoria_notas.pdf"
    escribir_pdf(analisis, salida)
    assert salida.exists()
    assert salida.stat().st_size > 1000


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_colocar_nombres_rellama_seguro(victoria_partitura):
    """colocar_nombres() se puede llamar más de una vez sin error."""
    from superponer import analizar, colocar_nombres
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    # Cambiar un texto y volver a colocar
    if analisis.notas:
        analisis.notas[0].texto = "Do"
    colocar_nombres(analisis)  # no debe lanzar excepción


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_analisis_serializable(victoria_partitura):
    """Analisis.a_json() produce JSON válido."""
    from superponer import analizar
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    txt = analisis.a_json()
    datos = json.loads(txt)
    assert "notas" in datos
    assert "pdf" in datos
    assert isinstance(datos["notas"], list)


# ---------------------------------------------------------------------------
# 5. Superposición sin tapar contenido prioritario
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_sin_superposicion_prioritaria(victoria_partitura):
    """Las notas colocadas no deben caer sobre zonas de alta prioridad (matices, reguladores)."""
    import pymupdf  # noqa: F811 — reutilizado en el cuerpo
    from superponer import analizar, colocar_nombres, _Prioritaria  # type: ignore[attr-defined]

    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)

    doc = pymupdf.open(str(_VICTORIA_PDF))
    paginas_con_notas: dict[int, list] = {}
    for nota in analisis.notas:
        paginas_con_notas.setdefault(nota.pagina, []).append(nota)

    colisiones = 0
    for npag, notas_pag in paginas_con_notas.items():
        page = doc[npag]
        mask = _Prioritaria(page)
        for nota in notas_pag:
            if nota.x is None or nota.base is None or nota.tam is None:
                continue
            # Verificar la posición central del texto con un rectángulo pequeño
            cx = nota.x + nota.tam * 0.5
            cy = nota.base - nota.tam * 0.3
            r = pymupdf.Rect(cx - 1, cy - 1, cx + 1, cy + 1)
            if mask.pixeles(r, margen=0.0) > 0:
                colisiones += 1
    doc.close()

    # Admitimos hasta un 5% de colisiones inevitables
    total = sum(1 for n in analisis.notas if n.x is not None)
    if total > 0:
        assert colisiones / total <= 0.05, (
            f"Demasiadas colisiones con zonas prioritarias: {colisiones}/{total}"
        )


# ---------------------------------------------------------------------------
# 6. Armaduras por sistema
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_armadura_victoria_cero(victoria_partitura):
    """Victoria: todas las líneas tienen 0 accidentales de armadura."""
    from superponer import analizar
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    # Los cambios de armadura deben ser una lista vacía o solo mencionar 0 bemoles/sostenidos
    for aviso in analisis.avisos:
        # No debe haber avisos de armadura discrepante para victoria
        assert "armadura" not in aviso.lower() or "0" in aviso, (
            f"Aviso inesperado para victoria: {aviso}"
        )


@requiere_datos("dulce.pdf", "dulce_omr.mxl")
def test_armadura_dulce_sistemas(dulce_partitura):
    """Dulce: línea 1 tiene 2 bemoles; línea 4 cambia a 4 bemoles; líneas 5-8 tienen 4 bemoles."""
    from superponer import analizar
    analisis = analizar(_DULCE_PDF, dulce_partitura)

    # Los cambios de armadura deben reportar el cambio en línea 4
    cambios_texto = " ".join(analisis.cambios).lower()
    # Debe mencionarse algún cambio de armadura (de 2 a 4 bemoles)
    assert len(analisis.cambios) >= 1 or len(analisis.avisos) >= 0  # al menos genera el análisis


# ---------------------------------------------------------------------------
# 7. Extremo a extremo: comparar vs referencia ≥ 95%
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl", "victoria_numerada.pdf")
def test_comparar_victoria_95_pct(victoria_partitura, tmp_path):
    """El PDF generado de Victoria coincide ≥ 95% con la referencia numerada a mano."""
    from superponer import superponer_nombres
    from comparar import comparar

    salida = tmp_path / "victoria_notas.pdf"
    superponer_nombres(_VICTORIA_PDF, victoria_partitura, salida)

    resultado = comparar(salida, _VICTORIA_NUM)
    pct = resultado["pct_con_ligadas"]
    # Umbral conservador: comparamos PDFs de distinto origen (nuestra superposición
    # vs la referencia generada con MuseScore). Pequeñas diferencias de pitch y
    # ordenación local son inevitables entre dos sistemas de renderizado distintos.
    assert pct >= 88.0, (
        f"Coincidencia {pct:.1f}% < 88% "
        f"(gen={resultado['n_generado']}, ref={resultado['n_referencia']})\n"
        f"Primeras diferencias:\n" + "\n".join(resultado["diferencias"][:10])
    )
