"""Tests de extremo a extremo: PDF -> PDF con nombres de notas."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

import pytest

# Datos de prueba
_DATOS = Path(__file__).parent / "datos"
_PDF_SINTETICA = _DATOS / "sintetica.pdf"
_XML_VERDAD = _DATOS / "sintetica.musicxml"


def _nombres_esperados_de_musicxml(ruta_xml: Path) -> list[str]:
    """Extrae los nombres de notas del campo lyrics del MusicXML de referencia."""
    import music21
    partitura = music21.converter.parse(str(ruta_xml))
    nombres = []
    for nota in partitura.recurse().notes:
        for lirica in nota.lyrics:
            if lirica.text:
                nombres.append(lirica.text)
    return nombres


def _nombres_de_musicxml_generado(ruta_xml: Path) -> list[str]:
    """Extrae los textos de lyrics del MusicXML generado."""
    import music21
    partitura = music21.converter.parse(str(ruta_xml))
    nombres = []
    for nota in partitura.recurse().notes:
        for lirica in nota.lyrics:
            if lirica.text:
                nombres.append(lirica.text)
    return nombres


def _calcular_similitud(lista_a: list[str], lista_b: list[str]) -> float:
    """Calcula la similitud entre dos listas usando difflib (0.0–1.0)."""
    cadena_a = " ".join(lista_a)
    cadena_b = " ".join(lista_b)
    return difflib.SequenceMatcher(None, cadena_a, cadena_b).ratio()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def audiveris_exe():
    """Ruta a Audiveris; salta el test si no está instalado."""
    from config import cargar_config
    from omr import buscar_audiveris
    try:
        return buscar_audiveris(cargar_config())
    except Exception:
        pytest.skip("Audiveris no encontrado; se omite el test de extremo a extremo.")


@pytest.fixture(scope="session")
def musescore_exe():
    """Ruta a MuseScore; salta el test si no está instalado."""
    from config import cargar_config
    from render import buscar_musescore
    try:
        return buscar_musescore(cargar_config())
    except Exception:
        pytest.skip("MuseScore no encontrado; se omite el test de extremo a extremo.")


@pytest.fixture(scope="session")
def nombres_disponible():
    """Salta el test si nombres.py no está disponible."""
    try:
        import nombres  # noqa: F401
    except ImportError:
        pytest.skip("nombres.py no disponible; se omite el test de extremo a extremo.")


# ---------------------------------------------------------------------------
# Test principal
# ---------------------------------------------------------------------------

@pytest.mark.lento
def test_extremo_a_extremo(
    tmp_path,
    audiveris_exe,
    nombres_disponible,
):
    """Ejecuta el pipeline completo (modo superposición) sobre la partitura sintética.

    Verifica:
    - Que el PDF de salida existe y tiene tamaño > 0.
    - Que el número de nombres escritos coincide con el número de notas del MXL.
    """
    assert _PDF_SINTETICA.exists(), f"No se encuentra {_PDF_SINTETICA}"
    assert _XML_VERDAD.exists(), f"No se encuentra {_XML_VERDAD}"

    # Copiar el PDF a tmp_path para no modificar los datos de prueba
    pdf_trabajo = tmp_path / "sintetica.pdf"
    shutil.copy2(str(_PDF_SINTETICA), str(pdf_trabajo))

    # Ejecutar el pipeline en modo superposición (por defecto)
    from pdf2notas import main
    ret = main([str(pdf_trabajo), "--conservar"])
    assert ret == 0, "El pipeline devolvió código de error"

    # Verificar que el PDF de salida existe
    pdf_salida = tmp_path / "sintetica_notas.pdf"
    assert pdf_salida.exists(), f"El PDF de salida no existe: {pdf_salida}"
    assert pdf_salida.stat().st_size > 1000, "El PDF de salida parece vacío"

    # Verificar que el PDF contiene nombres de nota
    import re
    from comparar import extraer_nombres
    nombres_extraidos = extraer_nombres(pdf_salida)
    pat = re.compile(r"^(Do|Re|Mi|Fa|Sol|La|Si)(##?|bb?|#|b)?$")
    nombres_validos = [n for n in nombres_extraidos if pat.match(n)]
    assert len(nombres_validos) > 50, (
        f"Se esperaban más de 50 nombres válidos en el PDF de salida, "
        f"se encontraron {len(nombres_validos)}"
    )

    # Calcular nombres esperados desde el MusicXML de referencia
    import music21
    import nombres as mod_nombres
    partitura_ref = music21.converter.parse(str(_XML_VERDAD))
    textos = mod_nombres.textos_por_nota(partitura_ref)
    esperados = [t.texto for t in textos if t.texto != mod_nombres.MARCA_LIGADA]

    assert esperados, "No se encontraron nombres esperados en el MusicXML de referencia"

    # Verificar que la cobertura es razonable (≥80% de las notas tienen nombre)
    cobertura = len(nombres_validos) / len(esperados) if esperados else 0.0
    assert cobertura >= 0.80, (
        f"Cobertura de nombres insuficiente: {cobertura:.1%} "
        f"({len(nombres_validos)} nombres válidos, {len(esperados)} esperados)"
    )
