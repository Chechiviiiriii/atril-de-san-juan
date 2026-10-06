"""Lanzador de la interfaz gráfica de pdf2notas.

Inicia el servidor HTTP local y abre la ventana de la aplicación con pywebview
(Edge WebView2 en Windows). Si pywebview no está disponible, abre el navegador
del sistema.

Opciones:
    --navegador         Usa el navegador en lugar de pywebview.
    --puerto N          Puerto HTTP (0 = automático).
    --precargar-ejemplos  Precarga el cache con las partituras de tests/datos/.
"""

from __future__ import annotations

import argparse
import atexit
import shutil
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

# Datos de la aplicación (único punto de definición; los mismos que usa el instalador)
# Si el empaquetador pone empaquetado/datos_app.json, se usa como fuente primaria.
def _leer_datos_app() -> tuple[str, str, str]:
    """Lee nombre, versión y URL del repo desde empaquetado/datos_app.json si existe."""
    import json as _json
    ruta_json = Path(__file__).parent / "empaquetado" / "datos_app.json"
    if ruta_json.exists():
        try:
            d = _json.loads(ruta_json.read_text(encoding="utf-8"))
            return (
                d.get("nombre", "Atril de San Juan"),
                d.get("version", "0.1.0"),
                d.get("url_fuente") or d.get("url_repo") or "https://github.com/Chechiviiiriii/atril-de-san-juan",
            )
        except Exception:
            pass
    return (
        "Atril de San Juan",
        "0.1.0",
        "https://github.com/Chechiviiiriii/atril-de-san-juan",
    )

NOMBRE_APP, VERSION, URL_REPO = _leer_datos_app()

# Raíz del proyecto
_RAIZ = Path(__file__).parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


# ---------------------------------------------------------------------------
# Utilidades de red
# ---------------------------------------------------------------------------

