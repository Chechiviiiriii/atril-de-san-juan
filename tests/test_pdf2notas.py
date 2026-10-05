"""Tests de pdf2notas.py."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers y fixtures
# ---------------------------------------------------------------------------

@dataclass
class ResumenFalso:
    """Implementación falsa de nombres.Resumen para tests."""
    notas_nombradas: int = 10
    ligadas_marcadas: int = 1
    acordes: int = 0
    armadura: str = "Sib mayor"
    avisos: list = field(default_factory=list)
    cambios: list = field(default_factory=lambda: ["Compás 1: clave de fa en 4ª, 2 bemoles"])


def _inyectar_mock_nombres(monkeypatch, resumen=None):
    """Inyecta un módulo 'nombres' falso en sys.modules."""
    if resumen is None:
        resumen = ResumenFalso()
    mock_mod = types.ModuleType("nombres")
    mock_mod.anotar_partitura = MagicMock(return_value=resumen)
    monkeypatch.setitem(sys.modules, "nombres", mock_mod)
    return mock_mod


# ---------------------------------------------------------------------------
# _imprimir_resumen
# ---------------------------------------------------------------------------

def test_imprimir_resumen_imprime_cambios(capsys):
    """Imprime las líneas de cambios antes del conteo de notas."""
    import pdf2notas
    resumen = ResumenFalso(
        notas_nombradas=50,
        ligadas_marcadas=3,
        cambios=["Compás 1: clave de fa en 4ª, 4 bemoles"],
        avisos=[],
    )
    pdf2notas._imprimir_resumen(resumen)
    out = capsys.readouterr().out
    assert "Compás 1: clave de fa en 4ª, 4 bemoles" in out
    assert "50" in out
    assert "3 ligadas marcadas" in out


def test_imprimir_resumen_tolerancia_api_vieja(capsys):
    """Tolera el campo ligadas_omitidas de la API anterior."""
    import pdf2notas

    @dataclass
    class ResumenViejo:
        notas_nombradas: int = 8
        ligadas_omitidas: int = 2
        acordes: int = 0
        armadura: str = ""
        avisos: list = field(default_factory=list)
        cambios: list = field(default_factory=list)

    pdf2notas._imprimir_resumen(ResumenViejo())
    out = capsys.readouterr().out
    assert "8" in out
    assert "2 ligadas" in out


def test_imprimir_resumen_muestra_avisos(capsys):
    """Muestra los avisos con el símbolo de advertencia."""
    import pdf2notas
    resumen = ResumenFalso(avisos=["nota de advertencia prueba"], cambios=[])
    pdf2notas._imprimir_resumen(resumen)
    out = capsys.readouterr().out
    assert "nota de advertencia prueba" in out


# ---------------------------------------------------------------------------
# poner_nombres — limpieza de metadatos
# ---------------------------------------------------------------------------

def test_poner_nombres_limpia_compositor_music21(monkeypatch, tmp_path):
    """Quita el compositor 'Music21' y pone el título si falta."""
    import music21

    _inyectar_mock_nombres(monkeypatch)

    # Crear una partitura mínima con metadatos de Music21
    partitura = music21.stream.Score()
    partitura.metadata = music21.metadata.Metadata()
    partitura.metadata.title = "sintetica.mxl"
    partitura.metadata.composer = "Music21"
    compas = music21.stream.Measure()
    compas.append(music21.note.Note("C4"))
    parte = music21.stream.Part()
    parte.append(compas)
    partitura.append(parte)

    # Guardar como MusicXML para que poner_nombres lo lea
    entrada = tmp_path / "entrada.musicxml"
    partitura.write("musicxml", fp=str(entrada))

    salida = tmp_path / "salida.musicxml"

    import pdf2notas
    pdf2notas.poner_nombres(entrada, salida, titulo="Mi partitura")

    # Verificar que el archivo XML no contiene "Music21" como compositor
    contenido = salida.read_text(encoding="utf-8")
    import re
    creadores = re.findall(r'<creator[^>]*type=["\']composer["\'][^>]*>([^<]*)</creator>', contenido)
    for creador in creadores:
        assert creador.strip() != "Music21", f"Compositor 'Music21' encontrado en el XML: {creador!r}"

    # El título debe haberse actualizado (el stem del archivo era "entrada")
    resultado = music21.converter.parse(str(salida))
    assert resultado.metadata.title == "Mi partitura"


def test_poner_nombres_limpia_nombre_parte_voice(monkeypatch, tmp_path):
    """Pone a vacío el nombre de parte 'Voice'."""
    import music21

    _inyectar_mock_nombres(monkeypatch)

    partitura = music21.stream.Score()
    partitura.metadata = music21.metadata.Metadata()
    parte = music21.stream.Part()
    parte.partName = "Voice"
    compas = music21.stream.Measure()
    compas.append(music21.note.Note("G3"))
    parte.append(compas)
    partitura.append(parte)

    entrada = tmp_path / "entrada.musicxml"
    partitura.write("musicxml", fp=str(entrada))
    salida = tmp_path / "salida.musicxml"

    import pdf2notas
    pdf2notas.poner_nombres(entrada, salida, titulo="Test")

    resultado = music21.converter.parse(str(salida))
    for p in resultado.parts:
        assert p.partName != "Voice"


# ---------------------------------------------------------------------------
# CLI — argumentos y flujo
# ---------------------------------------------------------------------------

def test_main_archivo_inexistente(tmp_path):
    """Devuelve código 1 si el PDF no existe."""
    import pdf2notas
    ret = pdf2notas.main([str(tmp_path / "no_existe.pdf")])
    assert ret == 1


def test_main_no_es_pdf(tmp_path):
    """Devuelve código 1 si el archivo no es PDF."""
    f = tmp_path / "partitura.txt"
    f.write_text("")
    import pdf2notas
    ret = pdf2notas.main([str(f)])
    assert ret == 1


def test_main_sin_argumentos_devuelve_1():
    """Sin argumentos devuelve 1."""
    import pdf2notas
    ret = pdf2notas.main([])
    assert ret == 1


def test_main_salida_con_carpeta_devuelve_1(tmp_path):
    """--salida y --carpeta juntos devuelven 1."""
    import pdf2notas
    ret = pdf2notas.main(["--salida", str(tmp_path / "out.pdf"), "--carpeta", str(tmp_path)])
    assert ret == 1


def test_main_carpeta_salta_notas_y_objetivo(monkeypatch, tmp_path):
    """--carpeta salta archivos _notas.pdf y _objetivo.pdf."""
    import pdf2notas

    # Crear PDFs en la carpeta
    (tmp_path / "real.pdf").write_text("")
    (tmp_path / "ya_procesado_notas.pdf").write_text("")
    (tmp_path / "objetivo_objetivo.pdf").write_text("")

    pdfs_procesados = []

    def mock_procesar(pdf, salida, args, config, audiveris, musescore, carpeta):
        pdfs_procesados.append(pdf.name)

    monkeypatch.setattr(pdf2notas, "_procesar_un_pdf", mock_procesar)

    # Mockear herramientas para que no busque executables reales
    from config import cargar_config as _cc
    monkeypatch.setattr(pdf2notas, "_importar_nombres", lambda: MagicMock())

    with patch("omr.buscar_audiveris", return_value=tmp_path / "aud.exe"), \
         patch("render.buscar_musescore", return_value=tmp_path / "ms.exe"):
        pdf2notas.main(["--carpeta", str(tmp_path)])

    assert "real.pdf" in pdfs_procesados
    assert "ya_procesado_notas.pdf" not in pdfs_procesados
    assert "objetivo_objetivo.pdf" not in pdfs_procesados


def test_main_carpeta_continua_tras_error(monkeypatch, tmp_path):
    """--carpeta sigue procesando aunque uno falle; devuelve código != 0."""
    import pdf2notas

    (tmp_path / "bueno.pdf").write_text("")
    (tmp_path / "malo.pdf").write_text("")

    llamadas = []

    def mock_procesar(pdf, salida, args, config, audiveris, musescore, carpeta):
        llamadas.append(pdf.name)
        if pdf.name == "malo.pdf":
            raise RuntimeError("fallo simulado")

    monkeypatch.setattr(pdf2notas, "_procesar_un_pdf", mock_procesar)

    with patch("omr.buscar_audiveris", return_value=tmp_path / "aud.exe"), \
         patch("render.buscar_musescore", return_value=tmp_path / "ms.exe"):
        ret = pdf2notas.main(["--carpeta", str(tmp_path)])

    assert "bueno.pdf" in llamadas
    assert "malo.pdf" in llamadas
    assert ret == 1
