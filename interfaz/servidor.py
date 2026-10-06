"""Servidor HTTP local para la interfaz gráfica de pdf2notas.

Expone los endpoints REST que consume la SPA en interfaz/web/.
Gestiona trabajos de procesamiento en hilos de fondo.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

# Asegurar que el directorio raíz esté en sys.path para importar los módulos del proyecto
_RAIZ = Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

_WEB = Path(__file__).parent / "web"

# ---------------------------------------------------------------------------
# Preferencias de usuario (tutoriales vistos, etc.)
# ---------------------------------------------------------------------------

# Sobreescribible en tests para aislar el archivo de preferencias
_ruta_prefs_override: Optional[Path] = None


def _ruta_preferencias() -> Path:
    """Devuelve la ruta al archivo JSON de preferencias del usuario."""
    if _ruta_prefs_override is not None:
        return _ruta_prefs_override
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Atril de San Juan" / "preferencias.json"
    else:
        return Path.home() / ".config" / "atril-de-san-juan" / "preferencias.json"


def _leer_preferencias() -> dict:
    """Lee las preferencias desde disco; devuelve estructura por defecto si no existe."""
    try:
        return json.loads(_ruta_preferencias().read_text(encoding="utf-8"))
    except Exception:
        return {"tutoriales_vistos": []}


def _guardar_preferencias(datos: dict) -> None:
    """Persiste las preferencias en disco."""
    ruta = _ruta_preferencias()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Metadatos de la aplicación (importados desde app.py para ser fuente única)
# ---------------------------------------------------------------------------
try:
    from app import NOMBRE_APP as _NOMBRE_APP, VERSION as _VERSION, URL_REPO as _URL_REPO
except Exception:
    _NOMBRE_APP = "Atril de San Juan"
    _VERSION    = "0.1.0"
    _URL_REPO   = "https://github.com/Chechiviiiriii/atril-de-san-juan"

# ---------------------------------------------------------------------------
# Gestión de trabajos de nombrado
# ---------------------------------------------------------------------------

class _Trabajo:
    """Estado de un trabajo de procesamiento de nombres."""

    def __init__(self, id: str) -> None:
        self.id = id
        self.estado: str = "procesando"
        self.fase: str = "Iniciando…"
        self.error: Optional[str] = None
        self.resultado: Optional[dict] = None
        self.analisis = None                       # objeto Analisis de superponer.py
        self.pdf_original: Optional[Path] = None   # ruta al PDF en el dir temporal
        self.pdf_final: Optional[Path] = None      # ruta al PDF final con nombres
        self.nombre_archivo: Optional[str] = None
        self._tmpdir = tempfile.TemporaryDirectory()
        self.directorio = Path(self._tmpdir.name)

    def limpiar(self) -> None:
        try:
            self._tmpdir.cleanup()
        except Exception:
            pass


_trabajos: dict[str, _Trabajo] = {}
_lock_trabajos = threading.Lock()


def _crear_trabajo() -> tuple[str, _Trabajo]:
    id_trabajo = str(uuid.uuid4())
    trabajo = _Trabajo(id_trabajo)
    with _lock_trabajos:
        _trabajos[id_trabajo] = trabajo
    return id_trabajo, trabajo


def _get_trabajo(id_trabajo: str) -> Optional[_Trabajo]:
    with _lock_trabajos:
        return _trabajos.get(id_trabajo)


# ---------------------------------------------------------------------------
# Gestión de archivos de empalme
# ---------------------------------------------------------------------------

class _ArchivoEmpalme:
    """Un PDF subido para empalmar."""

    def __init__(self, id: str) -> None:
        self.id = id
        self.titulo: str = ""
        self.nombre_archivo: str = ""
        self.paginas: int = 0
        self.sha256: str = ""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.directorio = Path(self._tmpdir.name)
        self.ruta_pdf: Optional[Path] = None
        self.ruta_miniatura: Optional[Path] = None

    def limpiar(self) -> None:
        try:
            self._tmpdir.cleanup()
        except Exception:
            pass


class _ResultadoEmpalme:
    """PDF resultante de un empalme."""

    def __init__(self, id: str) -> None:
        self.id = id
        self._tmpdir = tempfile.TemporaryDirectory()
        self.directorio = Path(self._tmpdir.name)
        self.pdf_final: Optional[Path] = None
        self.nombre_archivo: Optional[str] = None

    def limpiar(self) -> None:
        try:
            self._tmpdir.cleanup()
        except Exception:
            pass


_archivos_empalme: dict[str, _ArchivoEmpalme] = {}
_resultados_empalme: dict[str, _ResultadoEmpalme] = {}
_lock_empalme = threading.Lock()


def _crear_archivo_empalme() -> tuple[str, _ArchivoEmpalme]:
    id_ = str(uuid.uuid4())
    arch = _ArchivoEmpalme(id_)
    with _lock_empalme:
        _archivos_empalme[id_] = arch
    return id_, arch


def _get_archivo_empalme(id_: str) -> Optional[_ArchivoEmpalme]:
    with _lock_empalme:
        return _archivos_empalme.get(id_)


def _crear_resultado_empalme() -> tuple[str, _ResultadoEmpalme]:
    id_ = str(uuid.uuid4())
    res = _ResultadoEmpalme(id_)
    with _lock_empalme:
        _resultados_empalme[id_] = res
    return id_, res


def _get_resultado_empalme(id_: str) -> Optional[_ResultadoEmpalme]:
    with _lock_empalme:
        return _resultados_empalme.get(id_)


def limpiar_todos() -> None:
    """Elimina todos los directorios temporales."""
    with _lock_trabajos:
        for t in _trabajos.values():
            t.limpiar()
        _trabajos.clear()
    with _lock_empalme:
        for a in _archivos_empalme.values():
            a.limpiar()
        _archivos_empalme.clear()
        for r in _resultados_empalme.values():
            r.limpiar()
        _resultados_empalme.clear()


# ---------------------------------------------------------------------------
# Pipeline de procesamiento (función de módulo patcheable en tests)
# ---------------------------------------------------------------------------

def _procesar_hilo(trabajo: _Trabajo, mxl_precargado: Optional[Path] = None) -> None:
    """Ejecuta el pipeline completo en un hilo de fondo."""
    try:
        import pymupdf
        import music21

        from config import cargar_config, HerramientaNoEncontrada
        from omr import buscar_audiveris, pdf_a_musicxml
        from superponer import analizar, colocar_nombres, SinCabezasError
        from interfaz.cache import buscar_en_cache, guardar_en_cache

        config = cargar_config()
        pdf = trabajo.pdf_original

        # --- Paso 1: obtener MXL (cache o Audiveris) ---
        mxl = mxl_precargado
        if mxl is None:
            trabajo.fase = "Buscando en caché…"
            mxl = buscar_en_cache(pdf)

        if mxl is None:
            trabajo.fase = "Reconociendo con Audiveris…"
            try:
                audiveris = buscar_audiveris(config)
            except HerramientaNoEncontrada:
                raise RuntimeError(
                    "Audiveris no está instalado. "
                    "Instálalo con:\n  winget install audiveris.org.Audiveris\n"
                    "o descárgalo en https://github.com/Audiveris/audiveris/releases"
                )
            timeout = config.get("opciones", {}).get("timeout_omr", 900)
            carpeta_omr = trabajo.directorio / "omr"
            mxls = pdf_a_musicxml(pdf, carpeta_omr, audiveris, timeout)
            mxl = mxls[0]
            try:
                guardar_en_cache(pdf, mxl)
            except Exception:
                pass

        # --- Paso 2: parsear partitura ---
        trabajo.fase = "Leyendo la partitura…"
        partitura = music21.converter.parse(str(mxl))

        # --- Paso 3: analizar PDF + OMR ---
        trabajo.fase = "Buscando notas dudosas…"
        try:
            analisis = analizar(pdf, partitura)
        except SinCabezasError as exc:
            raise RuntimeError(
                "No se detectaron cabezas de nota en el PDF. "
                "Este archivo puede ser un PDF escaneado (imagen) en lugar de vectorial. "
                "pdf2notas solo funciona con partituras exportadas directamente "
                "desde Sibelius, MuseScore, Finale u otro editor de partituras."
            ) from exc

        # --- Paso 4: calcular posiciones ---
        trabajo.fase = "Colocando nombres…"
        colocar_nombres(analisis)

        # --- Paso 5: pre-renderizar páginas como PNG ---
        trabajo.fase = "Generando vista previa…"
        doc = pymupdf.open(str(pdf))
        paginas_info = []
        for num, page in enumerate(doc):
            mat = pymupdf.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=mat)
            ruta_img = trabajo.directorio / f"pag_{num}.png"
            pix.save(str(ruta_img))
            paginas_info.append({
                "ancho": page.rect.width,
                "alto": page.rect.height,
                "imagen": f"/api/trabajos/{trabajo.id}/paginas/{num}.png",
            })
        doc.close()

        # --- Construir resultado ---
        resultado = analisis.a_dict()
        resultado["paginas_info"] = paginas_info
        resultado["nombre_archivo"] = trabajo.nombre_archivo
        notas = analisis.notas
        resultado["total"] = len(notas)
        resultado["dudosas"] = sum(1 for n in notas if n.estado in ("dudosa", "deducida"))
        resultado["deducidas"] = sum(1 for n in notas if n.estado == "deducida")

        trabajo.analisis = analisis
        trabajo.resultado = resultado
        trabajo.estado = "listo"
        trabajo.fase = ""

    except Exception as exc:
        trabajo.estado = "error"
        trabajo.error = str(exc)
        trabajo.fase = ""


# ---------------------------------------------------------------------------
# Manejador HTTP
# ---------------------------------------------------------------------------

_TIPOS_MIME: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
}


class _Manejador(BaseHTTPRequestHandler):

    def log_message(self, format: str, *args) -> None:  # type: ignore[override]
        pass  # suprimir log de acceso

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str = "application/json") -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo: int, datos: dict) -> None:
        self._enviar(
            codigo,
            json.dumps(datos, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, codigo: int, mensaje: str) -> None:
        self._json(codigo, {"error": mensaje})

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Nombre-Archivo")
        self.end_headers()

    def do_GET(self) -> None:
        ruta = self.path.split("?")[0]

        # Archivos estáticos de la SPA
        if ruta in ("/", "/index.html"):
            self._servir_archivo(_WEB / "index.html")
            return

        # Archivos en interfaz/web/ servidos desde cualquier sub-ruta relativa
        ruta_web = (_WEB / ruta.lstrip("/")).resolve()
        try:
            ruta_web.relative_to(_WEB)  # seguridad: no salir de _WEB
        except ValueError:
            self._error(403, "Acceso no permitido.")
            return

        if ruta_web.exists() and ruta_web.is_file() and not ruta.startswith("/api/"):
            self._servir_archivo(ruta_web)
            return

        # API info
        if ruta == "/api/info":
            self._json(200, {
                "nombre": _NOMBRE_APP,
                "version": _VERSION,
                "url_repo": _URL_REPO,
            })
            return

        # API preferencias
        if ruta == "/api/preferencias":
            self._json(200, _leer_preferencias())
            return

        # API REST — trabajos de nombres
        if ruta.startswith("/api/trabajos"):
            sub = ruta[len("/api/trabajos"):].lstrip("/")
            self._api_get(sub)
            return

        # API REST — empalme
        if ruta.startswith("/api/empalme"):
            sub = ruta[len("/api/empalme"):].lstrip("/")
            self._api_empalme_get(sub)
            return

        self._error(404, "No encontrado.")

    def do_POST(self) -> None:
        ruta = self.path.split("?")[0]

        if ruta == "/api/preferencias":
            self._api_guardar_preferencias()
            return

        if ruta == "/api/trabajos":
            self._api_nuevo_trabajo()
            return

        if ruta.startswith("/api/trabajos/"):
            partes = ruta[len("/api/trabajos/"):].split("/")
            if len(partes) >= 2 and partes[1] == "confirmar":
                self._api_confirmar(partes[0])
                return
            if len(partes) >= 2 and partes[1] == "recolocar":
                self._api_recolocar(partes[0])
                return

        if ruta == "/api/empalme/archivos":
            self._api_empalme_subir()
            return

        if ruta == "/api/empalme/unir":
            self._api_empalme_unir()
            return

        self._error(404, "No encontrado.")

    # ------------------------------------------------------------------
    # Servir archivos estáticos
    # ------------------------------------------------------------------

    def _servir_archivo(self, ruta: Path) -> None:
        if not ruta.exists() or not ruta.is_file():
            self._error(404, f"Archivo no encontrado: {ruta.name}")
            return
        tipo = _TIPOS_MIME.get(ruta.suffix.lower(), "application/octet-stream")
        try:
            datos = ruta.read_bytes()
            self._enviar(200, datos, tipo)
        except OSError as exc:
            self._error(500, f"Error al leer {ruta.name}: {exc}")

    # ------------------------------------------------------------------
    # POST /api/preferencias
    # ------------------------------------------------------------------

    def _api_guardar_preferencias(self) -> None:
        """Guarda las preferencias del usuario o las reinicia si se pasa reiniciar=true."""
        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(longitud)
        try:
            datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
        except Exception:
            self._error(400, "JSON inválido.")
            return

        if datos.get("reiniciar"):
            _guardar_preferencias({"tutoriales_vistos": []})
            self._json(200, {"ok": True, "reiniciado": True})
            return

        # Validar y normalizar
        vistos = datos.get("tutoriales_vistos")
        if not isinstance(vistos, list):
            self._error(400, "El campo tutoriales_vistos debe ser una lista.")
            return

        prefs_actuales = _leer_preferencias()
        prefs_actuales["tutoriales_vistos"] = [
            str(p) for p in vistos if isinstance(p, str)
        ]
        try:
            _guardar_preferencias(prefs_actuales)
        except Exception as exc:
            self._error(500, f"Error al guardar preferencias: {exc}")
            return

        self._json(200, {"ok": True})

    # ------------------------------------------------------------------
    # POST /api/trabajos
    # ------------------------------------------------------------------

    def _api_nuevo_trabajo(self) -> None:
        longitud = int(self.headers.get("Content-Length", 0))
        if longitud == 0:
            self._error(400, "No se recibió ningún archivo.")
            return

        nombre_enc = self.headers.get("X-Nombre-Archivo", "partitura.pdf")
        try:
            nombre = unquote(nombre_enc, encoding="utf-8")
        except Exception:
            nombre = nombre_enc

        if not nombre.lower().endswith(".pdf"):
            self._error(400, "Solo se aceptan archivos PDF.")
            return

        cuerpo = self.rfile.read(longitud)
        if not cuerpo.startswith(b"%PDF"):
            self._error(400, "El archivo no parece un PDF válido.")
            return

        id_trabajo, trabajo = _crear_trabajo()
        trabajo.nombre_archivo = nombre

        ruta_pdf = trabajo.directorio / nombre
        ruta_pdf.write_bytes(cuerpo)
        trabajo.pdf_original = ruta_pdf

        # Comprobar cache antes de lanzar el hilo
        try:
            from interfaz.cache import buscar_en_cache
            mxl_cache = buscar_en_cache(ruta_pdf)
        except Exception:
            mxl_cache = None

        hilo = threading.Thread(
            target=_procesar_hilo,
            args=(trabajo, mxl_cache),
            daemon=True,
        )
        hilo.start()

        self._json(200, {"id": id_trabajo})

    # ------------------------------------------------------------------
    # GET /api/trabajos/...
    # ------------------------------------------------------------------

    def _api_get(self, sub: str) -> None:
        if not sub:
            self._error(404, "ID de trabajo no especificado.")
            return

        partes = sub.split("/")
        id_trabajo = partes[0]

        trabajo = _get_trabajo(id_trabajo)
        if trabajo is None:
            self._error(404, f"Trabajo no encontrado: {id_trabajo}")
            return

        if len(partes) == 1:
            self._json(200, {
                "estado": trabajo.estado,
                "fase": trabajo.fase,
                "error": trabajo.error,
                "resultado": trabajo.resultado,
            })
            return

        if len(partes) >= 3 and partes[1] == "paginas":
            nombre_pag = partes[2]
            try:
                n = int(nombre_pag.replace(".png", "").replace(".PNG", ""))
            except ValueError:
                self._error(400, "Número de página inválido.")
                return
            ruta_img = trabajo.directorio / f"pag_{n}.png"
            self._servir_archivo(ruta_img)
            return

        if len(partes) >= 2 and partes[1] == "pdf":
            if trabajo.pdf_final is None or not trabajo.pdf_final.exists():
                self._error(404, "PDF final no disponible aún.")
                return
            self._enviar_pdf(trabajo.pdf_final)
            return

        self._error(404, "Endpoint no encontrado.")

    def _enviar_pdf(self, ruta: Path) -> None:
        """Envía un PDF con cabeceras de descarga."""
        try:
            from urllib.parse import quote
            nombre_enc = quote(ruta.name, encoding="utf-8")
        except Exception:
            nombre_enc = ruta.name

        datos = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{nombre_enc}",
        )
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(datos)

    # ------------------------------------------------------------------
    # POST /api/trabajos/<id>/confirmar
    # ------------------------------------------------------------------

    def _api_confirmar(self, id_trabajo: str) -> None:
        trabajo = _get_trabajo(id_trabajo)
        if trabajo is None:
            self._error(404, f"Trabajo no encontrado: {id_trabajo}")
            return

        if trabajo.estado != "listo" or trabajo.analisis is None:
            self._error(400, "El trabajo no está listo para confirmar.")
            return

        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(longitud)
        try:
            datos = json.loads(cuerpo.decode("utf-8"))
        except Exception:
            self._error(400, "JSON inválido.")
            return

        correcciones: dict = datos.get("correcciones", {})

        try:
            from superponer import colocar_nombres, escribir_pdf

            analisis = trabajo.analisis

            # Aplicar correcciones del usuario (acepta formato nuevo {texto?,x?,base?,tam?}
            # y formato antiguo string)
            for nota in analisis.notas:
                id_str = str(nota.id)
                if id_str not in correcciones:
                    continue
                corr = correcciones[id_str]
                if isinstance(corr, str):
                    # Formato antiguo: solo texto
                    nota.texto = corr
                    nota.estado = "confirmada"
                else:
                    # Formato nuevo: objeto con campos opcionales
                    if "texto" in corr:
                        nota.texto = corr["texto"]
                        nota.estado = "confirmada"
                    if corr.get("fija") or "x" in corr:
                        nota.fija = True
                        if "x" in corr:
                            nota.x = float(corr["x"])
                        if "base" in corr:
                            nota.base = float(corr["base"])
                        if "tam" in corr:
                            nota.tam = float(corr["tam"])

            # Recalcular posiciones respetando notas fijas
            colocar_nombres(analisis)

            # Escribir PDF final (todas las notas en negro)
            stem = Path(trabajo.nombre_archivo).stem
            nombre_salida = f"{stem}_notas.pdf"
            ruta_salida = trabajo.directorio / nombre_salida
            escribir_pdf(analisis, ruta_salida, color_dudosas=False)

            trabajo.pdf_final = ruta_salida

            self._json(200, {
                "descarga": f"/api/trabajos/{id_trabajo}/pdf",
                "nombre": nombre_salida,
            })

        except Exception as exc:
            self._error(500, f"Error al generar el PDF: {exc}")

    # ------------------------------------------------------------------
    # POST /api/trabajos/<id>/recolocar
    # ------------------------------------------------------------------

    def _api_recolocar(self, id_trabajo: str) -> None:
        """Recomputa posiciones con las correcciones actuales y las devuelve."""
        trabajo = _get_trabajo(id_trabajo)
        if trabajo is None:
            self._error(404, f"Trabajo no encontrado: {id_trabajo}")
            return

        if trabajo.estado != "listo" or trabajo.analisis is None:
            self._error(400, "El trabajo no está listo.")
            return

        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(longitud)
        try:
            datos = json.loads(cuerpo.decode("utf-8"))
        except Exception:
            self._error(400, "JSON inválido.")
            return

        correcciones: dict = datos.get("correcciones", {})

        try:
            from superponer import colocar_nombres

            analisis = trabajo.analisis

            # Aplicar correcciones (misma lógica que en confirmar)
            for nota in analisis.notas:
                id_str = str(nota.id)
                if id_str not in correcciones:
                    # Si no hay corrección, asegurarse de que no esté marcada como fija
                    # salvo que ya lo estuviera de una llamada anterior
                    continue
                corr = correcciones[id_str]
                if isinstance(corr, str):
                    nota.texto = corr
                    nota.fija = False
                else:
                    if "texto" in corr:
                        nota.texto = corr["texto"]
                    if corr.get("fija") or "x" in corr:
                        nota.fija = True
                        if "x" in corr:
                            nota.x = float(corr["x"])
                        if "base" in corr:
                            nota.base = float(corr["base"])
                        if "tam" in corr:
                            nota.tam = float(corr["tam"])
                    else:
                        nota.fija = False

            # Recalcular posiciones
            colocar_nombres(analisis)

            # Devolver posiciones de todas las notas
            posiciones = [
                {
                    "id": n.id,
                    "x": n.x,
                    "base": n.base,
                    "tam": n.tam,
                    "sin_hueco": n.sin_hueco,
                }
                for n in analisis.notas
                if n.x is not None
            ]
            self._json(200, {"posiciones": posiciones})

        except Exception as exc:
            self._error(500, f"Error al recolocar: {exc}")

    # ------------------------------------------------------------------
    # API Empalme
    # ------------------------------------------------------------------

    def _api_empalme_get(self, sub: str) -> None:
        """GET /api/empalme/..."""
        partes = sub.split("/")

        # GET /api/empalme/archivos/<id>/miniatura
        if len(partes) >= 3 and partes[0] == "archivos" and partes[2] == "miniatura":
            arch = _get_archivo_empalme(partes[1])
            if arch is None:
                self._error(404, "Archivo no encontrado.")
                return
            if arch.ruta_miniatura and arch.ruta_miniatura.exists():
                self._servir_archivo(arch.ruta_miniatura)
            else:
                self._error(404, "Miniatura no disponible.")
            return

        # GET /api/empalme/resultado/<id>/pdf
        if len(partes) >= 3 and partes[0] == "resultado" and partes[2] == "pdf":
            res = _get_resultado_empalme(partes[1])
            if res is None:
                self._error(404, "Resultado no encontrado.")
                return
            if res.pdf_final and res.pdf_final.exists():
                self._enviar_pdf(res.pdf_final)
            else:
                self._error(404, "PDF final no disponible.")
            return

        self._error(404, "Endpoint de empalme no encontrado.")

    def _api_empalme_subir(self) -> None:
        """POST /api/empalme/archivos — Sube un PDF para empalmar."""
        longitud = int(self.headers.get("Content-Length", 0))
        if longitud == 0:
            self._error(400, "No se recibió ningún archivo.")
            return

        nombre_enc = self.headers.get("X-Nombre-Archivo", "marcha.pdf")
        try:
            nombre = unquote(nombre_enc, encoding="utf-8")
        except Exception:
            nombre = nombre_enc

        if not nombre.lower().endswith(".pdf"):
            self._error(400, "Solo se aceptan archivos PDF.")
            return

        cuerpo = self.rfile.read(longitud)
        if not cuerpo.startswith(b"%PDF"):
            self._error(400, "El archivo no parece un PDF válido.")
            return

        id_, arch = _crear_archivo_empalme()
        arch.nombre_archivo = nombre
        arch.sha256 = hashlib.sha256(cuerpo).hexdigest()

        ruta_pdf = arch.directorio / nombre
        ruta_pdf.write_bytes(cuerpo)
        arch.ruta_pdf = ruta_pdf

        try:
            import pymupdf
            from empalme import titulo_pdf, contar_paginas

            arch.titulo = titulo_pdf(ruta_pdf)
            arch.paginas = contar_paginas(ruta_pdf)

            # Generar miniatura de la primera página
            doc = pymupdf.open(str(ruta_pdf))
            if doc.page_count > 0:
                page = doc[0]
                mat = pymupdf.Matrix(0.5, 0.5)
                pix = page.get_pixmap(matrix=mat)
                ruta_min = arch.directorio / "miniatura.png"
                pix.save(str(ruta_min))
                arch.ruta_miniatura = ruta_min
            doc.close()

        except Exception as exc:
            arch.titulo = Path(nombre).stem
            arch.paginas = 0

        self._json(200, {
            "id": id_,
            "titulo": arch.titulo,
            "archivo": nombre,
            "paginas": arch.paginas,
            "sha256": arch.sha256,
            "miniatura": f"/api/empalme/archivos/{id_}/miniatura",
        })

    def _api_empalme_unir(self) -> None:
        """POST /api/empalme/unir — Une los PDFs en el orden indicado."""
        longitud = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(longitud)
        try:
            datos = json.loads(cuerpo.decode("utf-8"))
        except Exception:
            self._error(400, "JSON inválido.")
            return

        ids: list[str] = datos.get("ids", [])
        nombre_salida: str = datos.get("nombre", "Marchas empalmadas")
        if not nombre_salida.lower().endswith(".pdf"):
            nombre_salida += ".pdf"

        if len(ids) < 2:
            self._error(400, "Se necesitan al menos 2 marchas para empalmar.")
            return

        archivos: list[_ArchivoEmpalme] = []
        for id_ in ids:
            arch = _get_archivo_empalme(id_)
            if arch is None:
                self._error(404, f"Archivo no encontrado: {id_}")
                return
            if arch.ruta_pdf is None or not arch.ruta_pdf.exists():
                self._error(404, f"Archivo PDF no disponible: {id_}")
                return
            archivos.append(arch)

        try:
            from empalme import unir_pdfs

            id_res, resultado = _crear_resultado_empalme()
            resultado.nombre_archivo = nombre_salida

            ruta_salida = resultado.directorio / nombre_salida
            unir_pdfs([a.ruta_pdf for a in archivos], ruta_salida)
            resultado.pdf_final = ruta_salida

            self._json(200, {
                "descarga": f"/api/empalme/resultado/{id_res}/pdf",
                "nombre": nombre_salida,
            })

        except Exception as exc:
            self._error(500, f"Error al unir los PDFs: {exc}")


# ---------------------------------------------------------------------------
# Función de inicio
# ---------------------------------------------------------------------------

def iniciar(host: str = "127.0.0.1", puerto: int = 0) -> ThreadingHTTPServer:
    """Crea y arranca el servidor HTTP en un hilo de fondo."""
    servidor = ThreadingHTTPServer((host, puerto), _Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor
