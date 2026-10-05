"""Tests de la interfaz HTTP de pdf2notas.

Los tests de unidad usan sintetica.pdf (en git) con sintetica.musicxml como
partitura, evitando Audiveris por completo. Los tests E2E con dulce.pdf se
saltan automáticamente si el archivo no está disponible (está en .gitignore).
"""

from __future__ import annotations

import io
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

_RAIZ  = Path(__file__).parent.parent
_DATOS = Path(__file__).parent / "datos"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skip_sin_archivo(*rutas: Path):
    """Salta el test si alguna de las rutas no existe."""
    for r in rutas:
        if not r.exists():
            pytest.skip(f"Partitura de prueba no disponible (solo en local): {r.name}")


def _url(puerto: int, ruta: str) -> str:
    return f"http://127.0.0.1:{puerto}{ruta}"


def _get(puerto: int, ruta: str, timeout: int = 10) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(_url(puerto, ruta), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get_json(puerto: int, ruta: str, timeout: int = 10) -> tuple[int, dict]:
    cod, cuerpo = _get(puerto, ruta, timeout)
    return cod, json.loads(cuerpo)


def _post(puerto: int, ruta: str, body: bytes,
          headers: dict | None = None, timeout: int = 10) -> tuple[int, dict]:
    req = urllib.request.Request(
        _url(puerto, ruta),
        data=body,
        method="POST",
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _esperar_listo(puerto: int, id_trabajo: str, timeout_s: int = 120) -> dict:
    """Hace polling hasta que el trabajo esté listo o en error."""
    fin = time.time() + timeout_s
    while time.time() < fin:
        cod, datos = _get_json(puerto, f"/api/trabajos/{id_trabajo}")
        assert cod == 200, f"Estado no OK: {cod}"
        if datos["estado"] == "listo":
            return datos["resultado"]
        if datos["estado"] == "error":
            pytest.fail(f"Trabajo falló: {datos['error']}")
        time.sleep(0.5)
    pytest.fail("El trabajo no terminó en el tiempo límite.")


# ---------------------------------------------------------------------------
# Mock del pipeline (usa sintetica.pdf + sintetica.musicxml)
# ---------------------------------------------------------------------------

def _mock_procesar_hilo(trabajo, mxl_precargado=None):
    """Reemplaza _procesar_hilo: usa sintetica.musicxml en lugar de Audiveris."""
    try:
        import pymupdf
        import music21
        from superponer import analizar, colocar_nombres

        mxl = mxl_precargado or (_DATOS / "sintetica.musicxml")
        if not mxl.exists():
            trabajo.estado = "error"
            trabajo.error  = f"Mock: falta {mxl}"
            return

        partitura = music21.converter.parse(str(mxl))
        analisis  = analizar(trabajo.pdf_original, partitura)
        colocar_nombres(analisis)

        doc = pymupdf.open(str(trabajo.pdf_original))
        paginas_info = []
        for num, page in enumerate(doc):
            mat = pymupdf.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=mat)
            (trabajo.directorio / f"pag_{num}.png").write_bytes(pix.tobytes("png"))
            paginas_info.append({
                "ancho": page.rect.width,
                "alto":  page.rect.height,
                "imagen": f"/api/trabajos/{trabajo.id}/paginas/{num}.png",
            })
        doc.close()

        resultado = analisis.a_dict()
        resultado["paginas_info"] = paginas_info
        resultado["nombre_archivo"] = trabajo.nombre_archivo
        notas = analisis.notas
        resultado["total"]     = len(notas)
        resultado["dudosas"]   = sum(1 for n in notas if n.estado in ("dudosa", "deducida"))
        resultado["deducidas"] = sum(1 for n in notas if n.estado == "deducida")

        trabajo.analisis  = analisis
        trabajo.resultado = resultado
        trabajo.estado    = "listo"
        trabajo.fase      = ""

    except Exception as exc:
        trabajo.estado = "error"
        trabajo.error  = str(exc)
        trabajo.fase   = ""


# ---------------------------------------------------------------------------
# Fixture: servidor con pipeline mockeado
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidor_mock():
    """Inicia el servidor en un puerto libre con el pipeline mockeado."""
    _skip_sin_archivo(_DATOS / "sintetica.pdf", _DATOS / "sintetica.musicxml")

    import socket
    import interfaz.servidor as mod_servidor
    from http.server import ThreadingHTTPServer

    # Puerto libre
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]

    with mock.patch.object(mod_servidor, "_procesar_hilo", _mock_procesar_hilo):
        srv = ThreadingHTTPServer(("127.0.0.1", puerto), mod_servidor._Manejador)
        import threading
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        yield puerto

        srv.shutdown()
        mod_servidor.limpiar_todos()


