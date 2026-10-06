"""Tests de render.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atril.config import HerramientaNoEncontrada
from atril.render import ErrorRender, buscar_musescore, convertir


# ---------------------------------------------------------------------------
# buscar_musescore
# ---------------------------------------------------------------------------

def test_buscar_musescore_usa_ruta_config(tmp_path):
    """Usa la ruta configurada si existe."""
    exe = tmp_path / "MuseScore4.exe"
    exe.write_text("")
    config = {"rutas": {"musescore": str(exe)}}
    assert buscar_musescore(config) == exe


def test_buscar_musescore_ruta_config_inexistente_lanza_error(tmp_path):
    """Ruta configurada inexistente lanza HerramientaNoEncontrada."""
    config = {"rutas": {"musescore": str(tmp_path / "no_existe.exe")}}
    with pytest.raises(HerramientaNoEncontrada, match="config.toml no existe"):
        buscar_musescore(config)


def test_buscar_musescore_sin_nada_menciona_winget(monkeypatch):
    """Sin MuseScore instalado (ni en PATH ni en rutas típicas), el mensaje menciona winget."""
    import atril.render as render
    config = {"rutas": {"musescore": ""}}
    # Vaciar las rutas típicas para no encontrar nada aunque MuseScore esté instalado
    monkeypatch.setattr(render, "_RUTAS_MUSESCORE", [])
    with patch("shutil.which", return_value=None):
        with pytest.raises(HerramientaNoEncontrada, match="winget"):
            buscar_musescore(config)


# ---------------------------------------------------------------------------
# convertir
# ---------------------------------------------------------------------------

def _hacer_mock_run(salida: Path, returncode: int = 0):
    """Devuelve un mock de subprocess.run que crea el archivo de salida."""
    def mock_run(cmd, **kwargs):
        if returncode == 0:
            salida.write_text("")
        resultado = MagicMock()
        resultado.returncode = returncode
        resultado.stdout = resultado.stderr = ""
        return resultado
    return mock_run


def test_convertir_comando_sin_estilo(tmp_path):
    """Sin estilo, el comando es: mscore -o salida entrada."""
    entrada = tmp_path / "entrada.musicxml"
    entrada.write_text("")
    salida = tmp_path / "salida.pdf"
    ms = tmp_path / "mscore.exe"
    ms.write_text("")

    comandos = []

    def mock_run(cmd, **kwargs):
        comandos.append(cmd)
        salida.write_text("")
        r = MagicMock()
        r.returncode = 0
        r.stdout = r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=mock_run):
        convertir(entrada, salida, ms, timeout=60)

    cmd = comandos[0]
    assert "-S" not in cmd
    assert "-o" in cmd
    idx = cmd.index("-o")
    assert cmd[idx + 1] == str(salida)
    assert str(entrada) in cmd


def test_convertir_comando_con_estilo(tmp_path):
    """Con estilo, el comando incluye -S estilo.mss."""
    entrada = tmp_path / "entrada.musicxml"
    entrada.write_text("")
    salida = tmp_path / "salida.pdf"
    estilo = tmp_path / "estilo.mss"
    estilo.write_text("")
    ms = tmp_path / "mscore.exe"
    ms.write_text("")

    comandos = []

    def mock_run(cmd, **kwargs):
        comandos.append(cmd)
        salida.write_text("")
        r = MagicMock()
        r.returncode = 0
        r.stdout = r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=mock_run):
        convertir(entrada, salida, ms, timeout=60, estilo=estilo)

    cmd = comandos[0]
    assert "-S" in cmd
    idx = cmd.index("-S")
    assert cmd[idx + 1] == str(estilo)


def test_convertir_sin_salida_lanza_error(tmp_path):
    """Si MuseScore no genera la salida, lanza ErrorRender."""
    entrada = tmp_path / "entrada.musicxml"
    entrada.write_text("")
    salida = tmp_path / "salida.pdf"
    ms = tmp_path / "mscore.exe"
    ms.write_text("")

    def mock_run(cmd, **kwargs):
        # No crea el archivo de salida
        r = MagicMock()
        r.returncode = 0
        r.stdout = r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=mock_run):
        with pytest.raises(ErrorRender, match="no generó"):
            convertir(entrada, salida, ms, timeout=60)


def test_convertir_timeout_lanza_error(tmp_path):
    """Timeout de subprocess lanza ErrorRender."""
    entrada = tmp_path / "entrada.musicxml"
    entrada.write_text("")
    salida = tmp_path / "salida.pdf"
    ms = tmp_path / "mscore.exe"
    ms.write_text("")

    def mock_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 60)

    with patch("subprocess.run", side_effect=mock_run):
        with pytest.raises(ErrorRender, match="tardó más de"):
            convertir(entrada, salida, ms, timeout=60)
