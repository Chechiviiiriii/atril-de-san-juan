"""Punto de entrada para la distribución empaquetada de Atril de San Juan.

Este módulo es el entry point que usa PyInstaller. Delega en ``app.main()``
pero añade dos opciones de diagnóstico y prueba:

  --diagnostico <ruta_informe.txt>
      Escribe en el archivo indicado un informe de diagnóstico (versiones,
      rutas, disponibilidad de Audiveris y WebView2) y termina sin abrir
      ninguna ventana.

  --solo-servidor <puerto>
      Arranca únicamente el servidor HTTP en el puerto indicado y espera
      indefinidamente (sin ventana). Útil para pruebas automatizadas.

En uso normal, sin estas opciones, lanza la interfaz gráfica.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Directorio donde está este lanzador (dentro de _internal/ cuando está frozen,
# o en empaquetado/ en desarrollo).
_DIR_LANZADOR = Path(__file__).resolve().parent

# Raíz del proyecto: un nivel por encima de empaquetado/ (en dev) o _internal/ (frozen).
# En modo frozen, _RAIZ_PROYECTO apunta al directorio del ejecutable.
if getattr(sys, "frozen", False):
    _RAIZ_PROYECTO = Path(sys.executable).parent
    # _internal/ está dentro de la raíz; los módulos del proyecto están en sys._MEIPASS
    _DIR_MODULOS = Path(getattr(sys, "_MEIPASS", str(_RAIZ_PROYECTO)))
else:
    _RAIZ_PROYECTO = _DIR_LANZADOR.parent
    _DIR_MODULOS = _RAIZ_PROYECTO

# Asegurar que los módulos del proyecto son importables
if str(_DIR_MODULOS) not in sys.path:
    sys.path.insert(0, str(_DIR_MODULOS))

# ---------------------------------------------------------------------------
# Metadatos de la aplicación
# ---------------------------------------------------------------------------

def _cargar_datos_app() -> dict:
    """Lee empaquetado/datos_app.json.

    Cuando está frozen, app.py busca el JSON en:
      Path(app.__file__).parent / "empaquetado" / "datos_app.json"
    que equivale a  _MEIPASS / "empaquetado" / "datos_app.json".
    Aquí también buscamos ahí primero para coherencia.
    """
    candidatos = [
        _DIR_MODULOS / "empaquetado" / "datos_app.json",   # frozen: _MEIPASS/empaquetado/
        _DIR_LANZADOR / "datos_app.json",                  # frozen fallback / dev
        _RAIZ_PROYECTO / "empaquetado" / "datos_app.json", # dev: <proyecto>/empaquetado/
    ]
    for ruta in candidatos:
        if ruta.exists():
            try:
                with ruta.open(encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"nombre": "Atril de San Juan", "version": "desconocida"}


_DATOS_APP = _cargar_datos_app()
NOMBRE_APP: str = _DATOS_APP.get("nombre", "Atril de San Juan")
VERSION_APP: str = _DATOS_APP.get("version", "0.1.0")


# ---------------------------------------------------------------------------
# Modo --diagnostico
# ---------------------------------------------------------------------------

def _verificar_webview2() -> str:
    """Comprueba si el runtime de WebView2 está disponible (solo Windows)."""
    if sys.platform != "win32":
        return "Solo disponible en Windows"
    try:
        import winreg
        claves = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]
        for hive, clave in claves:
            try:
                with winreg.OpenKey(hive, clave) as k:
                    pv, _ = winreg.QueryValueEx(k, "pv")
                    if pv and pv != "0.0.0.0":
                        return f"Disponible (versión {pv})"
            except FileNotFoundError:
                pass
        return "No detectado — instala el runtime de Microsoft Edge WebView2"
    except Exception as exc:
        return f"No se pudo verificar: {exc}"


def _diagnostico(ruta_informe: str) -> None:
    """Escribe un informe de diagnóstico en ``ruta_informe`` y termina."""
    lineas: list[str] = []

    def _a(etiqueta: str, valor: str) -> None:
        lineas.append(f"{etiqueta}: {valor}")

    _a("Aplicación", f"{NOMBRE_APP} {VERSION_APP}")
    _a("Python", sys.version.replace("\n", " "))
    _a("Empaquetado (frozen)", str(getattr(sys, "frozen", False)))
    _a("sys.executable", sys.executable)

    if getattr(sys, "frozen", False):
        _a("sys._MEIPASS", getattr(sys, "_MEIPASS", "N/D"))
        _a("Raíz instalación", str(_RAIZ_PROYECTO))

    # Versiones de dependencias clave
    for nombre_mod, atrib in [
        ("music21", "__version__"),
        ("pymupdf", "__version__"),
        ("webview", "__version__"),
        ("numpy", "__version__"),
    ]:
        try:
            mod = __import__(nombre_mod)
            version = getattr(mod, atrib, "versión desconocida")
            _a(f"  {nombre_mod}", str(version))
        except ImportError as exc:
            _a(f"  {nombre_mod}", f"NO DISPONIBLE: {exc}")

    # Valores leídos por app.py desde datos_app.json
    try:
        import app as _app_mod
        _a("app.NOMBRE_APP", str(getattr(_app_mod, "NOMBRE_APP", "N/D")))
        _a("app.VERSION",    str(getattr(_app_mod, "VERSION",    "N/D")))
        _a("app.URL_REPO",   str(getattr(_app_mod, "URL_REPO",   "N/D")))
    except Exception as exc:
        _a("app (datos)", f"ERROR: {exc}")

    # Audiveris
    try:
        from atril.config import cargar_config
        from atril.omr import buscar_audiveris
        cfg = cargar_config()
        ruta_auv = buscar_audiveris(cfg)
        _a("Audiveris", str(ruta_auv))
    except Exception as exc:
        _a("Audiveris", f"ERROR: {exc}")

    # WebView2
    _a("WebView2", _verificar_webview2())

    informe = "\n".join(lineas) + "\n"
    Path(ruta_informe).write_text(informe, encoding="utf-8")
    # Terminar sin ventana
    sys.exit(0)


# ---------------------------------------------------------------------------
# Modo --solo-servidor
# ---------------------------------------------------------------------------

def _solo_servidor(puerto: int) -> None:
    """Arranca el servidor HTTP y espera indefinidamente (sin ventana)."""
    from interfaz.servidor import iniciar, limpiar_todos
    import atexit

    servidor = iniciar("127.0.0.1", puerto)
    atexit.register(limpiar_todos)
    url = f"http://127.0.0.1:{puerto}"
    # Escribir la URL en stdout para que el script de prueba pueda leerla
    try:
        sys.stdout.write(f"servidor_iniciado:{url}\n")
        sys.stdout.flush()
    except Exception:
        pass
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    servidor.shutdown()
    limpiar_todos()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def main() -> None:
    analizador = argparse.ArgumentParser(
        prog=_DATOS_APP.get("ejecutable", "AtrilDeSanJuan"),
        description=NOMBRE_APP,
        add_help=False,
    )
    analizador.add_argument("--diagnostico", metavar="INFORME", default=None,
                            help="Escribe un informe de diagnóstico y termina.")
    analizador.add_argument("--solo-servidor", metavar="PUERTO", type=int, default=None,
                            help="Arranca solo el servidor HTTP (sin ventana) en el puerto dado.")
    # Pasar los argumentos desconocidos a app.main()
    args_conocidos, resto = analizador.parse_known_args()

    if args_conocidos.diagnostico is not None:
        _diagnostico(args_conocidos.diagnostico)
        return

    if args_conocidos.solo_servidor is not None:
        _solo_servidor(args_conocidos.solo_servidor)
        return

    # Modo normal: lanzar la interfaz gráfica
    import app as _app_module
    _app_module.NOMBRE_APP = NOMBRE_APP
    _app_module.main(resto if resto else None)


if __name__ == "__main__":
    main()