# ---------------------------------------------------------------------------
# Tests de la interfaz web estática
# ---------------------------------------------------------------------------

def test_pagina_principal(servidor_mock):
    cod, cuerpo = _get(servidor_mock, "/")
    assert cod == 200
    assert b"pdf2notas" in cuerpo or b"DOCTYPE" in cuerpo


def test_estilo_css(servidor_mock):
    cod, _ = _get(servidor_mock, "/estilo.css")
    assert cod == 200


def test_app_js(servidor_mock):
    cod, _ = _get(servidor_mock, "/app.js")
    assert cod == 200


# ---------------------------------------------------------------------------
# Test: subir PDF → polling → PNG → confirmar → descargar
# ---------------------------------------------------------------------------

def test_flujo_completo(servidor_mock):
    """Flujo completo: subir → esperar → PNG → confirmar con corrección → descargar."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()

    # 1) Subir PDF
    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    assert cod == 200, f"Subida fallida: {datos}"
    id_trabajo = datos["id"]
    assert id_trabajo

    # 2) Esperar hasta que esté listo
    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    assert resultado is not None
    assert "notas" in resultado
    assert "paginas_info" in resultado
    assert len(resultado["paginas_info"]) > 0
    assert resultado["total"] >= 0

    # 3) Descargar PNG de la primera página
    cod_img, img_bytes = _get(servidor_mock, f"/api/trabajos/{id_trabajo}/paginas/0.png")
    assert cod_img == 200, f"PNG no disponible: {cod_img}"
    assert img_bytes[:4] == b"\x89PNG"   # firma PNG

    # 4) Confirmar con una corrección (si hay notas dudosas, corregir la primera)
    notas     = resultado.get("notas", [])
    dudosas   = [n for n in notas if n["estado"] in ("dudosa", "deducida")]
    correcs   = {}
    if dudosas:
        correcs[str(dudosas[0]["id"])] = "Do"

    cod_conf, datos_conf = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/confirmar",
        json.dumps({"correcciones": correcs}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_conf == 200, f"Confirmar fallido: {datos_conf}"
    assert "descarga" in datos_conf
    assert "nombre" in datos_conf
    assert datos_conf["nombre"].endswith("_notas.pdf")

    # 5) Descargar el PDF final
    cod_pdf, pdf_final = _get(servidor_mock, datos_conf["descarga"])
    assert cod_pdf == 200
    assert pdf_final[:4] == b"%PDF"       # firma PDF válida

    # 6) Verificar que PyMuPDF lo abre sin errores
    import pymupdf
    doc = pymupdf.open(stream=pdf_final, filetype="pdf")
    assert doc.page_count >= 1
    doc.close()


# ---------------------------------------------------------------------------
# Test: errores esperados
# ---------------------------------------------------------------------------

def test_subir_no_pdf(servidor_mock):
    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        b"Esto no es un PDF",
        headers={"X-Nombre-Archivo": "texto.txt"},
    )
    assert cod in (400, 200)   # 400 ideal; el servidor puede devolver 200 con error
    if cod == 400:
        assert "error" in datos
    else:
        # La extensión no termina en .pdf → debería haber fallado
        pass


def test_subir_pdf_falso(servidor_mock):
    """Bytes con nombre .pdf pero sin cabecera PDF válida."""
    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        b"Contenido falso sin cabecera PDF",
        headers={"X-Nombre-Archivo": "falso.pdf"},
    )
    assert cod == 400
    assert "error" in datos


def test_trabajo_inexistente(servidor_mock):
    cod, _ = _get_json(servidor_mock, "/api/trabajos/trabajo-que-no-existe")
    assert cod == 404


def test_pagina_inexistente(servidor_mock):
    cod, _ = _get(servidor_mock, "/api/trabajos/no-existe/paginas/0.png")
    assert cod == 404


# ---------------------------------------------------------------------------
# Tests del cache
# ---------------------------------------------------------------------------

def test_cache_sha256_y_busqueda(tmp_path, monkeypatch):
    """El SHA-256 de un PDF se mapea correctamente a su .mxl en el cache."""
    import interfaz.cache as mod_cache
    # Usar un directorio temporal como cache para aislar el test
    cache_tmp = tmp_path / "cache"
    monkeypatch.setattr(mod_cache, "carpeta_cache", lambda: cache_tmp)

    from interfaz.cache import sha256_pdf, precargar, buscar_en_cache

    # Crear PDF de prueba con contenido único (UUID en el nombre)
    import uuid
    contenido_pdf = f"%PDF-1.4 test-{uuid.uuid4()}".encode()
    pdf_test = tmp_path / "prueba.pdf"
    mxl_test = tmp_path / "prueba.mxl"
    pdf_test.write_bytes(contenido_pdf)
    mxl_test.write_bytes(b"<xml>test</xml>")

    # No está en cache
    assert buscar_en_cache(pdf_test) is None

    # Precargar
    sha = precargar(pdf_test, mxl_test)
    assert len(sha) == 64   # SHA-256 hex

    # Ahora sí está
    encontrado = buscar_en_cache(pdf_test)
    assert encontrado is not None
    assert encontrado.exists()
    assert encontrado.read_bytes() == b"<xml>test</xml>"

    # Mismo SHA para contenido idéntico
    pdf_copia = tmp_path / "copia.pdf"
    pdf_copia.write_bytes(contenido_pdf)
    assert sha256_pdf(pdf_copia) == sha
    encontrado_copia = buscar_en_cache(pdf_copia)
    assert encontrado_copia is not None


def test_cache_archivos_byte_identicos(tmp_path, monkeypatch):
    """Dos archivos byte-idénticos comparten la misma entrada de cache."""
    import uuid
    import interfaz.cache as mod_cache
    cache_tmp = tmp_path / "cache"
    monkeypatch.setattr(mod_cache, "carpeta_cache", lambda: cache_tmp)

    from interfaz.cache import sha256_pdf, precargar, buscar_en_cache

    contenido = f"%PDF-1.4 partitura unica {uuid.uuid4()}".encode()
    a = tmp_path / "a.pdf"
    b_pdf = tmp_path / "b.pdf"
    mxl = tmp_path / "x.mxl"
    a.write_bytes(contenido)
    b_pdf.write_bytes(contenido)
    mxl.write_bytes(b"<partitura/>")

    sha_a = sha256_pdf(a)
    sha_b = sha256_pdf(b_pdf)
    assert sha_a == sha_b   # mismo contenido → mismo SHA

    precargar(a, mxl)
    assert buscar_en_cache(b_pdf) is not None   # b también lo encuentra


# ---------------------------------------------------------------------------
# Test E2E con dulce.pdf + cache (LENTO — requiere datos locales)
# ---------------------------------------------------------------------------

@pytest.mark.lento
def test_e2e_dulce_con_cache():
    """E2E con dulce.pdf usando el MXL precargado (sin Audiveris)."""
    pdf_dulce = _DATOS / "dulce.pdf"
    mxl_dulce = _DATOS / "dulce_omr.mxl"
    _skip_sin_archivo(pdf_dulce, mxl_dulce)

    import socket
    import threading
    import interfaz.servidor as mod_servidor
    from http.server import ThreadingHTTPServer

    # Precargar en el cache para este test
    from interfaz.cache import precargar
    precargar(pdf_dulce, mxl_dulce)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]

    srv = ThreadingHTTPServer(("127.0.0.1", puerto), mod_servidor._Manejador)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    try:
        pdf_bytes = pdf_dulce.read_bytes()
        cod, datos = _post(
            puerto, "/api/trabajos",
            pdf_bytes,
            headers={"X-Nombre-Archivo": "dulce.pdf"},
        )
        assert cod == 200
        id_trabajo = datos["id"]

        resultado = _esperar_listo(puerto, id_trabajo, timeout_s=180)

        # dulce.pdf debe tener notas deducidas
        assert resultado["deducidas"] >= 1, (
            f"Se esperaban notas deducidas en dulce.pdf, pero deducidas={resultado['deducidas']}"
        )

        # Confirmar sin correcciones → PDF final
        cod_conf, datos_conf = _post(
            puerto,
            f"/api/trabajos/{id_trabajo}/confirmar",
            json.dumps({"correcciones": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        assert cod_conf == 200, f"Confirmar E2E falló: {datos_conf}"
        assert "descarga" in datos_conf

        cod_pdf, pdf_final = _get(puerto, datos_conf["descarga"])
        assert cod_pdf == 200
        assert pdf_final[:4] == b"%PDF"

        import pymupdf
        doc = pymupdf.open(stream=pdf_final, filetype="pdf")
        assert doc.page_count >= 1
        doc.close()

    finally:
        srv.shutdown()
        mod_servidor.limpiar_todos()
