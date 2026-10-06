"""Configuración del proyecto pdf2notas."""

from __future__ import annotations

import shutil
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-reuse-of-import]
    except ImportError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

# Valores por defecto cuando no hay config.toml
_DEFAULTS: dict = {
    "rutas": {"audiveris": "", "musescore": ""},
    "opciones": {"timeout_omr": 900, "timeout_render": 300},
}


class HerramientaNoEncontrada(Exception):
    """Se lanza cuando no se puede localizar un ejecutable requerido."""


def cargar_config(ruta: Path | None = None) -> dict:
    """Lee config.toml junto al script; devuelve valores por defecto si no existe.

    Args:
        ruta: Ruta explícita al archivo TOML. Si es None, busca ``config.toml``
              en el directorio del módulo.

    Returns:
        Diccionario con las claves ``rutas`` y ``opciones``.

    Raises:
        ValueError: Si el archivo TOML está mal escrito.
    """
    if ruta is None:
        # config.toml está en la raíz del proyecto (un nivel por encima de atril/)
        # En modo frozen (PyInstaller), __file__ apunta a _internal/atril/,
        # por lo que parent.parent es _internal/, donde también está config.toml.
        ruta = Path(__file__).parent.parent / "config.toml"

    if not ruta.exists():
        return _clonar_defaults()

    if tomllib is None:  # pragma: no cover
        raise ImportError(
            "Instala tomli con 'pip install tomli' para usar Python < 3.11"
        )

    try:
        with ruta.open("rb") as f:
            datos = tomllib.load(f)
    except Exception as exc:
        raise ValueError(
            f"Error al leer {ruta}: {exc}\n"
            "Comprueba que el archivo TOML está bien escrito."
        ) from exc

    # Fusionar con valores por defecto para no perder claves omitidas
    config = _clonar_defaults()
    for seccion, valores in datos.items():
        if seccion in config and isinstance(valores, dict):
            config[seccion].update(valores)
        else:
            config[seccion] = valores
    return config


def _clonar_defaults() -> dict:
    """Devuelve una copia profunda de los valores por defecto."""
    return {
        seccion: dict(valores)
        for seccion, valores in _DEFAULTS.items()
    }


def buscar_ejecutable(
    ruta_config: str,
    nombres_path: list[str],
    rutas_tipicas: list[Path],
    ayuda: str,
) -> Path:
    """Localiza un ejecutable según prioridades.

    Orden de búsqueda:
    1. Ruta explícita de config.toml (si está configurada).
    2. ``shutil.which`` para cada nombre en ``nombres_path``.
    3. Rutas típicas de instalación.

    Args:
        ruta_config: Valor de la clave de configuración (puede ser vacío).
        nombres_path: Nombres a buscar en el PATH del sistema.
        rutas_tipicas: Rutas absolutas donde suele instalarse la herramienta.
        ayuda: Mensaje de error si no se encuentra nada.

    Returns:
        Ruta al ejecutable encontrado.

    Raises:
        HerramientaNoEncontrada: Si no se localiza el ejecutable.
    """
    # 1. Ruta configurada explícitamente
    if ruta_config:
        p = Path(ruta_config)
        if p.exists():
            return p
        raise HerramientaNoEncontrada(
            f"La ruta configurada en config.toml no existe: {ruta_config}"
        )

    # 2. Buscar en el PATH del sistema
    for nombre in nombres_path:
        encontrado = shutil.which(nombre)
        if encontrado:
            return Path(encontrado)

    # 3. Rutas típicas de instalación
    for ruta in rutas_tipicas:
        if ruta.exists():
            return ruta

    raise HerramientaNoEncontrada(ayuda)
