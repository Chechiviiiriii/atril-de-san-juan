# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para Atril de San Juan.

Genera un paquete onedir (carpeta única) en modo windowed (sin consola),
apto para ser empaquetado con el instalador de Inno Setup.
"""

import json
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

SPEC_DIR = Path(SPECPATH).resolve()           # empaquetado/
PROYECTO = SPEC_DIR.parent                    # raíz del proyecto

# Leer metadatos de la app
with (SPEC_DIR / "datos_app.json").open(encoding="utf-8") as _f:
    _DATOS = json.load(_f)

NOMBRE_EJECUTABLE = _DATOS["ejecutable"]      # AtrilDeSanJuan
NOMBRE_APP        = _DATOS["nombre"]          # Atril de San Juan
VERSION           = _DATOS["version"]

# ---------------------------------------------------------------------------
# Recolección de dependencias dinámicas
# ---------------------------------------------------------------------------

webview_datas, webview_binaries, webview_hidden = collect_all("webview")
clr_loader_datas, clr_loader_binaries, clr_loader_hidden = collect_all("clr_loader")
pythonnet_datas, pythonnet_binaries, pythonnet_hidden = collect_all("pythonnet")

# music21: incluir todo EXCEPTO el corpus (partituras de ejemplo, muy pesadas)
music21_datas_all = collect_data_files("music21")
music21_datas = [
    (src, dst)
    for src, dst in music21_datas_all
    if "/corpus/" not in src.replace("\\", "/")
       and "\\corpus\\" not in src
]

# pymupdf necesita sus propios binarios
fitz_datas, fitz_binaries, fitz_hidden = collect_all("pymupdf")

# ---------------------------------------------------------------------------
# Datas del proyecto
# ---------------------------------------------------------------------------

project_datas = [
    # Archivos de setuptools que PyInstaller no incluye automáticamente
    (str(Path(__import__("setuptools").__file__).parent / "_vendor" / "jaraco" / "text" / "Lorem ipsum.txt"),
     "setuptools/_vendor/jaraco/text"),
    # Archivos web de la interfaz
    (str(PROYECTO / "interfaz" / "web"), "interfaz/web"),
    # Hoja de estilos de nombres musicales (ahora en atril/)
    (str(PROYECTO / "atril" / "estilo_nombres.mss"), "atril"),
    # Configuración por defecto (los usuarios pueden editarla)
    (str(PROYECTO / "config.toml"), "."),
    # Metadatos de la app en la ruta que app.py espera: empaquetado/datos_app.json
    # (app.py lee Path(__file__).parent / "empaquetado" / "datos_app.json")
    (str(SPEC_DIR / "datos_app.json"), "empaquetado"),
]

all_datas = (
    project_datas
    + webview_datas
    + clr_loader_datas
    + pythonnet_datas
    + music21_datas
    + fitz_datas
)

all_binaries = (
    webview_binaries
    + clr_loader_binaries
    + pythonnet_binaries
    + fitz_binaries
)

hidden_imports = list(set(
    webview_hidden
    + clr_loader_hidden
    + pythonnet_hidden
    + fitz_hidden
    + [
        # Backends de pywebview en Windows
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "webview.platforms.mshtml",
        "webview.platforms.win32",
        # pythonnet / clr
        "clr",
        "clr_loader",
        "clr_loader.ffi",
        "clr_loader.ffi.hostfxr",
        "clr_loader.ffi.netfx",
        "clr_loader.hostfxr",
        "clr_loader.netfx",
        "clr_loader.util.find",
        # music21 MusicXML
        "music21",
        "music21.corpus",
        "music21.musicxml",
        "music21.musicxml.m21ToXml",
        "music21.musicxml.xmlToM21",
        "music21.musicxml.fromMxObjects",
        "music21.musicxml.toMxObjects",
        "music21.converter",
        "music21.stream",
        "music21.note",
        "music21.pitch",
        # pymupdf / fitz
        "pymupdf",
        "fitz",
        # atril: módulos del motor importados de forma diferida
        "atril",
        "atril.config",
        "atril.nombres",
        "atril.omr",
        "atril.render",
        "atril.superponer",
        "atril.verificacion",
        "atril.empalme",
    ]
))

# ---------------------------------------------------------------------------
# Módulos a excluir (dependencias opcionales de music21 no necesarias)
# ---------------------------------------------------------------------------

excludes = [
    "matplotlib",
    "matplotlib.backends",
    "scipy",
    "tkinter",
    "_tkinter",
    "IPython",
    "notebook",
    "jupyter_core",
    "nbformat",
    "nbconvert",
    "docutils",
    "sphinx",
    "py2app",
    "wx",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "gi",
    "gtk",
    # "music21.corpus" NO se excluye: music21 lo importa al arrancar.
    # Sus partituras de ejemplo (lo pesado) ya se quitan de los datos más arriba.
]

# ---------------------------------------------------------------------------
# Directorio de hooks adicionales (pythonnet incluye el suyo propio)
# ---------------------------------------------------------------------------

import pythonnet as _pn
_PYTHONNET_HOOK_DIR = str(Path(_pn.__file__).parent / "_pyinstaller")

# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

a = Analysis(
    [str(SPEC_DIR / "lanzador.py")],
    pathex=[str(PROYECTO)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[_PYTHONNET_HOOK_DIR],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE_EJECUTABLE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,        # Sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SPEC_DIR / "icono.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NOMBRE_EJECUTABLE,
)
