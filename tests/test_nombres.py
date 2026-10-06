"""
tests/test_nombres.py — Tests para el módulo nombres.py

Los MusicXML de prueba se construyen en memoria con constructor_score() y se
parsean con converter.parse(..., format="musicxml"). El <alter> ya refleja
armadura y accidentales, tal como exportaría Audiveris.
"""

from __future__ import annotations

import textwrap
from collections import defaultdict
from pathlib import Path

import pytest
from music21 import chord as chord_mod
from music21 import converter, key, note, pitch, stream

import atril.nombres as nombres
from atril.nombres import (
    MARCA_LIGADA,
    NOMBRES_SOLFEO,
    Resumen,
    anotar_musicxml,
    anotar_partitura,
    avisos_armadura,
    describir_armadura,
    describir_cambios,
    nombre_nota,
    notas_a_nombrar,
)


# ===========================================================================
# Helper: constructor de MusicXML mínimo
# ===========================================================================

def _nota_xml(step: str, octave: int, alter: float = 0, duration: int = 1,
              type_: str = "quarter", accidental: str = "",
              tie_start: bool = False, tie_stop: bool = False,
              grace: bool = False) -> str:
    alter_xml = f"<alter>{alter}</alter>" if alter != 0 else ""
    acc_xml = f"<accidental>{accidental}</accidental>" if accidental else ""
    ties = ""
    notaciones = ""
    if tie_start:
        ties += '<tie type="start"/>'
        notaciones += '<tied type="start"/>'
    if tie_stop:
        ties += '<tie type="stop"/>'
        notaciones += '<tied type="stop"/>'
    not_xml = f"<notations>{notaciones}</notations>" if notaciones else ""
    grace_xml = "<grace/>" if grace else ""
    dur_xml = "" if grace else f"<duration>{duration}</duration>"
    return (
        f"<note>"
        f"{grace_xml}"
        f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"
        f"{dur_xml}"
        f"<type>{type_}</type>"
        f"{acc_xml}"
        f"{ties}"
        f"{not_xml}"
        f"</note>"
    )


def _silencio_xml(duration: int = 1, type_: str = "quarter") -> str:
    return f"<note><rest/><duration>{duration}</duration><type>{type_}</type></note>"


def _acorde_xml(notas: list[tuple], duration: int = 1, type_: str = "quarter") -> str:
    """notas: lista de (step, octave[, alter[, accidental[, tie_start[, tie_stop]]]]])."""
    resultado = ""
    for i, n in enumerate(notas):
        step, octave = n[0], n[1]
        alter = n[2] if len(n) > 2 else 0
        accidental = n[3] if len(n) > 3 else ""
        tie_start = n[4] if len(n) > 4 else False
        tie_stop = n[5] if len(n) > 5 else False
        chord_tag = "<chord/>" if i > 0 else ""
        alter_xml = f"<alter>{alter}</alter>" if alter != 0 else ""
        acc_xml = f"<accidental>{accidental}</accidental>" if accidental else ""
        ties = ""
        notaciones = ""
        if tie_start:
            ties += '<tie type="start"/>'
            notaciones += '<tied type="start"/>'
        if tie_stop:
            ties += '<tie type="stop"/>'
            notaciones += '<tied type="stop"/>'
        not_xml = f"<notations>{notaciones}</notations>" if notaciones else ""
        resultado += (
            f"<note>{chord_tag}"
            f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"
            f"<duration>{duration}</duration><type>{type_}</type>"
            f"{acc_xml}{ties}{not_xml}</note>"
        )
    return resultado


