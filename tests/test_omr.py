"""Tests de omr.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import HerramientaNoEncontrada
from omr import (
    ErrorOMR,
    _buscar_mxl_generados,
    _construir_cmd_audiveris,
    buscar_audiveris,
    pdf_a_musicxml,
)


# ---------------------------------------------------------------------------
# buscar_audiveris
# ---------------------------------------------------------------------------

def test_buscar_audiveris_usa_ruta_config(tmp_path):
    """Usa la ruta configurada si existe."""
    exe = tmp_path / "Audiveris.exe"
    exe.write_text("")
    config = {"rutas": {"audiveris": str(exe)}}
    assert buscar_audiveris(config) == exe


def test_buscar_audiveris_ruta_config_inexistente_lanza_error(tmp_path):
    """Ruta configurada inexistente lanza HerramientaNoEncontrada."""
    config = {"rutas": {"audiveris": str(tmp_path / "no_existe.exe")}}
    with pytest.raises(HerramientaNoEncontrada, match="config.toml no existe"):
        buscar_audiveris(config)


def test_buscar_audiveris_sin_nada_menciona_winget(monkeypatch):
    """Sin Audiveris instalado (ni en PATH ni en rutas típicas), el mensaje menciona winget."""
    import omr
    config = {"rutas": {"audiveris": ""}}
    # Vaciar las rutas típicas para no encontrar nada aunque Audiveris esté instalado
    monkeypatch.setattr(omr, "_RUTAS_AUDIVERIS", [])
    with patch("shutil.which", return_value=None):
        with pytest.raises(HerramientaNoEncontrada, match="winget"):
            buscar_audiveris(config)


# ---------------------------------------------------------------------------
# _construir_cmd_audiveris
# ---------------------------------------------------------------------------

def test_construir_cmd_exe(tmp_path):
    """Ejecutable normal -> comando directo."""
    exe = tmp_path / "Audiveris.exe"
    exe.write_text("")
    cmd = _construir_cmd_audiveris(exe)
    assert cmd == [str(exe)]


def test_construir_cmd_jar_con_java(tmp_path, monkeypatch):
    """Archivo .jar con java disponible -> comando java -jar."""
    import shutil
    jar = tmp_path / "audiveris.jar"
    jar.write_text("")
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/java" if n == "java" else None)
    cmd = _construir_cmd_audiveris(jar)
    assert cmd == ["/usr/bin/java", "-jar", str(jar)]


def test_construir_cmd_jar_sin_java_lanza_error(tmp_path, monkeypatch):
    """Archivo .jar sin java disponible lanza HerramientaNoEncontrada."""
    import shutil
    jar = tmp_path / "audiveris.jar"
    jar.write_text("")
    monkeypatch.setattr(shutil, "which", lambda n: None)
    with pytest.raises(HerramientaNoEncontrada, match="Java"):
        _construir_cmd_audiveris(jar)


# ---------------------------------------------------------------------------
# _buscar_mxl_generados
# ---------------------------------------------------------------------------

def test_buscar_mxl_principal(tmp_path):
    """Devuelve el .mxl principal si existe."""
    mxl = tmp_path / "partitura.mxl"
    mxl.write_text("")
    resultado = _buscar_mxl_generados(tmp_path, "partitura")
    assert resultado == [mxl]


def test_buscar_mxl_movimientos(tmp_path):
    """Devuelve movimientos en orden numérico."""
    (tmp_path / "obra.mvt2.mxl").write_text("")
    (tmp_path / "obra.mvt1.mxl").write_text("")
    (tmp_path / "obra.mvt3.mxl").write_text("")
    resultado = _buscar_mxl_generados(tmp_path, "obra")
    nombres = [f.name for f in resultado]
    assert nombres == ["obra.mvt1.mxl", "obra.mvt2.mxl", "obra.mvt3.mxl"]


def test_buscar_mxl_principal_tiene_prioridad(tmp_path):
    """Si existe el .mxl principal, ignora los .mvt."""
    (tmp_path / "obra.mxl").write_text("")
    (tmp_path / "obra.mvt1.mxl").write_text("")
    resultado = _buscar_mxl_generados(tmp_path, "obra")
    assert len(resultado) == 1
    assert resultado[0].name == "obra.mxl"


def test_buscar_mxl_sin_nada(tmp_path):
    """Devuelve lista vacía si no hay archivos."""
    assert _buscar_mxl_generados(tmp_path, "partitura") == []


# ---------------------------------------------------------------------------
# pdf_a_musicxml
# ---------------------------------------------------------------------------

def _mock_run_exitoso(cmd, *, capture_output, encoding, errors, timeout):
    """Simula subprocess.run exitoso que genera un .mxl."""
    # Extraer carpeta del argumento -output
    idx = cmd.index("-output")
    carpeta = Path(cmd[idx + 1])
    stem = Path(cmd[-1]).stem
    (carpeta / f"{stem}.mxl").write_text("")
    resultado = MagicMock()
    resultado.returncode = 0
    resultado.stdout = ""
    resultado.stderr = ""
    return resultado


def test_pdf_a_musicxml_comando_correcto(tmp_path):
    """Construye el comando de Audiveris con los argumentos correctos."""
    pdf = tmp_path / "partitura.pdf"
    pdf.write_text("")
    audiveris = tmp_path / "Audiveris.exe"
    audiveris.write_text("")

    comandos_capturados = []

    def mock_run(cmd, **kwargs):
        comandos_capturados.append(cmd)
        salida = MagicMock()
        salida.returncode = 0
        salida.stdout = ""
        salida.stderr = ""
        # Crear el archivo de salida esperado
        carpeta = Path(cmd[cmd.index("-output") + 1])
        (carpeta / f"{pdf.stem}.mxl").write_text("")
        return salida

    with patch("subprocess.run", side_effect=mock_run):
        pdf_a_musicxml(pdf, tmp_path / "salida", audiveris, timeout=30)

    cmd = comandos_capturados[0]
    assert "-batch" in cmd
    assert "-export" in cmd
    assert "-output" in cmd
    assert "--" in cmd
    assert str(pdf) in cmd


def test_pdf_a_musicxml_borra_mxl_antiguos(tmp_path):
    """Borra los .mxl del mismo stem antes de ejecutar."""
    pdf = tmp_path / "partitura.pdf"
    pdf.write_text("")
    carpeta_salida = tmp_path / "salida"
    carpeta_salida.mkdir()
    viejo = carpeta_salida / "partitura.mxl"
    viejo.write_text("viejo")

    def mock_run(cmd, **kwargs):
        # El viejo ya no debe existir
        assert not viejo.exists()
        # Crear nuevo
        (carpeta_salida / "partitura.mxl").write_text("nuevo")
        resultado = MagicMock()
        resultado.returncode = 0
        resultado.stdout = resultado.stderr = ""
        return resultado

    audiveris = tmp_path / "Audiveris.exe"
    audiveris.write_text("")

    with patch("subprocess.run", side_effect=mock_run):
        pdf_a_musicxml(pdf, carpeta_salida, audiveris, timeout=30)


def test_pdf_a_musicxml_sin_salida_lanza_error(tmp_path):
    """Si Audiveris no genera ningún .mxl, lanza ErrorOMR."""
    pdf = tmp_path / "partitura.pdf"
    pdf.write_text("")
    audiveris = tmp_path / "Audiveris.exe"
    audiveris.write_text("")

    def mock_run(cmd, **kwargs):
        resultado = MagicMock()
        resultado.returncode = 0
        resultado.stdout = resultado.stderr = ""
        return resultado

    with patch("subprocess.run", side_effect=mock_run):
        with pytest.raises(ErrorOMR, match="no ha podido reconocer"):
            pdf_a_musicxml(pdf, tmp_path / "salida", audiveris, timeout=30)


def test_pdf_a_musicxml_timeout_lanza_error(tmp_path):
    """Timeout de subprocess lanza ErrorOMR."""
    pdf = tmp_path / "partitura.pdf"
    pdf.write_text("")
    audiveris = tmp_path / "Audiveris.exe"
    audiveris.write_text("")

    def mock_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    with patch("subprocess.run", side_effect=mock_run):
        with pytest.raises(ErrorOMR, match="tardó más de"):
            pdf_a_musicxml(pdf, tmp_path / "salida", audiveris, timeout=30)
