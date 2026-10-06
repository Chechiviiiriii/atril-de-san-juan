"""Módulo de renderizado de partituras con MuseScore."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import HerramientaNoEncontrada, buscar_ejecutable

# Directorio raíz del proyecto (donde vive este módulo)
_RAIZ = Path(__file__).parent

# Estilo predeterminado para nombres de notas
ESTILO_PREDETERMINADO = _RAIZ / "estilo_nombres.mss"

# Rutas típicas de instalación de MuseScore según plataforma
_RUTAS_MUSESCORE: list[Path] = [
    # Windows — MuseScore 4
    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    / "MuseScore 4" / "bin" / "MuseScore4.exe",
    # Windows — MuseScore 3
    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    / "MuseScore 3" / "bin" / "MuseScore3.exe",
    # macOS
    Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore"),
    Path("/Applications/MuseScore 3.app/Contents/MacOS/mscore"),
]

_NOMBRES_PATH_MUSESCORE = [
    "MuseScore4",
    "mscore4portable",
    "musescore",
    "MuseScore3",
    "mscore",
]

_AYUDA_MUSESCORE = (
    "No se encuentra MuseScore. "
    "Instálalo con `winget install Musescore.Musescore` "
    "o pon su ruta en config.toml, sección [rutas], clave musescore."
)


class ErrorRender(Exception):
    """Error durante la generación del PDF con MuseScore."""


def buscar_musescore(config: dict) -> Path:
    """Localiza el ejecutable de MuseScore.

    Args:
        config: Diccionario de configuración cargado con ``cargar_config()``.

    Returns:
        Ruta al ejecutable de MuseScore.

    Raises:
        HerramientaNoEncontrada: Si no se encuentra MuseScore.
    """
    return buscar_ejecutable(
        ruta_config=config.get("rutas", {}).get("musescore", ""),
        nombres_path=_NOMBRES_PATH_MUSESCORE,
        rutas_tipicas=_RUTAS_MUSESCORE,
        ayuda=_AYUDA_MUSESCORE,
    )


def convertir(
    entrada: Path,
    salida: Path,
    musescore: Path,
    timeout: int,
    estilo: Path | None = None,
) -> Path:
    """Convierte un archivo de partitura con MuseScore.

    Args:
        entrada: Archivo de entrada (MusicXML, MSCZ, etc.).
        salida: Ruta del archivo de salida (PDF, MSCZ, MusicXML…).
        musescore: Ruta al ejecutable de MuseScore.
        timeout: Tiempo máximo de espera en segundos.
        estilo: Archivo de estilo ``.mss`` opcional.

    Returns:
        Ruta al archivo generado.

    Raises:
        ErrorRender: Si MuseScore no produce el archivo de salida.
    """
    cmd: list[str] = [str(musescore)]
    if estilo is not None:
        cmd += ["-S", str(estilo)]
    cmd += ["-o", str(salida), str(entrada)]

    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ErrorRender(
            f"MuseScore tardó más de {timeout} s procesando '{entrada.name}'. "
            "Puedes aumentar timeout_render en config.toml."
        )

    if not salida.exists():
        detalle = (resultado.stdout or "") + (resultado.stderr or "")
        raise ErrorRender(
            f"MuseScore no generó el archivo de salida '{salida.name}'.\n"
            f"Código de retorno: {resultado.returncode}\n"
            f"Salida:\n{detalle[-600:]}"
        )

    return salida


def musicxml_a_pdf(
    entrada: Path,
    salida: Path,
    musescore: Path,
    timeout: int,
) -> Path:
    """Convierte un archivo MusicXML a PDF usando MuseScore.

    Aplica ``estilo_nombres.mss`` de la raíz del proyecto si existe.

    Args:
        entrada: Archivo MusicXML de entrada.
        salida: Ruta del PDF de salida.
        musescore: Ruta al ejecutable de MuseScore.
        timeout: Tiempo máximo de espera en segundos.

    Returns:
        Ruta al PDF generado.
    """
    estilo = ESTILO_PREDETERMINADO if ESTILO_PREDETERMINADO.exists() else None
    return convertir(entrada, salida, musescore, timeout, estilo)


def revisar_en_musescore(
    musicxml: Path,
    musescore: Path,
    timeout: int,
) -> Path:
    """Abre el MusicXML en MuseScore para revisión manual y devuelve el MusicXML corregido.

    Flujo:
    1. Convierte el MusicXML a ``.mscz`` en la misma carpeta.
    2. Abre el ``.mscz`` en MuseScore (sin esperar al proceso).
    3. Pide al usuario que corrija, guarde con Ctrl+S y pulse Enter.
    4. Convierte el ``.mscz`` (posiblemente modificado) de vuelta a MusicXML.
    5. Devuelve la ruta al MusicXML resultante.

    Args:
        musicxml: Archivo MusicXML a revisar.
        musescore: Ruta al ejecutable de MuseScore.
        timeout: Tiempo máximo de espera para conversiones de MuseScore.

    Returns:
        Ruta al MusicXML resultante (en la misma carpeta que ``musicxml``).
    """
    carpeta = musicxml.parent
    mscz = carpeta / (musicxml.stem + ".mscz")
    xml_revisado = carpeta / (musicxml.stem + "_revisado.musicxml")

    # Paso 1: MusicXML -> MSCZ
    convertir(musicxml, mscz, musescore, timeout)

    # Registrar mtime para detectar cambios
    mtime_antes = mscz.stat().st_mtime

    # Paso 2: Abrir en MuseScore (sin bloquear)
    subprocess.Popen([str(musescore), str(mscz)])

    # Paso 3: Instrucciones al usuario
    print(
        "\nMuseScore se ha abierto con la partitura reconocida.\n"
        "Corrige las notas, guarda con Ctrl+S y cierra MuseScore.\n"
        "Luego pulsa Enter aquí para continuar."
    )
    input()

    # Comprobar si hubo cambios
    mtime_despues = mscz.stat().st_mtime
    if mtime_despues == mtime_antes:
        print("Aviso: el archivo no fue modificado. Se continúa con el original.")

    # Paso 4: MSCZ -> MusicXML
    convertir(mscz, xml_revisado, musescore, timeout)

    return xml_revisado
