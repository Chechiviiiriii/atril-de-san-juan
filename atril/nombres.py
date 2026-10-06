"""
nombres.py — Módulo para añadir nombres de notas en solfeo español a partituras MusicXML.

Nomenclatura: Do Re Mi Fa Sol La Si; bemol = "b", sostenido = "#".
Ejemplos: Mib, Fa#, Sibb, Fa##; becuadro explícito -> sin sufijo ("Si").

Flujo: PDF de partitura -> Audiveris -> MusicXML -> este módulo -> MuseScore -> PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from music21 import clef, converter, key, note, pitch, stream


# ---------------------------------------------------------------------------
# Dataclass NotaTexto
# ---------------------------------------------------------------------------

@dataclass
class NotaTexto:
    """Nota individual con su texto a mostrar (nombre en solfeo o marca de ligadura)."""
    elemento: object   # music21 Note o Chord (el contenedor del stream)
    nota: note.Note    # la Note individual (== elemento si no es acorde)
    pitch: pitch.Pitch
    texto: str         # nombre en solfeo o MARCA_LIGADA
    compas: int        # número de compás (0 si no disponible)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

NOMBRES_SOLFEO: dict[str, str] = {
    "C": "Do",
    "D": "Re",
    "E": "Mi",
    "F": "Fa",
    "G": "Sol",
    "A": "La",
    "B": "Si",
}

# Sufijos de alteración (alter redondeado)
_SUFIJOS: dict[int, str] = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}

# Texto para notas ligadas (stop/continue) con la misma altura que la anterior
MARCA_LIGADA = "·"  # punto medio ·

# Umbrales para el aviso de alteraciones impresas redundantes
UMBRAL_REDUNDANTES_ABS = 4    # número mínimo absoluto
UMBRAL_REDUNDANTES_PCT = 0.30  # porcentaje mínimo sobre impresas totales


# ---------------------------------------------------------------------------
# Funciones de nombre
# ---------------------------------------------------------------------------

def nombre_nota(p: pitch.Pitch) -> str:
    """Devuelve el nombre en solfeo español de un Pitch de music21.

    El alter ya refleja armadura y accidentales; no recalculamos nada.
    Becuadro explícito (accidental='natural', alter=0) -> sin sufijo.
    """
    base = NOMBRES_SOLFEO[p.step]
    alter = int(round(p.alter)) if p.accidental is not None else 0
    return base + _SUFIJOS.get(alter, "")


def _tie_type(n: note.Note) -> Optional[str]:
    """Devuelve 'start', 'stop', 'continue' o None según la ligadura de la nota."""
    if n.tie is not None:
        return n.tie.type
    return None


def _misma_altura(p1: pitch.Pitch, p2: pitch.Pitch) -> bool:
    """True si dos pitches tienen el mismo step, alter y octava."""
    return (
        p1.step == p2.step
        and int(round(p1.alter)) == int(round(p2.alter))
        and p1.octave == p2.octave
    )


def _altura_previa_existe(elemento, p: pitch.Pitch) -> bool:
    """True si la nota ligada debe llevar el punto en vez del nombre: la figura
    inmediatamente anterior es una nota con la misma altura que p, sin nada
    en medio y dentro del mismo compás.

    Regla del usuario: si hay algo entre las dos notas (un silencio o una barra
    de compás), se escribe el nombre. Además, una ligadura de unión no puede
    saltar un silencio ni salir de una nota en staccato; si el OMR la ve así,
    en realidad era una ligadura de expresión.
    """
    from music21 import articulations, chord as chord_mod

    prev = elemento.previous("GeneralNote")
    if prev is None or isinstance(prev, note.Rest):
        return False
    if prev.getContextByClass("Measure") is not elemento.getContextByClass("Measure"):
        return False
    if any(isinstance(a, articulations.Staccato) for a in prev.articulations):
        return False
    if isinstance(prev, chord_mod.Chord):
        return any(_misma_altura(n.pitch, p) for n in prev.notes)
    if isinstance(prev, note.Note):
        return _misma_altura(prev.pitch, p)
    return False


def notas_a_nombrar(elemento) -> list[note.Note]:
    """Devuelve las notas del elemento que deben recibir texto (nombre o marca de ligadura).

    - Note: [n] salvo que sea adorno (isGrace).
    - Chord: notas ordenadas de la más aguda a la más grave.
    - Rest y cualquier otro elemento: [].
    Las notas ligadas (stop/continue) se incluyen; anotar_partitura decide el texto.
    """
    if isinstance(elemento, note.Rest):
        return []

    if isinstance(elemento, note.Note):
        if elemento.duration.isGrace:
            return []
        return [elemento]

    from music21 import chord as chord_mod
    if isinstance(elemento, chord_mod.Chord):
        return sorted(elemento.notes, key=lambda x: x.pitch.ps, reverse=True)

    return []


# ---------------------------------------------------------------------------
# Descripción de armadura
# ---------------------------------------------------------------------------

def describir_armadura(ks: Optional[key.KeySignature]) -> str:
    """Devuelve una descripción legible de la armadura en solfeo español.

    None (sin KeySignature o armadura de Do mayor sin exportar) -> 'sin alteraciones'.
    """
    if ks is None or ks.sharps == 0:
        return "sin alteraciones"

    pitches = ks.alteredPitches
    nombres = [nombre_nota(p) for p in pitches]
    lista = ", ".join(nombres)

    n = abs(ks.sharps)
    if ks.sharps > 0:
        palabra = "sostenido" if n == 1 else "sostenidos"
        return f"{n} {palabra} ({lista})"
    else:
        palabra = "bemol" if n == 1 else "bemoles"
        return f"{n} {palabra} ({lista})"


# ---------------------------------------------------------------------------
# Nombre de clave
# ---------------------------------------------------------------------------

def _nombre_clave(c) -> str:
    """Devuelve el nombre legible en español de un objeto clef.Clef."""
    from music21 import clef as m21clef

    if isinstance(c, m21clef.PercussionClef):
        return "percusión"

    sign = getattr(c, "sign", None) or ""
    line = getattr(c, "line", None)
    octave_change = getattr(c, "octaveChange", 0) or 0

    lineas = {1: "1ª", 2: "2ª", 3: "3ª", 4: "4ª", 5: "5ª"}
    linea_str = lineas.get(line, f"{line}ª") if line is not None else ""

    if sign == "G":
        if octave_change == -1:
            return "sol 8ª baja"
        return f"sol en {linea_str}" if linea_str else "sol"
    if sign == "F":
        return f"fa en {linea_str}" if linea_str else "fa"
    if sign == "C":
        return f"do en {linea_str}" if linea_str else "do"

    return sign.lower()


def _clef_igual(c1, c2) -> bool:
    return (
        getattr(c1, "sign", None) == getattr(c2, "sign", None)
        and getattr(c1, "line", None) == getattr(c2, "line", None)
        and (getattr(c1, "octaveChange", 0) or 0) == (getattr(c2, "octaveChange", 0) or 0)
    )


# ---------------------------------------------------------------------------
# describir_cambios
# ---------------------------------------------------------------------------

def describir_cambios(score) -> list[str]:
    """Lista legible de clave y armadura al inicio y de cada cambio posterior.

    Por parte. Ignora repeticiones idénticas al inicio de cada sistema.
    Ejemplos: "Compás 1: clave de fa en 4ª, sin alteraciones",
              "Compás 25: armadura → 2 sostenidos (Fa#, Do#)",
              "Compás 31: clave → sol en 2ª".
    """
    partes = list(score.parts) if hasattr(score, "parts") and score.parts else [score]
    n_partes = len(partes)
    resultado: list[str] = []

    for idx_parte, parte in enumerate(partes):
        prefijo = f"[Parte {idx_parte + 1}] " if n_partes > 1 else ""
        compases = list(parte.getElementsByClass(stream.Measure))
        if not compases:
            compases = [parte]

        clef_actual = None
        ks_actual: Optional[key.KeySignature] = None
        primer_compas = True

        for compas in compases:
            num = getattr(compas, "number", 1) or 1
            nuevas_claves = list(compas.getElementsByClass(clef.Clef))
            nuevas_ks = list(compas.getElementsByClass(key.KeySignature))

            if primer_compas:
                clef_actual = nuevas_claves[0] if nuevas_claves else None
                ks_actual = nuevas_ks[0] if nuevas_ks else None
                clave_str = _nombre_clave(clef_actual) if clef_actual else "?"
                ks_str = describir_armadura(ks_actual)
                resultado.append(f"{prefijo}Compás {num}: clave de {clave_str}, {ks_str}")
                primer_compas = False
            else:
                for nueva_clave in nuevas_claves:
                    if clef_actual is None or not _clef_igual(nueva_clave, clef_actual):
                        resultado.append(f"{prefijo}Compás {num}: clave → {_nombre_clave(nueva_clave)}")
                        clef_actual = nueva_clave

                for nueva_ks in nuevas_ks:
                    # Sin armadura previa equivale a 0 alteraciones (Audiveris no exporta <key> en Do)
                    alteraciones_actuales = ks_actual.sharps if ks_actual is not None else 0
                    if nueva_ks.sharps != alteraciones_actuales:
                        resultado.append(f"{prefijo}Compás {num}: armadura → {describir_armadura(nueva_ks)}")
                        ks_actual = nueva_ks

    return resultado


# ---------------------------------------------------------------------------
# Avisos de armadura
# ---------------------------------------------------------------------------

def avisos_armadura(score) -> list[str]:
    """Genera avisos sobre posibles problemas con la armadura.

    Aviso 1 (sin armadura): eliminado; la ausencia de <key> en Audiveris
    indica Do mayor y es normal.
    Aviso 2: cambio de armadura que se revierte al original en <= 2 compases.
    Aviso 3: exceso de alteraciones impresas redundantes con la armadura vigente.
    """
    avisos: list[str] = []
    partes = list(score.parts) if hasattr(score, "parts") and score.parts else [score]

    for parte in partes:
        compases = list(parte.getElementsByClass(stream.Measure))
        if not compases:
            compases = [parte]

        # Recoger todos los cambios de KS con su compás de inicio
        ks_events: list[tuple[int, key.KeySignature]] = []
        ks_vigente: Optional[key.KeySignature] = None

        # Primera pasada: recoger KS events y detectar reverts
        for compas in compases:
            num_compas = getattr(compas, "number", 1) or 1
            for ks in compas.getElementsByClass(key.KeySignature):
                ks_events.append((num_compas, ks))
                ks_vigente = ks  # se actualiza

        # Aviso 2: cambio que se revierte en <= 2 compases
        for i in range(2, len(ks_events)):
            num_i, ks_i = ks_events[i]
            num_prev, ks_prev = ks_events[i - 1]   # el cambio sospechoso
            num_earlier, ks_earlier = ks_events[i - 2]  # la anterior
            if ks_i.sharps == ks_earlier.sharps:
                distancia = num_i - num_prev
                if 0 < distancia <= 2:
                    avisos.append(
                        f"Armadura dudosa en el compás {num_prev} "
                        f"(el cambio se revierte en {distancia} compás/compases)."
                    )

        # Aviso 3: alteraciones impresas redundantes
        total_impresas = 0
        redundantes = 0
        ks_vigente = None

        # Rastrear alteraciones por (step, octave) para detectar cortesías
        alts_compas_actual: dict[tuple[str, int], int] = {}
        alts_compas_anterior: dict[tuple[str, int], int] = {}

        for compas in compases:
            alts_compas_actual = {}

            for ks in compas.getElementsByClass(key.KeySignature):
                ks_vigente = ks

            from music21 import chord as chord_mod
            for elem in compas.recurse().notes:
                notas_elem: list[note.Note] = []
                if isinstance(elem, note.Note):
                    notas_elem = [elem]
                elif isinstance(elem, chord_mod.Chord):
                    notas_elem = list(elem.notes)

                for n in notas_elem:
                    if not hasattr(n, "pitch"):
                        continue
                    p = n.pitch
                    acc = p.accidental
                    if acc is None or not acc.displayStatus:
                        continue

                    total_impresas += 1
                    alter_nota = int(round(p.alter))
                    clave_nota = (p.step, p.octave)

                    # Alteración que marca la armadura vigente para este step
                    alter_armadura = 0
                    if ks_vigente is not None:
                        acc_arm = ks_vigente.accidentalByStep(p.step)
                        if acc_arm is not None:
                            alter_armadura = int(round(acc_arm.alter))

                    # ¿Es cortesía? Cancela una alteración distinta vista antes
                    es_cortesia = False
                    for alts in (alts_compas_actual, alts_compas_anterior):
                        alter_previo = alts.get(clave_nota)
                        if alter_previo is not None and alter_previo != alter_nota:
                            es_cortesia = True
                            break

                    if not es_cortesia and alter_nota == alter_armadura:
                        redundantes += 1

                    alts_compas_actual[clave_nota] = alter_nota

            alts_compas_anterior = dict(alts_compas_actual)

        if (
            redundantes >= UMBRAL_REDUNDANTES_ABS
            and total_impresas > 0
            and redundantes / total_impresas >= UMBRAL_REDUNDANTES_PCT
        ):
            avisos.append(
                f"Posible armadura mal leída: {redundantes} de {total_impresas} alteraciones impresas "
                f"son redundantes con la armadura ({redundantes * 100 // total_impresas} %). "
                "Revisa la partitura con --revisar."
            )

    return [a for a in avisos if a]


# ---------------------------------------------------------------------------
# Número de compás
# ---------------------------------------------------------------------------

def _numero_compas(elemento) -> int:
    """Devuelve el número de compás del elemento, o 0 si no está disponible."""
    try:
        m = elemento.getContextByClass("Measure")
        if m is not None:
            return int(getattr(m, "number", 0) or 0)
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# textos_por_nota
# ---------------------------------------------------------------------------

def texto_de_nota(
    elemento,
    n: note.Note,
    marca_ligada: Optional[str] = MARCA_LIGADA,
) -> Optional[str]:
    """Texto que se escribe bajo la nota ``n`` (que pertenece a ``elemento``,
    una nota o un acorde): su nombre, o ``marca_ligada`` si es la continuación
    de una ligadura justo detrás y en el mismo compás. ``None`` si no se escribe nada.

    Única fuente de la regla de ligaduras: la usan tanto las letras como la
    superposición sobre el PDF.
    """
    if _tie_type(n) in ("stop", "continue") and _altura_previa_existe(elemento, n.pitch):
        return marca_ligada
    return nombre_nota(n.pitch)


def textos_por_nota(
    score: stream.Score,
    marca_ligada: Optional[str] = MARCA_LIGADA,
) -> list[NotaTexto]:
    """Devuelve la lista de notas con su texto a mostrar.

    Aplica las mismas reglas que :func:`anotar_partitura`:
    - Notas ligadas (stop/continue) con la misma altura → ``marca_ligada``.
    - Adornos (isGrace) → excluidos.
    - Acordes → de la más aguda a la más grave.
    - ``marca_ligada=None`` → las notas ligadas se omiten de la lista.
    """
    resultado: list[NotaTexto] = []
    for elemento in score.recurse().notes:
        notas = notas_a_nombrar(elemento)
        if not notas:
            continue
        for n in notas:
            texto = texto_de_nota(elemento, n, marca_ligada)
            if texto is None:
                continue
            compas = _numero_compas(elemento)
            resultado.append(NotaTexto(
                elemento=elemento,
                nota=n,
                pitch=n.pitch,
                texto=texto,
                compas=compas,
            ))
    return resultado


# ---------------------------------------------------------------------------
# Dataclass Resumen
# ---------------------------------------------------------------------------

@dataclass
class Resumen:
    """Resumen del proceso de anotación de una partitura."""
    notas_nombradas: int
    ligadas_marcadas: int   # notas que recibieron MARCA_LIGADA
    acordes: int
    armadura: str
    cambios: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Anotar partitura
# ---------------------------------------------------------------------------

def anotar_partitura(
    score: stream.Score,
    marca_ligada: Optional[str] = MARCA_LIGADA,
) -> Resumen:
    """Añade el nombre de cada nota como lyric y devuelve un Resumen.

    El número de lyric se coloca tras el máximo ya existente para no solapar
    letras de canciones existentes.

    Para notas ligadas (stop/continue) con la misma altura que la anterior,
    añade marca_ligada (por defecto '·') en lugar del nombre. Si la altura
    es distinta (posible ligadura de expresión mal leída), añade el nombre normal.
    Si marca_ligada es None, no añade nada a las notas ligadas.
    """
    from music21 import chord as chord_mod

    # Calcular número de lyric a usar
    numero_letra = 1
    for elem in score.recurse().notes:
        lyric_list = getattr(elem, "lyrics", [])
        for lyr in lyric_list:
            if lyr.number is not None and lyr.number >= numero_letra:
                numero_letra = lyr.number + 1
        if isinstance(elem, chord_mod.Chord):
            for n in elem.notes:
                for lyr in getattr(n, "lyrics", []):
                    if lyr.number is not None and lyr.number >= numero_letra:
                        numero_letra = lyr.number + 1

    notas_nombradas = 0
    ligadas_marcadas = 0
    acordes_count = 0

    # Usamos textos_por_nota para no duplicar lógica
    lista = textos_por_nota(score, marca_ligada=marca_ligada)

    # Aplicar como lyrics; rastrear el elemento actual para el índice dentro del acorde
    elemento_actual = None
    i_en_elemento = 0

    for nt in lista:
        if nt.elemento is not elemento_actual:
            elemento_actual = nt.elemento
            i_en_elemento = 0
            if isinstance(nt.elemento, chord_mod.Chord):
                acordes_count += 1

        if nt.texto == marca_ligada and marca_ligada is not None:
            ligadas_marcadas += 1
        lyric_num = numero_letra + i_en_elemento
        nt.elemento.addLyric(nt.texto, lyricNumber=lyric_num)
        notas_nombradas += 1
        i_en_elemento += 1

    # Descripción de armadura
    todas_ks = list(score.recurse().getElementsByClass(key.KeySignature))
    if not todas_ks:
        armadura_str = describir_armadura(None)
    else:
        armadura_str = describir_armadura(todas_ks[0])
        distintas = {ks.sharps for ks in todas_ks}
        if len(distintas) > 1:
            armadura_str += " (con cambios de armadura)"

    cambios = describir_cambios(score)
    avisos = avisos_armadura(score)

    return Resumen(
        notas_nombradas=notas_nombradas,
        ligadas_marcadas=ligadas_marcadas,
        acordes=acordes_count,
        armadura=armadura_str,
        cambios=cambios,
        avisos=avisos,
    )


# ---------------------------------------------------------------------------
# Entrada/salida MusicXML
# ---------------------------------------------------------------------------

def anotar_musicxml(entrada: Path, salida: Path) -> Resumen:
    """Lee un MusicXML, anota los nombres y escribe el resultado.

    Raises FileNotFoundError si la entrada no existe.
    """
    entrada = Path(entrada)
    salida = Path(salida)

    if not entrada.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de entrada: {entrada}"
        )

    score = converter.parse(str(entrada))
    resumen = anotar_partitura(score)
    score.write("musicxml", fp=str(salida))
    return resumen