def construir_score(fifths: int = 0, clef_sign: str = "G", clef_line: int = 2,
                    compases: list[str] | None = None) -> stream.Score:
    """Construye un Score mínimo a partir de bloques de notas XML por compás."""
    if compases is None:
        compases = [""]
    partes = []
    for i, contenido in enumerate(compases):
        atributos = ""
        if i == 0:
            atributos = (
                f"<attributes>"
                f"<divisions>1</divisions>"
                f"<key><fifths>{fifths}</fifths></key>"
                f"<time><beats>4</beats><beat-type>4</beat-type></time>"
                f"<clef><sign>{clef_sign}</sign><line>{clef_line}</line></clef>"
                f"</attributes>"
            )
        partes.append(f'<measure number="{i + 1}">{atributos}{contenido}</measure>')

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"'
        ' "http://www.musicxml.org/dtds/partwise.dtd">'
        '<score-partwise version="3.1">'
        '<part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>'
        '<part id="P1">' + "".join(partes) + "</part>"
        "</score-partwise>"
    )
    return converter.parse(xml, format="musicxml")


def _letras_del_score(score) -> list[str]:
    """Recoge todos los textos de lyric del score en orden."""
    letras = []
    for elem in score.recurse().notes:
        for lyr in elem.lyrics:
            letras.append(lyr.text)
    return letras


# ===========================================================================
# Test 1: nombre_nota para todos los casos
# ===========================================================================

class TestNombreNota:
    def _p(self, step: str, alter: float = 0) -> pitch.Pitch:
        p = pitch.Pitch(step)
        if alter != 0:
            from music21 import pitch as m21pitch
            p.accidental = m21pitch.Accidental(alter)
        return p

    def test_naturales(self):
        esperados = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
                     "G": "Sol", "A": "La", "B": "Si"}
        for step, esperado in esperados.items():
            assert nombre_nota(self._p(step)) == esperado

    def test_bemol(self):
        assert nombre_nota(self._p("B", -1)) == "Sib"
        assert nombre_nota(self._p("E", -1)) == "Mib"

    def test_sostenido(self):
        assert nombre_nota(self._p("F", 1)) == "Fa#"
        assert nombre_nota(self._p("C", 1)) == "Do#"

    def test_becuadro(self):
        from music21 import pitch as m21pitch
        p = pitch.Pitch("B")
        p.accidental = m21pitch.Accidental("natural")
        assert nombre_nota(p) == "Si"

    def test_doble_bemol(self):
        assert nombre_nota(self._p("B", -2)) == "Sibb"

    def test_doble_sostenido(self):
        assert nombre_nota(self._p("F", 2)) == "Fa##"


# ===========================================================================
# Test 2: Tuba en 4 bemoles, pasaje completo
# ===========================================================================

def test_tuba_cuatro_bemoles():
    # Fa, Mib, Lab, Reb, Sib, Do (en orden)
    notas_xml = (
        _nota_xml("F", 4)
        + _nota_xml("E", 4, -1)
        + _nota_xml("A", 4, -1)
        + _nota_xml("D", 5, -1)
        + _nota_xml("B", 3, -1)
        + _nota_xml("C", 4)
    )
    score = construir_score(fifths=-4, clef_sign="F", clef_line=4, compases=[notas_xml])
    anotar_partitura(score)
    assert _letras_del_score(score) == ["Fa", "Mib", "Lab", "Reb", "Sib", "Do"]


def test_tuba_armadura_correcta():
    score = construir_score(fifths=-4, clef_sign="F", clef_line=4,
                            compases=[_nota_xml("C", 4)])
    resumen = anotar_partitura(score)
    assert resumen.armadura == "4 bemoles (Sib, Mib, Lab, Reb)"


# ===========================================================================
# Test 3: Becuadro
# ===========================================================================

def test_becuadro():
    # Si con accidental natural -> "Si"
    # Si posterior sin alter en mismo compás -> "Si"
    # Si en compás siguiente con alter -1 -> "Sib"
    compas1 = (
        _nota_xml("B", 4, 0, accidental="natural")
        + _nota_xml("B", 4)
    )
    compas2 = _nota_xml("B", 4, -1)
    score = construir_score(fifths=-2, compases=[compas1, compas2])
    anotar_partitura(score)
    letras = _letras_del_score(score)
    assert letras[0] == "Si"
    assert letras[1] == "Si"
    assert letras[2] == "Sib"


# ===========================================================================
# Test 4: Alteración que dura hasta la barra
# ===========================================================================

