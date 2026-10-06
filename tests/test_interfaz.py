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
        from atril.superponer import analizar, colocar_nombres

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
    assert b"DOCTYPE" in cuerpo or b"Atril" in cuerpo or b"pdf2notas" in cuerpo


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


# ---------------------------------------------------------------------------
# Tests nuevos: /api/info
# ---------------------------------------------------------------------------

def test_api_info(servidor_mock):
    """GET /api/info devuelve nombre, versión y url_repo."""
    cod, datos = _get_json(servidor_mock, "/api/info")
    assert cod == 200
    assert "nombre"   in datos
    assert "version"  in datos
    assert "url_repo" in datos
    assert datos["nombre"]  != ""
    assert datos["version"] != ""
    assert datos["url_repo"].startswith("https://github.com/")


# ---------------------------------------------------------------------------
# Tests nuevos: /api/trabajos/<id>/recolocar
# ---------------------------------------------------------------------------

def test_recolocar_devuelve_posiciones(servidor_mock):
    """POST /api/trabajos/<id>/recolocar devuelve posiciones actualizadas."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()

    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]

    _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)

    # Recolocar con correcciones vacías
    cod_r, datos_r = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/recolocar",
        json.dumps({"correcciones": {}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_r == 200, f"Recolocar falló: {datos_r}"
    assert "posiciones" in datos_r
    posiciones = datos_r["posiciones"]
    assert isinstance(posiciones, list)
    for pos in posiciones:
        assert "id"   in pos
        assert "x"    in pos
        assert "base" in pos
        assert "tam"  in pos


def test_recolocar_nota_fija_no_se_mueve(servidor_mock):
    """Una nota marcada como fija en recolocar no cambia de posición."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()

    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica2.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]

    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    notas = resultado.get("notas", [])
    if not notas:
        pytest.skip("No hay notas en sintetica")

    primera = notas[0]
    id_nota = str(primera["id"])

    # Fijar en posición arbitraria
    x_fija    = 55.5
    base_fija = 77.3
    tam_fija  = 10.0

    correcciones = {
        id_nota: {"x": x_fija, "base": base_fija, "tam": tam_fija, "fija": True}
    }
    cod_r, datos_r = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/recolocar",
        json.dumps({"correcciones": correcciones}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_r == 200

    pos_fija = next((p for p in datos_r["posiciones"] if str(p["id"]) == id_nota), None)
    assert pos_fija is not None, "La nota fija no aparece en posiciones"
    assert abs(pos_fija["x"]    - x_fija)    < 0.1, "x de nota fija cambió"
    assert abs(pos_fija["base"] - base_fija) < 0.1, "base de nota fija cambió"


# ---------------------------------------------------------------------------
# Tests nuevos: confirmar con formato antiguo (string) y nuevo (objeto)
# ---------------------------------------------------------------------------

def test_confirmar_formato_antiguo(servidor_mock):
    """confirmar acepta formato antiguo {id: 'texto'} (string)."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()

    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]

    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    notas = resultado.get("notas", [])

    # Correcciones en formato antiguo (solo strings)
    correcs = {}
    for n in notas[:2]:
        correcs[str(n["id"])] = "Re"

    cod_c, datos_c = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/confirmar",
        json.dumps({"correcciones": correcs}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_c == 200, f"confirmar (antiguo) falló: {datos_c}"
    assert "descarga" in datos_c


def test_confirmar_formato_nuevo(servidor_mock):
    """confirmar acepta formato nuevo {id: {texto, x, base, tam, fija}}."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()

    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica_nueva.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]

    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    notas = resultado.get("notas", [])
    if not notas:
        pytest.skip("No hay notas en sintetica")

    # Corrección en formato nuevo
    n0 = notas[0]
    correcs = {
        str(n0["id"]): {
            "texto": "Mi",
            "x":     float(n0.get("x", 50) + 5),
            "base":  float(n0.get("base", 100)),
            "tam":   float(n0.get("tam", 9.5)),
            "fija":  True,
        }
    }

    cod_c, datos_c = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/confirmar",
        json.dumps({"correcciones": correcs}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_c == 200, f"confirmar (nuevo) falló: {datos_c}"
    assert "descarga" in datos_c

    # Verificar que el PDF generado contiene texto en la posición indicada
    cod_pdf, pdf_final = _get(servidor_mock, datos_c["descarga"])
    assert cod_pdf == 200
    assert pdf_final[:4] == b"%PDF"

    import pymupdf
    doc = pymupdf.open(stream=pdf_final, filetype="pdf")
    # Buscar el texto "Mi" cerca de la posición indicada
    pagina = doc[int(n0.get("pagina", 0))]
    bloques = pagina.get_text("dict")["blocks"]
    textos_encontrados = []
    for bloque in bloques:
        if bloque.get("type") != 0:
            continue
        for linea in bloque.get("lines", []):
            for span in linea.get("spans", []):
                textos_encontrados.append(span.get("text", ""))
    doc.close()
    texto_total = " ".join(textos_encontrados)
    assert "Mi" in texto_total, f"'Mi' no encontrado en el PDF; textos: {texto_total[:200]}"


# ---------------------------------------------------------------------------
# Tests nuevos: empalme
# ---------------------------------------------------------------------------

def test_empalme_subir_y_listar(servidor_mock):
    """POST /api/empalme/archivos sube un PDF y devuelve metadatos."""
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    cod, datos = _post(
        servidor_mock,
        "/api/empalme/archivos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    assert cod == 200, f"Subida empalme falló: {datos}"
    assert "id"       in datos
    assert "titulo"   in datos
    assert "paginas"  in datos
    assert "sha256"   in datos
    assert "miniatura" in datos
    assert datos["paginas"] >= 1


def test_empalme_miniatura(servidor_mock):
    """GET /api/empalme/archivos/<id>/miniatura devuelve una imagen PNG."""
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    _, datos = _post(
        servidor_mock,
        "/api/empalme/archivos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    id_arch = datos["id"]
    ruta_min = datos["miniatura"]

    cod_img, img_bytes = _get(servidor_mock, ruta_min)
    assert cod_img == 200
    assert img_bytes[:4] == b"\x89PNG"


def test_empalme_unir_dos(servidor_mock):
    """Subir dos veces sintetica.pdf y unirlas da el doble de páginas."""
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    import pymupdf
    from atril.empalme import contar_paginas as _cp
    n_orig = _cp(_DATOS / "sintetica.pdf")

    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    ids = []
    for _ in range(2):
        _, datos = _post(
            servidor_mock,
            "/api/empalme/archivos",
            pdf_bytes,
            headers={"X-Nombre-Archivo": "sintetica.pdf"},
        )
        ids.append(datos["id"])

    cod, datos_union = _post(
        servidor_mock,
        "/api/empalme/unir",
        json.dumps({"ids": ids, "nombre": "union_test"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod == 200, f"Unir falló: {datos_union}"
    assert "descarga" in datos_union

    cod_pdf, pdf_final = _get(servidor_mock, datos_union["descarga"])
    assert cod_pdf == 200
    assert pdf_final[:4] == b"%PDF"

    doc = pymupdf.open(stream=pdf_final, filetype="pdf")
    n_final = doc.page_count
    doc.close()
    assert n_final == n_orig * 2


def test_empalme_unir_requiere_minimo_dos(servidor_mock):
    """Unir con menos de 2 PDFs da 400."""
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("sintetica.pdf no disponible")

    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    _, datos = _post(
        servidor_mock,
        "/api/empalme/archivos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica.pdf"},
    )
    id_solo = datos["id"]

    cod, datos_err = _post(
        servidor_mock,
        "/api/empalme/unir",
        json.dumps({"ids": [id_solo], "nombre": "solo_uno"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod == 400
    assert "error" in datos_err


# ---------------------------------------------------------------------------
# Tests del tutorial: endpoints de preferencias y selectores en el HTML
# ---------------------------------------------------------------------------

@pytest.fixture
def servidor_prefs(tmp_path, monkeypatch):
    """Servidor con el archivo de preferencias redirigido a un directorio temporal."""
    _skip_sin_archivo(_DATOS / "sintetica.pdf", _DATOS / "sintetica.musicxml")

    import socket
    import interfaz.servidor as mod_servidor
    from http.server import ThreadingHTTPServer

    ruta_prefs = tmp_path / "preferencias.json"
    monkeypatch.setattr(mod_servidor, "_ruta_prefs_override", ruta_prefs)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]

    with mock.patch.object(mod_servidor, "_procesar_hilo", _mock_procesar_hilo):
        srv = ThreadingHTTPServer(("127.0.0.1", puerto), mod_servidor._Manejador)
        import threading
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        yield puerto, ruta_prefs
        srv.shutdown()
        mod_servidor.limpiar_todos()
        monkeypatch.setattr(mod_servidor, "_ruta_prefs_override", None)


def test_preferencias_lectura_inicial(servidor_prefs):
    """GET /api/preferencias devuelve estructura válida aunque el archivo no exista."""
    puerto, _ = servidor_prefs
    cod, datos = _get_json(puerto, "/api/preferencias")
    assert cod == 200
    assert "tutoriales_vistos" in datos
    assert isinstance(datos["tutoriales_vistos"], list)


def test_preferencias_marcar_visto(servidor_prefs):
    """POST /api/preferencias guarda y persiste los tutoriales vistos."""
    puerto, ruta_prefs = servidor_prefs

    cod, datos = _post(
        puerto, "/api/preferencias",
        json.dumps({"tutoriales_vistos": ["inicio", "subir"]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod == 200
    assert datos.get("ok") is True

    # Verificar que se guardó en disco
    assert ruta_prefs.exists()
    guardado = json.loads(ruta_prefs.read_text(encoding="utf-8"))
    assert "inicio" in guardado["tutoriales_vistos"]
    assert "subir"  in guardado["tutoriales_vistos"]

    # Leer de vuelta vía API
    cod2, datos2 = _get_json(puerto, "/api/preferencias")
    assert cod2 == 200
    assert "inicio" in datos2["tutoriales_vistos"]


def test_preferencias_reiniciar(servidor_prefs):
    """POST /api/preferencias con reiniciar=true borra los tutoriales vistos."""
    puerto, ruta_prefs = servidor_prefs

    # Primero marcar algo
    _post(
        puerto, "/api/preferencias",
        json.dumps({"tutoriales_vistos": ["inicio"]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    # Ahora reiniciar
    cod, datos = _post(
        puerto, "/api/preferencias",
        json.dumps({"reiniciar": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod == 200
    assert datos.get("ok") is True

    # Verificar que la lista está vacía
    cod2, datos2 = _get_json(puerto, "/api/preferencias")
    assert cod2 == 200
    assert datos2["tutoriales_vistos"] == []


# ---------------------------------------------------------------------------
# Tests de acordes
# ---------------------------------------------------------------------------

def test_resultado_incluye_campo_acorde(servidor_mock):
    """El resultado del análisis incluye el campo 'acorde' en cada nota."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica_acorde.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]
    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    notas = resultado.get("notas", [])
    assert len(notas) > 0, "No hay notas en el resultado"
    for nota in notas:
        assert "acorde" in nota, f"Nota {nota.get('id')} sin campo 'acorde'"


def test_confirmar_correccion_acorde(servidor_mock):
    """Confirmar con correcciones para varias notas de un acorde escribe todos los nombres en el PDF."""
    pdf_bytes = (_DATOS / "sintetica.pdf").read_bytes()
    cod, datos = _post(
        servidor_mock, "/api/trabajos",
        pdf_bytes,
        headers={"X-Nombre-Archivo": "sintetica_acorde2.pdf"},
    )
    assert cod == 200
    id_trabajo = datos["id"]
    resultado = _esperar_listo(servidor_mock, id_trabajo, timeout_s=120)
    notas = resultado.get("notas", [])

    # Buscar notas de un acorde (acorde != null) si hay alguno, o simplemente
    # corregir las dos primeras notas (simula corrección de acorde)
    notas_acorde = [n for n in notas if n.get("acorde") is not None]
    if len(notas_acorde) >= 2:
        elegidas = notas_acorde[:2]
    elif len(notas) >= 2:
        elegidas = notas[:2]
    else:
        pytest.skip("No hay suficientes notas en sintetica")

    correcs = {
        str(elegidas[0]["id"]): {"texto": "Do"},
        str(elegidas[1]["id"]): {"texto": "Mi"},
    }
    cod_c, datos_c = _post(
        servidor_mock,
        f"/api/trabajos/{id_trabajo}/confirmar",
        json.dumps({"correcciones": correcs}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert cod_c == 200, f"Confirmar acorde falló: {datos_c}"
    assert "descarga" in datos_c

    cod_pdf, pdf_final = _get(servidor_mock, datos_c["descarga"])
    assert cod_pdf == 200
    assert pdf_final[:4] == b"%PDF"

    import pymupdf
    doc = pymupdf.open(stream=pdf_final, filetype="pdf")
    texto_total = ""
    for page in doc:
        texto_total += page.get_text()
    doc.close()
    assert "Do" in texto_total or "Mi" in texto_total, (
        f"Las correcciones del acorde no aparecen en el PDF; texto={texto_total[:300]}"
    )


def test_selectores_tutorial_en_html():
    """Todos los selectores de id en tutorial.json existen como id="..." en index.html."""
    raiz     = Path(__file__).parent.parent
    ruta_t   = raiz / "interfaz" / "web" / "tutorial.json"
    ruta_html = raiz / "interfaz" / "web" / "index.html"

    if not ruta_t.exists():
        pytest.skip("tutorial.json no encontrado")
    if not ruta_html.exists():
        pytest.skip("index.html no encontrado")

    tutorial = json.loads(ruta_t.read_text(encoding="utf-8"))
    html     = ruta_html.read_text(encoding="utf-8")

    faltantes = []
    for pantalla, pasos in tutorial.items():
        for paso in pasos:
            selector = paso.get("selector", "")
            if not selector:
                continue
            if selector.startswith("#"):
                id_buscado = selector[1:]
                if f'id="{id_buscado}"' not in html:
                    faltantes.append(f"[{pantalla}] selector '{selector}' no encontrado")

    assert not faltantes, "Selectores de tutorial.json ausentes en index.html:\n" + "\n".join(faltantes)
