"""Cache de resultados de Audiveris basada en SHA-256 del PDF.

La clave es el SHA-256 del archivo PDF; el valor es el archivo .mxl generado
por Audiveris. Si el .mxl ya existe en el cache, se omite el paso de OMR.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def carpeta_cache() -> Path:
    """Devuelve la carpeta del cache según el sistema operativo."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_CACHE_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "pdf2notas" / "cache"


def sha256_pdf(pdf: Path) -> str:
    """Calcula el SHA-256 de un archivo PDF."""
    h = hashlib.sha256()
    with open(pdf, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def ruta_en_cache(sha: str) -> Path:
    """Devuelve la ruta del .mxl en el cache para el SHA dado."""
    return carpeta_cache() / f"{sha}.mxl"


def buscar_en_cache(pdf: Path) -> Path | None:
    """Devuelve la ruta al .mxl cacheado para el PDF, o None si no existe."""
    sha = sha256_pdf(pdf)
    ruta = ruta_en_cache(sha)
    return ruta if ruta.exists() else None


def guardar_en_cache(pdf: Path, mxl: Path) -> Path:
    """Guarda el .mxl en el cache con clave SHA-256 del PDF. Devuelve la ruta."""
    sha = sha256_pdf(pdf)
    destino = ruta_en_cache(sha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(mxl), str(destino))
    return destino


def precargar(pdf: Path, mxl: Path) -> str:
    """Precarga un .mxl en el cache para el PDF dado. Devuelve el SHA-256."""
    sha = sha256_pdf(pdf)
    destino = ruta_en_cache(sha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(mxl), str(destino))
    return sha
