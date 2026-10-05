"""Tests de config.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import HerramientaNoEncontrada, buscar_ejecutable, cargar_config


# ---------------------------------------------------------------------------
# cargar_config
# ---------------------------------------------------------------------------

def test_cargar_config_sin_archivo_devuelve_defaults(tmp_path):
    """Sin config.toml devuelve los valores por defecto."""
    cfg = cargar_config(tmp_path / "no_existe.toml")
    assert cfg["rutas"]["audiveris"] == ""
    assert cfg["rutas"]["musescore"] == ""
    assert cfg["opciones"]["timeout_omr"] == 900
    assert cfg["opciones"]["timeout_render"] == 300


def test_cargar_config_lee_valores(tmp_path):
    """Carga correctamente los valores del TOML."""
    toml = tmp_path / "config.toml"
    toml.write_text(
        '[rutas]\naudiveris = "/ruta/audiveris"\n'
        '[opciones]\ntimeout_omr = 600\n',
        encoding="utf-8",
    )
    cfg = cargar_config(toml)
    assert cfg["rutas"]["audiveris"] == "/ruta/audiveris"
    assert cfg["opciones"]["timeout_omr"] == 600
    # timeout_render no especificado -> valor por defecto
    assert cfg["opciones"]["timeout_render"] == 300


def test_cargar_config_toml_malo_lanza_value_error(tmp_path):
    """Un TOML mal formado lanza ValueError."""
    toml = tmp_path / "config.toml"
    toml.write_text("esto no es toml válido = [[[", encoding="utf-8")
    with pytest.raises(ValueError, match="Error al leer"):
        cargar_config(toml)


# ---------------------------------------------------------------------------
# buscar_ejecutable
# ---------------------------------------------------------------------------

def test_buscar_ejecutable_ruta_config_valida(tmp_path):
    """Usa la ruta de config si existe."""
    exe = tmp_path / "mi_exe.exe"
    exe.write_text("")
    resultado = buscar_ejecutable(
        str(exe), [], [], "ayuda no usada"
    )
    assert resultado == exe


def test_buscar_ejecutable_ruta_config_inexistente_lanza_error(tmp_path):
    """Si la ruta de config no existe, lanza HerramientaNoEncontrada."""
    ruta_falsa = str(tmp_path / "no_existe.exe")
    with pytest.raises(HerramientaNoEncontrada, match="config.toml no existe"):
        buscar_ejecutable(ruta_falsa, [], [], "ayuda")


def test_buscar_ejecutable_en_path(monkeypatch, tmp_path):
    """Encuentra el ejecutable a través de shutil.which."""
    exe = tmp_path / "herramienta"
    exe.write_text("")

    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: str(exe) if name == "herramienta" else None)

    resultado = buscar_ejecutable("", ["herramienta"], [], "ayuda")
    assert resultado == exe


def test_buscar_ejecutable_rutas_tipicas(tmp_path):
    """Encuentra el ejecutable en las rutas típicas."""
    exe = tmp_path / "exe"
    exe.write_text("")

    resultado = buscar_ejecutable("", [], [tmp_path / "no_existe", exe], "ayuda")
    assert resultado == exe


def test_buscar_ejecutable_no_encontrado_mensaje_winget():
    """Si no encuentra nada, el mensaje de error menciona winget."""
    ayuda = "Instálalo con winget install algo"
    with pytest.raises(HerramientaNoEncontrada, match="winget"):
        buscar_ejecutable("", [], [], ayuda)


def test_buscar_ejecutable_ruta_config_tiene_prioridad(monkeypatch, tmp_path):
    """La ruta de config tiene prioridad sobre el PATH."""
    exe_config = tmp_path / "config_exe"
    exe_config.write_text("")
    exe_path = tmp_path / "path_exe"
    exe_path.write_text("")

    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: str(exe_path))

    resultado = buscar_ejecutable(str(exe_config), ["algo"], [], "ayuda")
    assert resultado == exe_config