def test_alteracion_dura_hasta_barra():
    # Fa# impreso, otro Fa con alter 1 sin impreso -> "Fa#" ambas
    # Compás siguiente Fa sin alter -> "Fa"
    compas1 = (
        _nota_xml("F", 4, 1, accidental="sharp")
        + _nota_xml("F", 4, 1)
    )
    compas2 = _nota_xml("F", 4)
    score = construir_score(fifths=0, compases=[compas1, compas2])
    anotar_partitura(score)
    letras = _letras_del_score(score)
    assert letras[0] == "Fa#"
    assert letras[1] == "Fa#"
    assert letras[2] == "Fa"


# ===========================================================================
# Test 5: Claves de sol y do en 3ª no alteran los nombres
# ===========================================================================

def test_claves_no_afectan_nombres():
    nota = _nota_xml("E", 4, -1)
    score_sol = construir_score(fifths=-3, clef_sign="G", clef_line=2, compases=[nota])
    anotar_partitura(score_sol)
    score_do3 = construir_score(fifths=-3, clef_sign="C", clef_line=3, compases=[nota])
    anotar_partitura(score_do3)
    assert _letras_del_score(score_sol) == ["Mib"]
    assert _letras_del_score(score_do3) == ["Mib"]


# ===========================================================================
# Test 6: Ligaduras — ahora reciben MARCA_LIGADA
# ===========================================================================

def test_ligadura_dentro_del_compas():
    # Misma nota justo detrás y en el mismo compás: primera -> nombre, segunda -> MARCA_LIGADA
    compas = _nota_xml("C", 4, tie_start=True) + _nota_xml("C", 4, tie_stop=True)
    score = construir_score(compases=[compas])
    resumen = anotar_partitura(score)
    letras = _letras_del_score(score)
    assert letras == ["Do", MARCA_LIGADA]
    assert resumen.ligadas_marcadas == 1


def test_ligaduras_a_traves_de_barra_llevan_nombre():
    # Regla del usuario: si hay una barra de compás en medio, se escribe el nombre
    compas1 = _nota_xml("C", 4, tie_start=True)
    compas2 = _nota_xml("C", 4, tie_stop=True)
    score = construir_score(compases=[compas1, compas2])
    resumen = anotar_partitura(score)
    assert _letras_del_score(score) == ["Do", "Do"]
    assert resumen.ligadas_marcadas == 0


def test_ligadura_con_silencio_en_medio_lleva_nombre():
    # Una ligadura no puede saltar un silencio: el OMR confundió una ligadura de expresión
    compas = (_nota_xml("D", 4, tie_start=True) + _silencio_xml()
              + _nota_xml("D", 4, tie_stop=True))
    score = construir_score(compases=[compas])
    resumen = anotar_partitura(score)
    assert _letras_del_score(score) == ["Re", "Re"]
    assert resumen.ligadas_marcadas == 0


def test_cadena_ligaduras():
    # start / (start+stop = continue) / stop en el mismo compás -> nombre, ·, ·
    compas = (_nota_xml("G", 4, tie_start=True)
              + _nota_xml("G", 4, tie_stop=True, tie_start=True)  # continue
              + _nota_xml("G", 4, tie_stop=True))
    score = construir_score(compases=[compas])
    resumen = anotar_partitura(score)
    letras = _letras_del_score(score)
    assert letras[0] == "Sol"
    assert letras[1] == MARCA_LIGADA
    assert letras[2] == MARCA_LIGADA
    assert resumen.ligadas_marcadas == 2


def test_ligadura_marca_none():
    # Con marca_ligada=None las notas ligadas no reciben nada
    compas = _nota_xml("C", 4, tie_start=True) + _nota_xml("C", 4, tie_stop=True)
    score = construir_score(compases=[compas])
    resumen = anotar_partitura(score, marca_ligada=None)
    letras = _letras_del_score(score)
    assert letras == ["Do"]
    assert resumen.ligadas_marcadas == 0


