"""Módulo de reconocimiento óptico de música (OMR) con Audiveris."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from config import HerramientaNoEncontrada, buscar_ejecutable

# Rutas típicas de instalación de Audiveris según plataforma
_RUTAS_AUDIVERIS: list[Path] = [
    # Windows
    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    / "Audiveris" / "Audiveris.exe",
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Programs" / "Audiveris" / "Audiveris.exe",
    # macOS
    Path("/Applications/Audiveris.app/Contents/MacOS/Audiveris"),
    # Linux
    Path("/opt/audiveris/bin/Audiveris"),
]

_NOMBRES_PATH_AUDIVERIS = ["audiveris", "Audiveris"]

_AYUDA_AUDIVERIS = (
    "No se encuentra Audiveris. "
    "Instálalo con `winget install audiveris.org.Audiveris` "
    "(o desde https://github.com/Audiveris/audiveris/releases) "
    "o pon su ruta en config.toml, sección [rutas], clave audiveris."
)


class ErrorOMR(Exception):
    """Error durante el reconocimiento óptico de música."""


def buscar_audiveris(config: dict) -> Path:
    """Localiza el ejecutable de Audiveris.

    Orden de búsqueda:
    1. Cuando la aplicación está empaquetada (frozen): ``<dir_exe>/audiveris/Audiveris.exe``.
    2. Ruta explícita de config.toml (si está configurada).
    3. ``shutil.which`` para cada nombre en el PATH.
    4. Rutas típicas de instalación.

    Args:
        config: Diccionario de configuración cargado con ``cargar_config()``.

    Returns:
        Ruta al ejecutable de Audiveris.

    Raises:
        HerramientaNoEncontrada: Si no se encuentra Audiveris.
    """
    # 1. Búsqueda en la carpeta de la instalación (cuando está empaquetado)
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "audiveris" / "Audiveris.exe"
        if bundled.exists():
            return bundled

    return buscar_ejecutable(
        ruta_config=config.get("rutas", {}).get("audiveris", ""),
        nombres_path=_NOMBRES_PATH_AUDIVERIS,
        rutas_tipicas=_RUTAS_AUDIVERIS,
        ayuda=_AYUDA_AUDIVERIS,
    )


def _construir_cmd_audiveris(audiveris: Path) -> list[str]:
    """Devuelve la parte inicial del comando para invocar Audiveris.

    Si la ruta es un .jar, comprueba que ``java`` está en el PATH.
    """
    if audiveris.suffix.lower() == ".jar":
        java = shutil.which("java")
        if not java:
            raise HerramientaNoEncontrada(
                "Para usar Audiveris como .jar necesitas Java 21+. "
                "Instálalo con: winget install EclipseAdoptium.Temurin.21.JRE"
            )
        return [java, "-jar", str(audiveris)]
    return [str(audiveris)]


def _buscar_mxl_generados(carpeta: Path, stem: str) -> list[Path]:
    """Busca los archivos MXL/XML generados por Audiveris para el stem dado.

    Devuelve primero ``<stem>.mxl``; si no existe, los movimientos
    ``<stem>.mvtN.mxl`` en orden numérico; si tampoco, cualquier ``.xml``.
    """
    principal = carpeta / f"{stem}.mxl"
    if principal.exists():
        return [principal]

    # Movimientos (partitura con varios movimientos)
    patron_mvt = re.compile(rf"^{re.escape(stem)}\.mvt(\d+)\.mxl$", re.IGNORECASE)
    movimientos: list[tuple[int, Path]] = []
    for f in carpeta.iterdir():
        m = patron_mvt.match(f.name)
        if m:
            movimientos.append((int(m.group(1)), f))
    if movimientos:
        return [p for _, p in sorted(movimientos)]

    # Archivos XML sin comprimir
    xml_files = sorted(carpeta.glob(f"{stem}.xml"))
    return xml_files


def _ultimas_lineas_error(texto: str, n: int = 15) -> str:
    """Extrae las últimas N líneas que contienen WARN o ERROR."""
    lineas = [
        l for l in texto.splitlines()
        if "WARN" in l or "ERROR" in l or "Exception" in l
    ]
    return "\n".join(lineas[-n:])


def pdf_a_musicxml(
    pdf: Path,
    carpeta: Path,
    audiveris: Path,
    timeout: int,
) -> list[Path]:
    """Ejecuta Audiveris sobre ``pdf`` y devuelve los archivos MXL generados.

    Args:
        pdf: Archivo PDF a reconocer.
        carpeta: Carpeta donde Audiveris deposita los resultados.
        audiveris: Ruta al ejecutable de Audiveris.
        timeout: Tiempo máximo de espera en segundos.

    Returns:
        Lista de rutas a los archivos ``.mxl`` (o ``.xml``) generados,
        ordenados: primero ``<stem>.mxl``; si hay movimientos, en orden numérico.

    Raises:
        ErrorOMR: Si Audiveris no produce salida o falla.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    stem = pdf.stem

    # Borrar MXL/XML antiguos del mismo stem para evitar confusiones
    for patron in (f"{stem}.mxl", f"{stem}.xml"):
        for viejo in carpeta.glob(patron):
            viejo.unlink()
    for viejo in carpeta.glob(f"{stem}.mvt*.mxl"):
        viejo.unlink()

    cmd = _construir_cmd_audiveris(audiveris) + [
        "-batch", "-export",
        "-output", str(carpeta),
        "--", str(pdf),
    ]

    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ErrorOMR(
            f"Audiveris tardó más de {timeout} s procesando '{pdf.name}'. "
            "Puedes aumentar timeout_omr en config.toml."
        )

    # Recopilar salida para mensajes de error
    salida_combinada = (resultado.stdout or "") + (resultado.stderr or "")
    errores_log = _ultimas_lineas_error(salida_combinada)

    # Buscar salidas aunque el código de retorno sea 0 (Audiveris siempre da 0)
    archivos = _buscar_mxl_generados(carpeta, stem)
    if not archivos:
        detalle = (
            f"\nÚltimos mensajes de Audiveris:\n{errores_log}"
            if errores_log
            else f"\nSalida de Audiveris:\n{salida_combinada[-800:]}"
        )
        raise ErrorOMR(
            f"Audiveris no ha podido reconocer la partitura '{pdf.name}'. "
            "Comprueba que el PDF contiene una partitura legible."
            + detalle
        )

    return archivos