def _puerto_libre(puerto_deseado: int = 0) -> int:
    """Devuelve un puerto TCP libre en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", puerto_deseado))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Precarga de ejemplos
# ---------------------------------------------------------------------------

def precargar_ejemplos() -> None:
    """Precarga el cache de Audiveris con las partituras de prueba.

    Los PDFs raíz ``Tú eres Victoria Tuba.pdf`` y ``Dulce Mirada de Jesus Tbn 1º Do.pdf``
    son byte-idénticos a los de ``tests/datos/``, por lo que el mismo SHA-256
    sirve para ambos.
    """
    from interfaz.cache import precargar, sha256_pdf

    datos = _RAIZ / "tests" / "datos"

    pares_base: list[tuple[Path, Path]] = [
        (datos / "victoria.pdf",  datos / "victoria_omr.mxl"),
        (datos / "dulce.pdf",     datos / "dulce_omr.mxl"),
    ]

    # PDFs del directorio raíz que pueden ser byte-idénticos a los de tests/datos
    pares_raiz: list[tuple[Path, Path]] = [
        (_RAIZ / "Tú eres Victoria Tuba.pdf",              datos / "victoria_omr.mxl"),
        (_RAIZ / "Dulce Mirada de Jesus Tbn 1º Do.pdf",    datos / "dulce_omr.mxl"),
    ]

    cargados = 0
    sha_ya_cargados: set[str] = set()

    def _cargar(pdf: Path, mxl: Path, etiquetar: str) -> None:
        nonlocal cargados
        if not pdf.exists():
            return
        if not mxl.exists():
            print(f"  Aviso: falta el MXL {mxl.name}, omitiendo {etiquetar}.")
            return
        sha = sha256_pdf(pdf)
        if sha in sha_ya_cargados:
            print(f"  {etiquetar} → mismo SHA que uno ya cargado, se omite.")
            return
        try:
            precargar(pdf, mxl)
            sha_ya_cargados.add(sha)
            cargados += 1
            print(f"  Cargado: {etiquetar} (SHA …{sha[-8:]})")
        except Exception as exc:
            print(f"  Error cargando {etiquetar}: {exc}")

    print("Precargando ejemplos en el cache…")
    for pdf, mxl in pares_base:
        _cargar(pdf, mxl, pdf.name)

    for pdf, mxl in pares_raiz:
        _cargar(pdf, mxl, pdf.name)

    if cargados:
        print(f"Cache listo: {cargados} partituras precargadas.")
    else:
        print("No se precargó ninguna partitura (¿faltan archivos en tests/datos/).")


# ---------------------------------------------------------------------------
# Inicio del servidor
# ---------------------------------------------------------------------------

def iniciar_servidor(puerto: int) -> object:
    """Arranca el servidor HTTP y devuelve el objeto servidor."""
    from interfaz.servidor import iniciar
    return iniciar("127.0.0.1", puerto)


# ---------------------------------------------------------------------------
# API JS para pywebview
# ---------------------------------------------------------------------------

def _pdf_final(id_: str) -> Optional[Path]:
    """PDF final de un trabajo de nombres o de un empalme, según el id."""
    from interfaz.servidor import _get_trabajo, _get_resultado_empalme

    for origen in (_get_trabajo(id_), _get_resultado_empalme(id_)):
        if origen is not None and origen.pdf_final is not None:
            return origen.pdf_final
    return None


class _ApiJS:
    """Métodos expuestos al JavaScript de la ventana pywebview."""

    def guardar_pdf(self, id_trabajo: str) -> bool:
        """Abre el diálogo nativo «Guardar como» y copia el PDF final."""
        try:
            import webview

            pdf_final = _pdf_final(id_trabajo)
            if pdf_final is None:
                return False

            nombre_sugerido = pdf_final.name
            ventanas = webview.windows
            if not ventanas:
                return False

            resultado = ventanas[0].create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=nombre_sugerido,
                file_types=("PDF (*.pdf)",),
            )
            if not resultado:
                return False

            destino = resultado[0] if isinstance(resultado, (list, tuple)) else resultado
            shutil.copy2(str(pdf_final), str(destino))
            return True

        except Exception:
            return False

    def abrir_enlace(self, url: str) -> None:
        """Abre una URL externa en el navegador predeterminado del sistema.

        Solo acepta URLs del repositorio oficial para evitar uso como proxy.
        """
        _PREFIX = "https://github.com/Chechiviiiriii/"
        if not isinstance(url, str) or not url.startswith(_PREFIX):
            return
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def abrir_pdf(self, id_trabajo: str) -> None:
        """Abre el PDF final de un trabajo o empalme con el visor del sistema."""
        try:
            pdf_final = _pdf_final(id_trabajo)
            if pdf_final is None:
                return
            ruta = str(pdf_final)
            import os
            if sys.platform == "win32":
                os.startfile(ruta)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", ruta], check=False)
            else:
                import subprocess
                subprocess.run(["xdg-open", ruta], check=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    analizador = argparse.ArgumentParser(
        prog="app",
        description=f"Interfaz gráfica de {NOMBRE_APP}",
    )
    analizador.add_argument(
        "--navegador",
        action="store_true",
        help="Abrir en el navegador del sistema en lugar de en la ventana integrada.",
    )
    analizador.add_argument(
        "--puerto",
        type=int,
        default=0,
        metavar="N",
        help="Puerto HTTP (0 = automático).",
    )
    analizador.add_argument(
        "--precargar-ejemplos",
        action="store_true",
        help="Precargar el cache con las partituras de tests/datos/ al arrancar.",
    )
    args = analizador.parse_args(argv)

    if args.precargar_ejemplos:
        precargar_ejemplos()

    puerto = args.puerto if args.puerto else _puerto_libre()
    url = f"http://127.0.0.1:{puerto}"
    servidor = iniciar_servidor(puerto)

    from interfaz.servidor import limpiar_todos
    atexit.register(limpiar_todos)

    # ------------------------------------------------------------------
    # Modo navegador
    # ------------------------------------------------------------------
    if args.navegador:
        print(f"{NOMBRE_APP} iniciado en {url}")
        print("Presiona Ctrl+C para detener.")
        webbrowser.open(url)
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        servidor.shutdown()
        return

    # ------------------------------------------------------------------
    # Intentar pywebview; si no está disponible, usar el navegador
    # ------------------------------------------------------------------
    try:
        import webview  # type: ignore[import]
    except ImportError:
        print(f"pywebview no disponible. Abriendo en el navegador: {url}")
        webbrowser.open(url)
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        servidor.shutdown()
        return

    api = _ApiJS()
    webview.create_window(
        title=NOMBRE_APP,
        url=url,
        width=1280,
        height=860,
        min_size=(1000, 700),
        js_api=api,
    )

    webview.start(debug=False)

    # Al llegar aquí, la ventana se ha cerrado
    limpiar_todos()
    servidor.shutdown()


if __name__ == "__main__":
    main()