def test_ligadura_expresion_distinta_altura():
    # Tie entre notas de distinta altura (slur mal leído) -> ambas nombradas
    compas1 = _nota_xml("C", 4, tie_start=True)
    compas2 = _nota_xml("E", 4, tie_stop=True)  # altura distinta
    score = construir_score(compases=[compas1, compas2])
    resumen = anotar_partitura(score)
    letras = _letras_del_score(score)
    assert letras[0] == "Do"
    assert letras[1] == "Mi"   # nombrada normalmente
    assert resumen.ligadas_marcadas == 0


# ===========================================================================
# Test 7: Acordes
# ===========================================================================

def test_acorde_simple():
    # Do3 + Mib3 -> Mib (línea n), Do (línea n+1)
    notas_acorde = _acorde_xml([
        ("E", 3, -1),  # Mib3 (más aguda)
        ("C", 3),      # Do3 (más grave)
    ])
    score = construir_score(compases=[notas_acorde])
    resumen = anotar_partitura(score)

    por_numero: dict[int, list[str]] = defaultdict(list)
    for elem in score.recurse().notes:
        for lyr in elem.lyrics:
            por_numero[lyr.number].append(lyr.text)

    nums = sorted(por_numero.keys())
    assert len(nums) == 2
    assert por_numero[nums[0]] == ["Mib"]   # más aguda, número menor
    assert por_numero[nums[1]] == ["Do"]    # más grave, número mayor
    assert resumen.acordes == 1


def test_acorde_con_nota_ligada():
    # Acorde: Sol (libre) + Mib (tie stop) -> Sol recibe nombre, Mib recibe MARCA_LIGADA
    # Necesitamos un acorde previo para que la ligadura sea "real" (misma altura)
    # (en el mismo compás: con una barra en medio se escribiría el nombre)
    acorde_previo = _acorde_xml([("G", 4), ("E", 4, -1, "", True, False)])
    acorde_actual = _acorde_xml([("G", 4), ("E", 4, -1, "", False, True)])
    score = construir_score(compases=[acorde_previo + acorde_actual])
    anotar_partitura(score)

    letras_compas2: list[str] = []
    elementos = list(score.recurse().notes)
    # El segundo elemento del recurse es el acorde del compás 2
    for elem in elementos[1:]:  # saltar el primer acorde
        for lyr in elem.lyrics:
            letras_compas2.append(lyr.text)

    # El acorde del compás 2: Sol (libre) debería tener nombre, Mib (tied) → ·
    # Pero las ligaduras de los dos acordes: Sol no está ligado, Mib sí (stop)
    # Sol → nombre; Mib (stop, misma altura) → ·
    assert "Sol" in letras_compas2
    assert MARCA_LIGADA in letras_compas2


def test_acorde_con_nota_ligada_no_prior():
    # Acorde con Mib tie-stop pero sin acorde previo -> distinta altura (slur)
    # -> ambas notas nombradas normalmente
    notas_acorde = _acorde_xml([
        ("G", 4),
        ("E", 4, -1, "", False, True),  # Mib ligada stop sin previo
    ])
    score = construir_score(compases=[notas_acorde])
    anotar_partitura(score)

    letras = []
    for elem in score.recurse().notes:
        for lyr in elem.lyrics:
            letras.append(lyr.text)

    assert "Sol" in letras
    assert "Mib" in letras
    assert MARCA_LIGADA not in letras


# ===========================================================================
# Test 8: Silencios y adornos no reciben letra
# ===========================================================================

def test_silencios_sin_letra():
    contenido = _silencio_xml() + _nota_xml("C", 4)
    score = construir_score(compases=[contenido])
    anotar_partitura(score)
    assert _letras_del_score(score) == ["Do"]


def test_adornos_sin_letra():
    contenido = _nota_xml("D", 5, grace=True) + _nota_xml("C", 4)
    score = construir_score(compases=[contenido])
    anotar_partitura(score)
    assert _letras_del_score(score) == ["Do"]


# ===========================================================================
# Test 9: Lyric existente en línea 1 -> nombres van en línea 2
# ===========================================================================

