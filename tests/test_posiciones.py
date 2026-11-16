"""Tests de atril/posiciones.py (posiciones de pistones en lugar de nombres)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from pathlib import Path

import pytest

from atril import posiciones as P

_DATOS = Path(__file__).parent / "datos"


# ---------------------------------------------------------------------------
# Alturas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre, octava, midi", [
    ("Do", 4, 60),
    ("Sol", 2, 43),
    ("Sib", 2, 46),
    ("La#", 2, 46),      # enarmónico de Sib2
    ("Fa#", 4, 66),
    ("Si#", 3, 60),      # la octava es la de la letra
    ("Dob", 4, 59),
    ("Mibb", 3, 50),
    ("Sol##", 3, 57),
])
def test_midi_de_nombre(nombre, octava, midi):
    assert P.midi_de_nombre(nombre, octava) == midi


@pytest.mark.parametrize("nombre, octava", [("?", 3), ("·", 3), ("Do", None), ("Dox", 3), ("", 3)])
def test_midi_de_nombre_invalido(nombre, octava):
    assert P.midi_de_nombre(nombre, octava) is None


def test_etiquetas():
    assert P.etiqueta_de_midi(60) == "Do4"
    assert P.etiqueta_de_midi(46) == "La#2 / Sib2"


# ---------------------------------------------------------------------------
# Tablas por defecto
# ---------------------------------------------------------------------------

def test_tabla_trombon_y_bombardino3_iguales():
    assert P.tabla_defecto("trombon") == P.tabla_defecto("bombardino3")
    t = P.tabla_defecto("trombon")
    assert min(t) == 43 and max(t) == 66          # Sol2 – Fa#4
    assert t[43] == "1/3" and t[49] == "1/2/3" and t[63] == "2"


def test_tabla_bombardino4():
    t = P.tabla_defecto("bombardino4")
    assert min(t) == 37 and max(t) == 72          # Reb2 – Do5
    assert t[37] == "1/2/3/4" and t[40] == "1/2/4" and t[43] == "4"
    assert t[49] == "2/4" and t[50] == "4" and t[52] == "1/2"
    assert t[62] == "1" and t[63] == "2"
    # De Mib3 hacia arriba es igual que el de 3 pistones (donde este tiene posición)
    t3 = P.tabla_defecto("bombardino3")
    assert all(t[m] == t3[m] for m in t3 if m >= 51)


def test_tabla_tuba_sin_quinto_piston():
    assert P.tabla_defecto("tuba") != P.tabla_defecto("bombardino4")
    t = P.tabla_defecto("tuba")
    assert min(t) == 24 and max(t) == 72          # Do1 – Do5
    assert 25 not in t and 26 not in t            # Do#1 y Re1 necesitan el 5.º
    assert all("5" not in v for v in t.values())
    assert t[27] == "1/3/4" and t[29] == "1/2/4" and t[30] == "2/4"


# ---------------------------------------------------------------------------
# Regla de la x y textos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valor, esperado", [
    ("1/2", "x"),
    (" 1 / 2 ", "x"),
    ("1/2/3", "1/2/3"),
    ("1/2/4", "1/2/4"),
    ("2", "2"),
])
def test_texto_final(valor, esperado):
    assert P.texto_final(valor, "x") == esperado


def test_tabla_efectiva_usa_simbolo_configurable():
    t = P.tabla_efectiva({"simbolo_12": "+"}, "trombon")
    assert t[45] == "+"          # La2 = 1/2
    assert t[49] == "1/2/3"      # Reb3 no cambia
    assert P.tabla_efectiva(None, "trombon")[45] == "x"


def test_texto_posicion():
    t = P.tabla_efectiva(None, "trombon")
    assert P.texto_posicion("Sib", 2, t) == "1"
    assert P.texto_posicion("La#", 2, t) == "1"
    assert P.texto_posicion("·", 2, t) == "·"     # ligadura
    assert P.texto_posicion("Do", 2, t) == ""      # fuera de la tabla: nada
    assert P.texto_posicion("?", 2, t) == ""


# ---------------------------------------------------------------------------
# Configuración del usuario
# ---------------------------------------------------------------------------

def test_tabla_guardada_sustituye_a_la_de_defecto():
    conf = {"tablas": {"tuba": {"60": "1/3", "61": ""}}}
    assert P.tablas_usuario(conf, "tuba") == {60: "1/3"}
    assert P.tablas_usuario(conf, "trombon") == P.tabla_defecto("trombon")


def test_normalizar_configuracion():
    datos = {
        "simbolo_12": " x ",
        "tablas": {
            "tuba": {"60": " 1/3 ", "61": "", "nope": "2"},
            "desconocido": {"60": "1"},
        },
    }
    assert P.normalizar_configuracion(datos) == {
        "simbolo_12": "x",
        "tablas": {"tuba": {"60": "1/3"}},
    }


def test_describir_configuracion():
    d = P.describir_configuracion(None)
    ids = [i["id"] for i in d["instrumentos"]]
    assert ids == ["tuba", "bombardino4", "bombardino3", "trombon"]
    trombon = d["instrumentos"][3]
    midis = [f["midi"] for f in trombon["filas"]]
    assert midis == sorted(midis, reverse=True)    # de agudo a grave
    fila_sol2 = next(f for f in trombon["filas"] if f["midi"] == 43)
    assert fila_sol2["valor"] == "1/3" and fila_sol2["defecto"] == "1/3"


# ---------------------------------------------------------------------------
# Sobre una partitura real
# ---------------------------------------------------------------------------

def test_aplicar_a_analisis(tmp_path):
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("Falta la partitura sintética")
    import music21
    import pymupdf
    from atril.superponer import analizar, colocar_nombres, escribir_pdf

    a = analizar(_DATOS / "sintetica.pdf",
                 music21.converter.parse(str(_DATOS / "sintetica.musicxml")))
    assert all(n.octava is not None for n in a.notas if n.texto != "?")

    tabla = P.tabla_efectiva(None, "tuba")
    P.aplicar_posiciones(a, tabla)
    for n in a.notas:
        assert n.impreso == P.texto_posicion(n.texto, n.octava, tabla)
    colocar_nombres(a)
    for n in a.notas:
        assert (n.x is not None) == bool(n.impreso)

    salida = tmp_path / "pistones.pdf"
    escribir_pdf(a, salida)
    texto = "".join(p.get_text() for p in pymupdf.open(str(salida)))
    assert "2/3" in texto
    assert "Mib" not in texto

    # Volver a nombres
    P.aplicar_posiciones(a, None)
    assert all(n.visible == n.texto for n in a.notas)


# ---------------------------------------------------------------------------
# API del servidor
# ---------------------------------------------------------------------------

@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    import interfaz.servidor as mod
    from http.server import ThreadingHTTPServer

    monkeypatch.setattr(mod, "_ruta_prefs_override", tmp_path / "prefs.json")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), mod._Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield puerto, tmp_path / "prefs.json"
    srv.shutdown()


def _llamar(puerto, ruta, datos=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}{ruta}",
        data=None if datos is None else json.dumps(datos).encode(),
        method="GET" if datos is None else "POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_posiciones(servidor):
    puerto, ruta_prefs = servidor

    cod, d = _llamar(puerto, "/api/posiciones")
    assert cod == 200 and d["instrumento"] == "" and d["simbolo_12"] == "x"

    cod, _ = _llamar(puerto, "/api/posiciones", {"instrumento": "tuba"})
    assert cod == 200
    cod, _ = _llamar(puerto, "/api/posiciones", {"instrumento": "violin"})
    assert cod == 400

    conf = {"simbolo_12": "X", "tablas": {"tuba": {"60": "1/2"}}}
    cod, _ = _llamar(puerto, "/api/posiciones", {"configuracion": conf})
    assert cod == 200
    cod, d = _llamar(puerto, "/api/posiciones")
    assert d["instrumento"] == "tuba" and d["simbolo_12"] == "X"
    tuba = next(i for i in d["instrumentos"] if i["id"] == "tuba")
    assert [f["valor"] for f in tuba["filas"] if f["valor"]] == ["1/2"]

    # Reiniciar tutoriales no borra la configuración
    _llamar(puerto, "/api/preferencias", {"reiniciar": True})
    prefs = json.loads(ruta_prefs.read_text(encoding="utf-8"))
    assert prefs["instrumento"] == "tuba" and "posiciones" in prefs

    # Restablecer las tablas por defecto
    _llamar(puerto, "/api/posiciones", {"configuracion": None})
    cod, d = _llamar(puerto, "/api/posiciones")
    assert d["simbolo_12"] == "x"


# ---------------------------------------------------------------------------
# Negrita / cursiva y modo Notas/Números
# ---------------------------------------------------------------------------

def test_fuente_de_estilo():
    from atril.superponer import fuente_de_estilo
    assert fuente_de_estilo() == "tiro"
    assert fuente_de_estilo(negrita=True) == "tibo"
    assert fuente_de_estilo(cursiva=True) == "tiit"
    assert fuente_de_estilo(True, True) == "tibi"


def test_pdf_en_negrita_y_cursiva(tmp_path):
    if not (_DATOS / "sintetica.pdf").exists():
        pytest.skip("Falta la partitura sintética")
    import music21
    import pymupdf
    from atril.superponer import analizar, colocar_nombres, escribir_pdf, fuente_de_estilo

    a = analizar(_DATOS / "sintetica.pdf",
                 music21.converter.parse(str(_DATOS / "sintetica.musicxml")))
    a.fuente = fuente_de_estilo(True, True)
    colocar_nombres(a)
    salida = tmp_path / "negrita.pdf"
    escribir_pdf(a, salida)
    fuentes = {f[3] for f in pymupdf.open(str(salida))[0].get_fonts()}
    assert "Times-BoldItalic" in fuentes


def test_api_modo_y_estilo(servidor):
    puerto, _ = servidor
    cod, d = _llamar(puerto, "/api/posiciones")
    assert d["modo"] == "notas" and d["estilo"] == {"negrita": False, "cursiva": False}

    _llamar(puerto, "/api/posiciones", {"modo": "numeros", "instrumento": "trombon",
                                        "estilo": {"negrita": True, "cursiva": False}})
    cod, d = _llamar(puerto, "/api/posiciones")
    assert d["modo"] == "numeros" and d["instrumento"] == "trombon"
    assert d["estilo"] == {"negrita": True, "cursiva": False}

    cod, _ = _llamar(puerto, "/api/posiciones", {"modo": "otro"})
    assert cod == 400


def test_estilo_de_cabecera():
    from interfaz.servidor import _estilo_de_cabecera
    assert _estilo_de_cabecera("negrita,cursiva") == (True, True)
    assert _estilo_de_cabecera("cursiva") == (False, True)
    assert _estilo_de_cabecera("") == (False, False)
    assert _estilo_de_cabecera(None) == (False, False)