def test_nombres_van_despues_de_lyric_existente():
    from music21 import note as m21note
    from music21 import stream as m21stream

    score = m21stream.Score()
    parte = m21stream.Part()
    compas = m21stream.Measure(number=1)
    n = m21note.Note("C4", quarterLength=1)
    n.addLyric("hola", lyricNumber=1)
    compas.append(n)
    parte.append(compas)
    score.append(parte)

    anotar_partitura(score)
    lyric_numeros = [lyr.number for lyr in n.lyrics]
    assert 1 in lyric_numeros
    assert 2 in lyric_numeros
    texts = [lyr.text for lyr in n.lyrics]
    assert "Do" in texts


# ===========================================================================
# Test 10: describir_armadura
# ===========================================================================

def test_describir_armadura():
    assert describir_armadura(None) == "sin alteraciones"
    assert describir_armadura(key.KeySignature(0)) == "sin alteraciones"
    assert describir_armadura(key.KeySignature(-1)) == "1 bemol (Sib)"
    assert describir_armadura(key.KeySignature(-4)) == "4 bemoles (Sib, Mib, Lab, Reb)"
    assert describir_armadura(key.KeySignature(2)) == "2 sostenidos (Fa#, Do#)"


# ===========================================================================
# Test 11: avisos_armadura y partitura sin <key>
# ===========================================================================

def test_sin_avisos_partitura_normal_cuatro_bemoles():
    contenido = (
        _nota_xml("B", 3, -1)
        + _nota_xml("E", 4, -1)
        + _nota_xml("A", 4, -1)
        + _nota_xml("D", 5, -1)
    )
    score = construir_score(fifths=-4, compases=[contenido])
    avisos = avisos_armadura(score)
    assert avisos == []


def test_sin_armadura_no_es_aviso():
    # Audiveris no exporta <key> para Do mayor -> no debe haber aviso
    from music21 import note as m21note
    from music21 import stream as m21stream

    score = m21stream.Score()
    parte = m21stream.Part()
    compas = m21stream.Measure(number=1)
    compas.append(m21note.Note("C4", quarterLength=1))
    parte.append(compas)
    score.append(parte)

    avisos = avisos_armadura(score)
    assert avisos == []


def test_sin_armadura_describe_sin_alteraciones():
    # Sin KeySignature -> describir_armadura(None) = "sin alteraciones"
    assert describir_armadura(None) == "sin alteraciones"


def test_aviso_cambio_armadura_revertido():
    # C1: -4 bemoles; C2: -2 bemoles; C3: -4 bemoles (revertido en 1 compás)
    compas2_xml = (
        '<measure number="2">'
        '<attributes><key><fifths>-2</fifths></key></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><type>quarter</type></note>'
        '</measure>'
    )
    compas3_xml = (
        '<measure number="3">'
        '<attributes><key><fifths>-4</fifths></key></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><type>quarter</type></note>'
        '</measure>'
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"'
        ' "http://www.musicxml.org/dtds/partwise.dtd">'
        '<score-partwise version="3.1">'
        '<part-list><score-part id="P1"><part-name>T</part-name></score-part></part-list>'
        '<part id="P1">'
        '<measure number="1">'
        '<attributes><divisions>1</divisions><key><fifths>-4</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>F</sign><line>4</line></clef></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><type>quarter</type></note>'
        '</measure>'
        + compas2_xml + compas3_xml
        + '</part></score-partwise>'
    )
    score = converter.parse(xml, format="musicxml")
    avisos = avisos_armadura(score)
    # Debe haber un aviso sobre el compás 2
    assert any(
        "dudosa" in a.lower() or "2" in a
        for a in avisos
    ), f"Sin aviso de armadura dudosa, avisos={avisos}"


def test_aviso_redundantes():
    # 6 Reb impresas con armadura de 4 bemoles -> aviso
    notas = "".join(_nota_xml("D", 5, -1, accidental="flat") for _ in range(6))
    score = construir_score(fifths=-4, compases=[notas])
    avisos = avisos_armadura(score)
    assert any("redundant" in a.lower() or "armadura" in a.lower() for a in avisos)


def test_cortesia_no_cuenta_como_redundante():
    # Reb impreso (1 redundante) + Re natural (cortesía) + Reb impreso (cortesía)
    # Solo 1 redundante, muy por debajo del umbral
    compas1 = _nota_xml("D", 5, -1, accidental="flat")
    compas2 = (
        _nota_xml("D", 5, 0, accidental="natural")
        + _nota_xml("D", 5, -1, accidental="flat")
    )
    score = construir_score(fifths=-4, compases=[compas1, compas2])
    avisos = avisos_armadura(score)
    assert not any("redundant" in a.lower() for a in avisos)


# ===========================================================================
# Test 12: describir_cambios
# ===========================================================================

def test_describir_cambios_inicio():
    score = construir_score(fifths=-4, clef_sign="F", clef_line=4,
                            compases=[_nota_xml("C", 4)])
    cambios = describir_cambios(score)
    assert len(cambios) >= 1
    assert "fa en 4ª" in cambios[0].lower() or "fa" in cambios[0].lower()
    assert "4 bemoles" in cambios[0]


def test_describir_cambios_cambio_armadura():
    compas2_xml = (
        '<measure number="2">'
        '<attributes><key><fifths>2</fifths></key></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><type>quarter</type></note>'
        '</measure>'
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"'
        ' "http://www.musicxml.org/dtds/partwise.dtd">'
        '<score-partwise version="3.1">'
        '<part-list><score-part id="P1"><part-name>T</part-name></score-part></part-list>'
        '<part id="P1">'
        '<measure number="1">'
        '<attributes><divisions>1</divisions><key><fifths>0</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><type>quarter</type></note>'
        '</measure>'
        + compas2_xml
        + '</part></score-partwise>'
    )
    score = converter.parse(xml, format="musicxml")
    cambios = describir_cambios(score)
    # Debe haber un cambio de armadura en el compás 2
    assert any("2 sostenidos" in c for c in cambios)
    assert any("Compás 2" in c for c in cambios)


def test_describir_cambios_sin_key():
    # Sin <key> en el XML -> Compás 1 con "sin alteraciones"
    from music21 import note as m21note
    from music21 import stream as m21stream

    score = m21stream.Score()
    parte = m21stream.Part()
    from music21 import clef as m21clef
    compas = m21stream.Measure(number=1)
    compas.insert(0, m21clef.TrebleClef())
    compas.append(m21note.Note("C4", quarterLength=1))
    parte.append(compas)
    score.append(parte)

    cambios = describir_cambios(score)
    assert len(cambios) >= 1
    assert "sin alteraciones" in cambios[0]


def test_cambios_en_resumen():
    score = construir_score(fifths=0, clef_sign="G", clef_line=2,
                            compases=[_nota_xml("C", 4)])
    resumen = anotar_partitura(score)
    assert isinstance(resumen.cambios, list)
    assert len(resumen.cambios) >= 1


# ===========================================================================
# Test 13: Ida y vuelta anotar_musicxml
# ===========================================================================

def test_ida_y_vuelta(tmp_path: Path):
    entrada = tmp_path / "entrada.xml"
    salida = tmp_path / "salida.xml"

    contenido = (
        _nota_xml("C", 4)
        + _nota_xml("E", 4, -1)
        + _nota_xml("G", 4)
    )
    score_orig = construir_score(fifths=-3, compases=[contenido])
    score_orig.write("musicxml", fp=str(entrada))

    resumen = anotar_musicxml(entrada, salida)

    assert salida.exists()
    assert resumen.notas_nombradas == 3

    score_leido = converter.parse(str(salida))
    letras = _letras_del_score(score_leido)
    assert letras == ["Do", "Mib", "Sol"]


def test_anotar_musicxml_archivo_no_existe(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        anotar_musicxml(tmp_path / "no_existe.xml", tmp_path / "salida.xml")
