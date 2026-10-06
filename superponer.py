"""
superponer.py — Escribe los nombres de las notas directamente sobre el PDF original.

En lugar de redibujar la partitura con MuseScore, sobreimprime los nombres encima
del PDF vectorial. Los nombres se colocan justo debajo de cada pentagrama, evitando
tapar matices, reguladores, ligaduras y otros textos.

API pública:
    analizar(pdf, partitura) → Analisis
    colocar_nombres(analisis) → None
    escribir_pdf(analisis, salida, color_dudosas=True) → None
    superponer_nombres(pdf, partitura, salida, ...) → Analisis   # atajo CLI

Uso típico (CLI):
    analisis = superponer_nombres(pdf, partitura, salida)

Uso avanzado (GUI con corrección manual):
    analisis = analizar(pdf, partitura)
    # el usuario revisa/corrige analisis.notas
    colocar_nombres(analisis)
    escribir_pdf(analisis, salida)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pymupdf

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ZOOM_MASCARA: int = 4

TAMANOS: tuple[tuple[float, float], ...] = (
    (9.5, 0.0),
    (8.5, 2.5),
    (7.5, 5.0),
    (6.5, 9.0),
)

DESPLAZAMIENTOS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (-1.5, 1.0),
    (1.5, 1.0),
    (-3.0, 2.5),
    (3.0, 2.5),
)

MARGEN_TINTA: float = 0.6
MARGEN_TINTA_PEQUENO: float = 0.35
MARGEN_NOMBRES_X: float = 1.1
MARGEN_NOMBRES_Y: float = 0.3
PESO_PRIORITARIO: int = 25

POS_PREFERIDA_ESPACIOS: float = 1.6
TAM_PREFERIDO: float = 9.5
COSTE_ARRIBA: float = 0.6
COSTE_ABAJO: float = 1.0

COLOR_NORMAL: tuple[float, float, float] = (0.0, 0.0, 0.0)
COLOR_DEDUCIDA: tuple[float, float, float] = (0.75, 0.0, 0.0)

FUENTE_NOMBRE: str = "tiro"

# Caracteres de cabeza en fuentes musicales clásicas
_CABEZAS_CLASICAS: frozenset[str] = frozenset("œ˙w")

# Puntos de código SMuFL para cabezas (U+E0A0–U+E0A4)
_CABEZAS_SMUFL: frozenset[int] = frozenset(range(0xE0A0, 0xE0A5))

# Fuentes musicales tipo Sonata/Sibelius/Finale
_PALABRAS_MUSICA: tuple[str, ...] = (
    "opus", "sibelius", "petrucci", "maestro", "engraver",
    "helsinki", "reprise", "inkpen", "jazz", "broadway", "sonata",
)

# Fuentes SMuFL modernas
_PALABRAS_SMUFL: tuple[str, ...] = (
    "leland", "bravura", "petaluma", "sebastian", "gonville",
    "emmentaler", "november2", "smufl",
)

# Alteraciones en fuentes clásicas y SMuFL
_ALT_CLASICAS: dict[str, int] = {"#": 1, "b": -1, "n": 0}
_ALT_SMUFL: dict[int, int] = {0xE262: 1, 0xE260: -1, 0xE261: 0}

# Umbral para agrupar accidentales de armadura (puntos)
_UMBRAL_GRUPO_ARM: float = 22.0
# Umbral para detectar doble barra (puntos entre las dos líneas)
_UMBRAL_DOBLE_BARRA: float = 5.0


# ---------------------------------------------------------------------------
# Excepción
# ---------------------------------------------------------------------------

class SinCabezasError(ValueError):
    """El PDF no tiene cabezas de nota reconocibles (puede ser escaneado)."""


# ---------------------------------------------------------------------------
# Dataclasses geométricos (internos + exportados para verificacion.py)
# ---------------------------------------------------------------------------

@dataclass
class Pentagrama:
    """Pentagrama detectado en el PDF."""
    pagina: int
    arriba: float
    abajo: float
    x0: float
    x1: float

    @property
    def espacio(self) -> float:
        """Espacio interlineal del pentagrama (puntos)."""
        return (self.abajo - self.arriba) / 4.0


@dataclass
class Cabeza:
    """Cabeza de nota detectada en el PDF."""
    pent: int                                    # índice de pentagrama (local al inicio, luego global)
    x: float                                     # origen x del glifo
    xc: float                                    # centro x del bounding box
    y: float                                     # origen y (centro vertical de la cabeza)
    paso: int                                    # posición en el pentagrama (0 = primera línea baja…)
    tam: float                                   # tamaño de la fuente
    bbox: tuple[float, float, float, float] = field(default_factory=lambda: (0.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# Dataclasses públicos de la API
# ---------------------------------------------------------------------------

@dataclass
class NotaColocada:
    """Una nota/cabeza del PDF con su nombre asignado y estado de colocación."""
    id: int
    pagina: int                                   # 0-based
    linea: int                                    # 1-based (sobre todo el documento)
    compas: Optional[int]                         # número de compás de Audiveris (o vecino)
    cabeza: tuple[float, float, float, float]     # bbox de la cabeza en puntos
    texto: str                                    # "Mib", "·", "?"
    estado: str                                   # "ok" | "deducida" | "dudosa"
    motivo: str                                   # "" | "Audiveris no la leyó" | "alteración distinta" | …
    x: Optional[float] = None                    # posición x del texto (tras colocar_nombres)
    base: Optional[float] = None                 # línea base del texto
    tam: Optional[float] = None                  # tamaño de fuente usado
    sin_hueco: bool = False
    fija: bool = False                           # True si el usuario fijó la posición manualmente
    acorde: Optional[int] = None                 # id común para todas las cabezas del mismo acorde (None si es nota suelta)

    def a_dict(self) -> dict:
        """Serializa a diccionario JSON-compatible."""
        return {
            "id": self.id,
            "pagina": self.pagina,
            "linea": self.linea,
            "compas": self.compas,
            "cabeza": list(self.cabeza),
            "texto": self.texto,
            "estado": self.estado,
            "motivo": self.motivo,
            "x": self.x,
            "base": self.base,
            "tam": self.tam,
            "sin_hueco": self.sin_hueco,
            "fija": self.fija,
            "acorde": self.acorde,
        }


@dataclass
class Analisis:
    """Resultado del análisis de un PDF + partitura Audiveris."""
    pdf: Path
    paginas: list[tuple[float, float]]            # (ancho, alto) por página
    notas: list[NotaColocada]
    cambios: list[str]                            # clave/armadura y cambios
    avisos: list[str]                             # armaduras que no coinciden, etc.
    # Campos internos para colocar_nombres y escribir_pdf
    _pentagramas: list[Pentagrama] = field(default_factory=list, repr=False)

    def a_dict(self) -> dict:
        """Serializa a diccionario JSON-compatible."""
        return {
            "pdf": str(self.pdf),
            "paginas": [list(p) for p in self.paginas],
            "notas": [n.a_dict() for n in self.notas],
            "cambios": self.cambios,
            "avisos": self.avisos,
        }

    def a_json(self) -> str:
        """Serializa a JSON."""
        return json.dumps(self.a_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Auxiliares de fuente
# ---------------------------------------------------------------------------

def _nombre_fuente_base(fontname: str) -> str:
    """Elimina el prefijo de subconjunto ``XXXXXX+``."""
    return fontname.split("+", 1)[-1]


def _es_fuente_smufl(fontname: str) -> bool:
    base = _nombre_fuente_base(fontname).lower()
    if "text" in base:
        return False
    return any(k in base for k in _PALABRAS_SMUFL)


def _es_fuente_musica_clasica(fontname: str) -> bool:
    base = _nombre_fuente_base(fontname).lower()
    if "text" in base:
        return False
    return any(k in base for k in _PALABRAS_MUSICA)


def _es_cabeza_char(codepoint: int, fontname: str) -> bool:
    """True si el carácter PDF es una cabeza de nota reconocible."""
    if _es_fuente_smufl(fontname):
        return codepoint in _CABEZAS_SMUFL
    if _es_fuente_musica_clasica(fontname):
        return chr(codepoint) in _CABEZAS_CLASICAS
    return False


def _es_alt_clasica(codepoint: int, fontname: str) -> Optional[int]:
    """Devuelve el valor de alteración si el glifo es un accidental clásico, o None."""
    if not _es_fuente_musica_clasica(fontname):
        return None
    return _ALT_CLASICAS.get(chr(codepoint))


def _es_alt_smufl(codepoint: int) -> Optional[int]:
    """Devuelve el valor de alteración SMuFL, o None."""
    return _ALT_SMUFL.get(codepoint)


# ---------------------------------------------------------------------------
# Detección de pentagramas
# ---------------------------------------------------------------------------

TRAMO_MINIMO_LINEA_PENTAGRAMA = 0.05   # fracción del ancho de página (una línea adicional es mucho más corta)
ESPACIO_MIN_PENTAGRAMA = 2.0    # pt entre líneas consecutivas
ESPACIO_MAX_PENTAGRAMA = 12.0
TOLERANCIA_LINEA = 0.35         # pt de desviación admitida respecto al espaciado regular


def _agrupar_lineas_equiespaciadas(ys: list[float]) -> list[list[float]]:
    """Busca grupos de 5 alturas con separación constante (un pentagrama).

    Ignora líneas sueltas intercaladas (p. ej. barras de notas o líneas
    adicionales largas) que romperían una agrupación de 5 en 5 consecutivas.
    """
    grupos: list[list[float]] = []
    i = 0
    while i <= len(ys) - 5:
        grupo = None
        for j in range(i + 1, min(i + 5, len(ys))):
            espacio = ys[j] - ys[i]
            if not ESPACIO_MIN_PENTAGRAMA <= espacio <= ESPACIO_MAX_PENTAGRAMA:
                continue
            candidato = [ys[i]]
            for k in range(1, 5):
                objetivo = ys[i] + k * espacio
                cercana = min(ys, key=lambda y: abs(y - objetivo))
                if abs(cercana - objetivo) > TOLERANCIA_LINEA:
                    break
                candidato.append(cercana)
            if len(candidato) == 5:
                grupo = candidato
                break
        if grupo is None:
            i += 1
            continue
        grupos.append(grupo)
        i = ys.index(grupo[-1]) + 1
    return grupos


def detectar_pentagramas(page: pymupdf.Page, num_pagina: int) -> list[Pentagrama]:
    """Detecta grupos de 5 líneas horizontales largas en la página.

    Devuelve lista de :class:`Pentagrama` para esta página, en orden de arriba a abajo.
    """
    # Solo cuentan los trazos largos (la línea entera o, como mucho, un compás):
    # muchas líneas adicionales cortas a la misma altura (notas agudas seguidas)
    # sumarían tanta longitud como una línea del pentagrama y lo desplazarían.
    tramo_minimo = page.rect.width * TRAMO_MINIMO_LINEA_PENTAGRAMA
    segs: dict[float, list[float]] = {}
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.3:
                y = round(it[1].y, 1)
                x0, x1 = sorted((it[1].x, it[2].x))
            elif it[0] == "re" and it[1].height < 1.2 and it[1].width > 20:
                y = round((it[1].y0 + it[1].y1) / 2, 1)
                x0, x1 = it[1].x0, it[1].x1
            else:
                continue
            if x1 - x0 < tramo_minimo:
                continue
            entrada = segs.setdefault(y, [0.0, x0, x1])
            entrada[0] += x1 - x0
            entrada[1] = min(entrada[1], x0)
            entrada[2] = max(entrada[2], x1)

    ys = sorted(
        y for y, (lon, _, _) in segs.items()
        if lon > page.rect.width * 0.35
    )

    grupos = _agrupar_lineas_equiespaciadas(ys)

    resultado: list[Pentagrama] = []
    for g in grupos:
        x0s = [segs[y][1] for y in g]
        x1s = [segs[y][2] for y in g]
        resultado.append(Pentagrama(
            pagina=num_pagina,
            arriba=g[0],
            abajo=g[-1],
            x0=min(x0s),
            x1=max(x1s),
        ))
    return resultado


# ---------------------------------------------------------------------------
# Detección de cabezas de nota
# ---------------------------------------------------------------------------

def _lineas_adicionales(
    page: pymupdf.Page, pents: list[Pentagrama]
) -> list[tuple[float, float, float]]:
    """Líneas adicionales (las cortas por encima o debajo del pentagrama): ``(y, x0, x1)``."""
    espacio = sum(p.espacio for p in pents) / len(pents)
    lineas_pentagrama = [
        p.arriba + k * p.espacio for p in pents for k in range(5)
    ]
    resultado = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.3:
                y = (it[1].y + it[2].y) / 2
                x0, x1 = sorted((it[1].x, it[2].x))
            elif it[0] == "re" and it[1].height < 1.2:
                y = (it[1].y0 + it[1].y1) / 2
                x0, x1 = it[1].x0, it[1].x1
            else:
                continue
            if not (0.8 * espacio <= x1 - x0 <= 4.0 * espacio):
                continue          # ni líneas del pentagrama ni trocitos sueltos
            if any(abs(y - yl) < 0.3 for yl in lineas_pentagrama):
                continue
            resultado.append((y, x0, x1))
    return resultado


def _adicionales_presentes(
    adicionales: list[tuple[float, float, float]], xc: float, ys: list[float], tol: float
) -> bool:
    """True si hay una línea adicional en cada altura de ``ys`` que pase por x = xc."""
    return all(
        any(abs(y - ya) <= tol and x0 - 1 <= xc <= x1 + 1 for ya, x0, x1 in adicionales)
        for y in ys
    )


def _pentagrama_de_cabeza(
    pents: list[Pentagrama],
    adicionales: list[tuple[float, float, float]],
    xc: float,
    y: float,
) -> int:
    """Índice del pentagrama al que pertenece una cabeza de nota.

    Una nota fuera del pentagrama necesita líneas adicionales entre ella y SU
    pentagrama. Cuando los sistemas están juntos, una nota muy aguda puede quedar
    más cerca del pentagrama de arriba; por eso, entre los pentagramas vecinos se
    elige aquel cuyas líneas adicionales están dibujadas, y solo si ninguno
    encaja se usa el más cercano.
    """
    def distancia(p: Pentagrama) -> float:
        return abs((p.arriba + p.abajo) / 2 - y)

    candidatos = sorted(range(len(pents)), key=lambda k: distancia(pents[k]))[:2]
    encajan: list[tuple[int, int]] = []               # (líneas adicionales confirmadas, índice)
    for k in candidatos:
        p = pents[k]
        e = p.espacio
        if p.arriba - 0.75 * e <= y <= p.abajo + 0.75 * e:
            return k                                   # dentro o pegada: sin líneas adicionales
        if y < p.arriba:
            n = int((p.arriba - y) / e + 0.25)        # líneas adicionales necesarias por encima
            alturas = [p.arriba - i * e for i in range(1, n + 1)]
        else:
            n = int((y - p.abajo) / e + 0.25)
            alturas = [p.abajo + i * e for i in range(1, n + 1)]
        if _adicionales_presentes(adicionales, xc, alturas, 0.3 * e):
            encajan.append((n, k))
    if encajan:
        # Si encajan los dos (la nota está sobre su propia línea adicional, que también
        # podría ser «la primera» del otro pentagrama), gana el que tiene toda la
        # escalera de líneas adicionales hasta él: más pruebas.
        return max(encajan)[1]
    return candidatos[0]


def detectar_cabezas(page: pymupdf.Page, pents_locales: list[Pentagrama]) -> list[Cabeza]:
    """Detecta cabezas de nota en la página y las asigna al pentagrama más cercano.

    Los índices de pentagrama son locales (índice dentro de ``pents_locales``).
    Usa :func:`detectar_pentagramas` primero para obtener los pentagramas.
    """
    if not pents_locales:
        return []

    adicionales = _lineas_adicionales(page, pents_locales)
    resultado: list[Cabeza] = []

    for sp in page.get_texttrace():
        fn = sp["font"]
        for ch in sp["chars"]:
            c = ch[0]
            if not _es_cabeza_char(c, fn):
                continue
            ox, oy = ch[2]
            bx0, by0, bx1, by1 = ch[3]
            idx = _pentagrama_de_cabeza(pents_locales, adicionales, (bx0 + bx1) / 2.0, oy)
            p = pents_locales[idx]
            paso = round((p.abajo - oy) / (p.espacio / 2))
            resultado.append(Cabeza(
                pent=idx,
                x=ox,
                xc=(bx0 + bx1) / 2.0,
                y=oy,
                paso=paso,
                tam=sp["size"],
                bbox=(bx0, by0, bx1, by1),
            ))

    resultado.sort(key=lambda h: (h.pent, round(h.x / 2), h.y))
    return resultado


# ---------------------------------------------------------------------------
# Extracción de caracteres por página (para inferencia y cross-check)
# ---------------------------------------------------------------------------

def _extraer_chars_pagina(page: pymupdf.Page) -> list[tuple[int, str, float, float]]:
    """Devuelve lista de ``(codepoint, fontname_base, ox, oy)`` para todos los glifos."""
    resultado = []
    for sp in page.get_texttrace():
        fn_base = _nombre_fuente_base(sp["font"])
        for ch in sp["chars"]:
            ox, oy = ch[2]
            resultado.append((ch[0], fn_base, ox, oy))
    return resultado


# ---------------------------------------------------------------------------
# Detección de armadura en el PDF
# ---------------------------------------------------------------------------

def _es_alt(codepoint: int, fontname_base: str) -> Optional[int]:
    """Devuelve el valor de alteración del glifo, o None si no es un accidental."""
    fn = fontname_base.lower()
    if "text" in fn:
        return None
    if any(k in fn for k in _PALABRAS_SMUFL):
        return _ALT_SMUFL.get(codepoint)
    if any(k in fn for k in _PALABRAS_MUSICA):
        alt = _ALT_CLASICAS.get(chr(codepoint))
        return alt
    return None


def _armadura_inicio_sistema(
    pent: Pentagrama,
    heads_pent: list[Cabeza],
    chars: list[tuple],
) -> int:
    """Cuenta los accidentales de armadura al inicio del pentagrama (antes de la 1ª cabeza).

    Devuelve el número de alteraciones (negativo = bemoles, positivo = sostenidos).
    """
    if heads_pent:
        primer_x = min(h.x for h in heads_pent)
    else:
        primer_x = pent.x1

    e = pent.espacio
    en_pentagrama = [
        (c, fn, ox, oy) for (c, fn, ox, oy) in chars
        if pent.x0 - 5 <= ox < primer_x - 5
        and pent.arriba - e * 3 <= oy <= pent.abajo + e * 3
    ]
    # La armadura termina en el primer silencio (p. ej. «𝄾 Solb»: ese bemol es de la nota)
    silencios = [ox for (c, fn, ox, oy) in en_pentagrama
                 if c in SILENCIOS_SMUFL or (_es_fuente_musica_clasica(fn) and chr(c) in SILENCIOS_CLASICOS)]
    limite = min(silencios) if silencios else primer_x

    alteraciones = sorted(
        (ox, alt) for (c, fn, ox, oy) in en_pentagrama
        if ox < limite and (alt := _es_alt(c, fn)) is not None
    )
    # Solo el primer grupo seguido: las alteraciones de la armadura van pegadas entre sí
    grupo: list[int] = []
    x_anterior = None
    for ox, alt in alteraciones:
        if x_anterior is not None and ox - x_anterior > 2.5 * e:
            break
        grupo.append(alt)
        x_anterior = ox
    flats = sum(1 for alt in grupo if alt == -1)
    sharps = sum(1 for alt in grupo if alt == 1)

    if flats > 0 and sharps == 0:
        return -flats
    if sharps > 0 and flats == 0:
        return sharps
    return 0


def _detectar_dobles_barras(page: pymupdf.Page, pent: Pentagrama) -> list[float]:
    """Detecta posiciones x de dobles barras dentro del pentagrama.

    Una doble barra = dos líneas verticales separadas < 5 puntos.
    """
    y_rango = (pent.arriba - 2, pent.abajo + 2)
    barras: list[float] = []

    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] != "l":
                continue
            a, b = it[1], it[2]
            # Línea vertical: x casi constante, y varía
            if abs(a.x - b.x) > 2:
                continue
            if abs(a.y - b.y) < 8:
                continue
            if not (y_rango[0] <= min(a.y, b.y) and max(a.y, b.y) <= y_rango[1] + 20):
                continue
            xv = (a.x + b.x) / 2.0
            if xv < pent.x0 or xv > pent.x1:
                continue
            barras.append(round(xv, 1))

    barras.sort()
    dobles: list[float] = []
    for i in range(len(barras) - 1):
        if barras[i + 1] - barras[i] < _UMBRAL_DOBLE_BARRA:
            dobles.append((barras[i] + barras[i + 1]) / 2.0)
    return dobles


def _armadura_tras_doble_barra(
    pent: Pentagrama,
    x_doble: float,
    heads_pent: list[Cabeza],
    chars: list[tuple],
) -> Optional[int]:
    """Detecta un cambio de armadura justo después de la doble barra dada.

    Devuelve el nuevo valor de alteraciones, o None si no hay cambio de armadura.
    """
    # Siguiente cabeza a partir de la doble barra
    cabs_despues = [h for h in heads_pent if h.x > x_doble + 2]
    if cabs_despues:
        siguiente_cab_x = min(h.x for h in cabs_despues)
    else:
        siguiente_cab_x = pent.x1

    flats = 0
    sharps = 0
    xs_alt: list[float] = []

    for (c, fn, ox, oy) in chars:
        if ox <= x_doble + 1:
            continue
        if ox >= siguiente_cab_x:
            continue
        if oy < pent.arriba - pent.espacio * 3 or oy > pent.abajo + pent.espacio * 3:
            continue
        alt = _es_alt(c, fn)
        if alt is None:
            continue
        xs_alt.append(ox)
        if alt == -1:
            flats += 1
        elif alt == 1:
            sharps += 1
        elif alt == 0 and xs_alt:
            # Becuadro → podría ser parte de una modulación
            pass

    if not xs_alt:
        return None

    # Verificar que los accidentales están agrupados (armadura, no nota suelta)
    if len(xs_alt) >= 2:
        rango = max(xs_alt) - min(xs_alt)
        if rango > _UMBRAL_GRUPO_ARM:
            return None  # demasiado dispersos para ser armadura

    # Verificar que no hay cabeza a la misma altura justo después de los accidentales
    # (si hay una cabeza inmediatamente al mismo y-pos, podría ser nota con accidental)
    fin_alts = max(xs_alt) if xs_alt else x_doble
    cabs_cercanas = [
        h for h in heads_pent
        if fin_alts < h.x < fin_alts + 15
    ]
    for (c2, fn2, ox2, oy2) in chars:
        if ox2 <= fin_alts or ox2 > fin_alts + 15:
            continue
        if not _es_cabeza_char(c2, fn2):
            continue
        # Si hay una cabeza a la misma y que un accidental → es nota con accidental
        for (c3, fn3, ox3, oy3) in chars:
            if abs(ox3 - ox2) > 20 or not (_es_alt(c3, fn3) is not None):
                continue
            if abs(oy3 - oy2) < pent.espacio * 0.5:
                return None

    if flats > 0 and sharps == 0:
        return -flats
    if sharps > 0 and flats == 0:
        return sharps
    return 0  # becuadros → regresa a Do mayor


def _detectar_armadura_por_sistema(
    doc: pymupdf.Document,
    pents: list[Pentagrama],
    heads: list[Cabeza],
    chars: dict[int, list],
) -> list[int]:
    """Devuelve el número de alteraciones de armadura para cada pentagrama.

    Considera el inicio del sistema y cambios mid-línea.
    El valor devuelto es el que está en vigor AL FINAL de la línea.
    """
    resultado: list[int] = []
    for k, pent in enumerate(pents):
        heads_k = [h for h in heads if h.pent == k]
        chars_pag = chars.get(pent.pagina, [])
        arm = _armadura_inicio_sistema(pent, heads_k, chars_pag)

        # Buscar cambios mid-línea
        pagina = doc[pent.pagina]
        dobles = _detectar_dobles_barras(pagina, pent)
        for x_dbl in dobles:
            cambio = _armadura_tras_doble_barra(pent, x_dbl, heads_k, chars_pag)
            if cambio is not None:
                arm = cambio

        resultado.append(arm)
    return resultado


def _cambios_armadura_por_sistema(
    doc: pymupdf.Document,
    pents: list[Pentagrama],
    heads: list[Cabeza],
    chars: dict[int, list],
) -> dict[int, list[tuple[float, int]]]:
    """Devuelve los cambios de armadura mid-línea: {idx_pent: [(x_doble, nuevo_valor)]}."""
    resultado: dict[int, list[tuple[float, int]]] = {}
    for k, pent in enumerate(pents):
        heads_k = [h for h in heads if h.pent == k]
        chars_pag = chars.get(pent.pagina, [])
        pagina = doc[pent.pagina]
        dobles = _detectar_dobles_barras(pagina, pent)
        cambios: list[tuple[float, int]] = []
        for x_dbl in dobles:
            cambio = _armadura_tras_doble_barra(pent, x_dbl, heads_k, chars_pag)
            if cambio is not None:
                cambios.append((x_dbl, cambio))
        if cambios:
            resultado[k] = cambios
    return resultado


# ---------------------------------------------------------------------------
# Armadura de Audiveris por sistema
# ---------------------------------------------------------------------------

def _indices_sistema(parte) -> list[int]:
    """Devuelve los índices de compás donde empieza cada sistema."""
    from music21 import layout

    compases = list(parte.getElementsByClass("Measure"))
    inicios = [
        i for i, m in enumerate(compases)
        if m.getElementsByClass(layout.SystemLayout)
    ]
    if not inicios or inicios[0] != 0:
        inicios = [0] + inicios
    return inicios


def _armadura_omr_por_sistema(partitura, pents: list[Pentagrama]) -> list[int]:
    """Devuelve las alteraciones de armadura de Audiveris por sistema.

    Usa la última KeySignature en vigor antes del inicio de cada sistema.
    """
    from music21 import key as m21key

    parte = partitura.parts[0]
    compases = list(parte.getElementsByClass("Measure"))
    inicios = _indices_sistema(parte)
    limites = inicios + [len(compases)]

    # Recoger todas las KeySignatures con su índice de compás
    ks_por_compas: list[tuple[int, int]] = []  # (indice_compas, sharps)
    for i, m in enumerate(compases):
        for ks in m.getElementsByClass(m21key.KeySignature):
            ks_por_compas.append((i, ks.sharps))

    resultado: list[int] = []
    n_sistemas = len(pents)
    for k in range(n_sistemas):
        inicio = limites[k] if k < len(limites) else 0
        # La KeySignature en vigor es la última cuyo compás <= inicio
        sharps = 0
        for (idx_m, sh) in ks_por_compas:
            if idx_m <= inicio:
                sharps = sh
        resultado.append(sharps)

    return resultado


# ---------------------------------------------------------------------------
# Notas de Audiveris con referencia al objeto music21
# ---------------------------------------------------------------------------

def _notas_omr_con_ref(partitura) -> list[list[tuple[int, str, object]]]:
    """Lista de notas por sistema: cada entrada es ``(paso, texto, nota_m21)``.

    El ``paso`` es la posición en el pentagrama según clave de Audiveris.
    El ``texto`` es el nombre en solfeo o ``MARCA_LIGADA``.
    """
    from music21 import layout
    from music21 import clef as m21clef
    from nombres import notas_a_nombrar, texto_de_nota

    sistemas: list[list[tuple[int, str, object]]] = []
    actual: list[tuple[int, str, object]] = []

    for m in partitura.parts[0].getElementsByClass("Measure"):
        if m.getElementsByClass(layout.SystemLayout) and actual:
            sistemas.append(actual)
            actual = []
        for elemento in m.recurse().notes:
            cl = elemento.getContextByClass(m21clef.Clef) or m21clef.BassClef()
            for nota in notas_a_nombrar(elemento):   # adornos fuera; acordes de agudo a grave
                paso = nota.pitch.diatonicNoteNum - cl.lowestLine
                actual.append((paso, texto_de_nota(elemento, nota), elemento))

    if actual:
        sistemas.append(actual)
    return sistemas


# ---------------------------------------------------------------------------
# Alineación por programación dinámica
# ---------------------------------------------------------------------------

def _alinear(
    a: list[int],
    b: list[int],
) -> list[tuple[int, Optional[int]]]:
    """Alinea pasos PDF (``a``) con pasos OMR (``b``) por edición mínima.

    Devuelve lista de ``(i_pdf, j_omr | None)``.
    ``None`` indica que la cabeza i_pdf no tiene pareja en OMR.
    """
    n, m = len(a), len(b)
    if n == 0:
        return []

    D = np.zeros((n + 1, m + 1), dtype=float)
    D[:, 0] = np.arange(n + 1)
    D[0, :] = np.arange(m + 1)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            costo_sub = 0.0 if a[i - 1] == b[j - 1] else 1.5
            D[i, j] = min(
                D[i - 1, j - 1] + costo_sub,
                D[i - 1, j] + 1.0,
                D[i, j - 1] + 1.0,
            )

    i, j = n, m
    pares: list[tuple[int, Optional[int]]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i - 1, j - 1] + (0.0 if a[i - 1] == b[j - 1] else 1.5):
            pares.append((i - 1, j - 1 if a[i - 1] == b[j - 1] else None))
            i -= 1
            j -= 1
        elif i > 0 and D[i, j] == D[i - 1, j] + 1.0:
            pares.append((i - 1, None))
            i -= 1
        else:
            j -= 1

    return pares[::-1]


# ---------------------------------------------------------------------------
# Inferencia de notas sin pareja
# ---------------------------------------------------------------------------

def _alteracion_impresa(
    chars: list[tuple],
    h: Cabeza,
    pent: Pentagrama,
) -> Optional[int]:
    """Alteración dibujada justo a la izquierda de la cabeza, o None."""
    for (c, fn, ox, oy) in chars:
        if not (0 < h.x - ox < 2.2 * pent.espacio):
            continue
        if abs(oy - h.y) > 0.4 * pent.espacio:
            continue
        alt_sm = _ALT_SMUFL.get(c)
        if alt_sm is not None and _es_fuente_smufl(fn):
            return alt_sm
        if any(k in fn.lower() for k in _PALABRAS_MUSICA) and "text" not in fn.lower():
            alt_cl = _ALT_CLASICAS.get(chr(c))
            if alt_cl is not None:
                return alt_cl
    return None


def _numero_compas(nota) -> int:
    """Número de compás de la nota en music21 (0 si no disponible)."""
    try:
        m = nota.getContextByClass("Measure")
        if m is not None:
            return int(getattr(m, "number", 0) or 0)
    except Exception:
        pass
    return 0


def _inferir_nombre(
    h: Cabeza,
    nota_vecina,
    chars: list[tuple],
    pent: Pentagrama,
) -> str:
    """Infiere el nombre de una cabeza que Audiveris no leyó."""
    from music21 import clef as m21clef, key as m21key
    from music21 import pitch as m21pitch
    from nombres import nombre_nota

    cl = nota_vecina.getContextByClass(m21clef.Clef) or m21clef.BassClef()
    ks = nota_vecina.getContextByClass(m21key.KeySignature)
    p = m21pitch.Pitch()
    p.diatonicNoteNum = cl.lowestLine + h.paso

    # Alteración impresa a la izquierda de la cabeza
    alter = _alteracion_impresa(chars, h, pent)
    if alter is None:
        # Alteración impresa en el mismo compás para la misma nota
        compas = nota_vecina.getContextByClass("Measure")
        if compas:
            previas = [
                q for n2 in compas.recurse().notes
                for q in n2.pitches
                if q.step == p.step
                and q.octave == p.octave
                and q.accidental is not None
                and q.accidental.displayStatus
            ]
            if previas:
                alter = int(round(previas[-1].alter))
        if alter is None and ks is not None:
            acc_arm = ks.accidentalByStep(p.step)
            alter = int(round(acc_arm.alter)) if acc_arm else 0
        if alter is None:
            alter = 0

    if alter:
        p.accidental = m21pitch.Accidental(alter)
    return nombre_nota(p)


# ---------------------------------------------------------------------------
# Máscaras de tinta
# ---------------------------------------------------------------------------

class _Tinta:
    """Máscara de tinta del PDF con tabla de sumas acumuladas para O(1)."""

    def __init__(self, page: pymupdf.Page) -> None:
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(ZOOM_MASCARA, ZOOM_MASCARA),
            colorspace=pymupdf.csGRAY,
        )
        m = (
            np.frombuffer(pix.samples, dtype=np.uint8)
            .reshape(pix.height, pix.width) < 160
        )
        self.h, self.w = m.shape
        self.sat = np.zeros((self.h + 1, self.w + 1), dtype=np.int32)
        self.sat[1:, 1:] = m.astype(np.int32).cumsum(0).cumsum(1)

    def pixeles(self, r: pymupdf.Rect, margen: float) -> int:
        """Número de píxeles de tinta en el rectángulo ``r`` con margen."""
        x0 = max(0, int((r.x0 - margen) * ZOOM_MASCARA))
        y0 = max(0, int((r.y0 - margen) * ZOOM_MASCARA))
        x1 = min(self.w, int((r.x1 + margen) * ZOOM_MASCARA) + 1)
        y1 = min(self.h, int((r.y1 + margen) * ZOOM_MASCARA) + 1)
        if x1 <= x0 or y1 <= y0:
            return 10 ** 6
        s = self.sat
        return int(s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0])


class _Prioritaria(_Tinta):
    """Tinta prioritaria: textos, matices, reguladores, ligaduras."""

    def __init__(self, page: pymupdf.Page) -> None:
        w = int(page.rect.width * ZOOM_MASCARA) + 1
        h = int(page.rect.height * ZOOM_MASCARA) + 1
        m = np.zeros((h, w), dtype=bool)

        def marca(x0: float, y0: float, x1: float, y1: float) -> None:
            r0 = max(0, int(y0 * ZOOM_MASCARA))
            r1 = int(y1 * ZOOM_MASCARA) + 1
            c0 = max(0, int(x0 * ZOOM_MASCARA))
            c1 = int(x1 * ZOOM_MASCARA) + 1
            if r1 > r0 and c1 > c0:
                m[r0:r1, c0:c1] = True

        for sp in page.get_texttrace():
            fn = sp["font"]
            es_musical = (
                _es_fuente_musica_clasica(fn) or _es_fuente_smufl(fn)
            )
            for ch in sp["chars"]:
                # Texto ordinario (dinámica, letras de ensayo, letras de canción…)
                c = ch[0]
                if es_musical:
                    # En fuente musical solo marcamos dinámicas/articulaciones
                    if chr(c) not in "pfmzrsnƒπ":
                        continue
                x0, y0, x1, y1 = ch[3]
                marca(x0, y0 + (y1 - y0) * 0.25, x1, y1 - (y1 - y0) * 0.15)

        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l":
                    a, b = it[1], it[2]
                    # Línea oblicua → regulador
                    if abs(a.y - b.y) > 0.3 and abs(a.x - b.x) > 0.3:
                        marca(min(a.x, b.x), min(a.y, b.y),
                              max(a.x, b.x), max(a.y, b.y))
                elif it[0] == "c":
                    xs = [pt.x for pt in it[1:]]
                    ys = [pt.y for pt in it[1:]]
                    marca(min(xs), min(ys), max(xs), max(ys))

        self.h, self.w = m.shape
        self.sat = np.zeros((self.h + 1, self.w + 1), dtype=np.int32)
        self.sat[1:, 1:] = m.astype(np.int32).cumsum(0).cumsum(1)


# ---------------------------------------------------------------------------
# Caja de texto y colisión
# ---------------------------------------------------------------------------

_PUNTO_MEDIO = "·"  # MARCA_LIGADA


def _caja(
    texto: str,
    x_centro: float,
    base: float,
    tam: float,
    fuente: pymupdf.Font,
) -> tuple[pymupdf.Rect, float, float]:
    """Devuelve ``(rect, x_insertar, tam_efectivo)`` para el texto."""
    from nombres import MARCA_LIGADA as _ML
    if texto == _ML:
        tam_ef = tam * 1.8
        w = fuente.text_length(texto, fontsize=tam_ef)
        x = x_centro - w / 2
        return (
            pymupdf.Rect(x + w * 0.3, base - tam_ef * 0.38,
                         x + w * 0.7, base - tam_ef * 0.2),
            x,
            tam_ef,
        )
    w = fuente.text_length(texto, fontsize=tam)
    x = x_centro - w / 2
    return (
        pymupdf.Rect(x, base - tam * 0.70, x + w, base + tam * 0.05),
        x,
        tam,
    )


def _choca_con_colocadas(
    r: pymupdf.Rect,
    colocadas: list[pymupdf.Rect],
) -> bool:
    x0 = r.x0 - MARGEN_NOMBRES_X
    y0 = r.y0 - MARGEN_NOMBRES_Y
    x1 = r.x1 + MARGEN_NOMBRES_X
    y1 = r.y1 + MARGEN_NOMBRES_Y
    return any(
        x0 < c.x1 and c.x0 < x1 and y0 < c.y1 and c.y0 < y1
        for c in colocadas[-30:]
    )


# ---------------------------------------------------------------------------
# Colocación en una página
# ---------------------------------------------------------------------------

def _colocar_en_pagina(
    page: pymupdf.Page,
    pents: list[Pentagrama],
    notas_pagina: list[NotaColocada],
    fuente: pymupdf.Font,
) -> None:
    """Calcula las posiciones (x, base, tam, sin_hueco) para cada nota de la página.

    Modifica las notas in-place. No dibuja en el PDF.
    Las notas con fija=True conservan su posición y se registran como ocupadas
    para que las demás las eviten.
    """
    from nombres import MARCA_LIGADA as _ML

    tinta = _Tinta(page)
    prioritaria = _Prioritaria(page)
    colocadas: list[pymupdf.Rect] = []

    # Primer paso: registrar notas fijas en la lista de zonas ocupadas
    for nota in notas_pagina:
        if not nota.fija or nota.x is None or nota.base is None or nota.tam is None:
            continue
        if not nota.texto:
            continue
        if nota.texto == _ML:
            tam_ef = nota.tam * 1.8
            w = fuente.text_length(nota.texto, fontsize=tam_ef)
            r = pymupdf.Rect(
                nota.x + w * 0.3, nota.base - tam_ef * 0.38,
                nota.x + w * 0.7, nota.base - tam_ef * 0.2,
            )
        else:
            w = fuente.text_length(nota.texto, fontsize=nota.tam)
            r = pymupdf.Rect(
                nota.x, nota.base - nota.tam * 0.70,
                nota.x + w, nota.base + nota.tam * 0.05,
            )
        colocadas.append(r)

    # Segundo paso: colocar notas no fijas
    for nota in notas_pagina:
        if nota.texto is None:
            continue
        if nota.fija:
            continue   # ya registrada; posición preservada
        pent = pents[nota.linea - 1]
        e = pent.espacio
        siguiente = next(
            (q.arriba for q in pents
             if q.pagina == pent.pagina and q.arriba > pent.abajo + 1),
            page.rect.height - 8,
        )
        hueco = siguiente - pent.abajo
        preferida = pent.abajo + POS_PREFERIDA_ESPACIOS * e + TAM_PREFERIDO * 0.70
        base_min = pent.abajo + 0.3 * e + TAMANOS[-1][0] * 0.70
        base_max = pent.abajo + 0.80 * hueco

        # Lista de posiciones candidatas, ordenadas por coste
        bases = [
            base_min + 0.5 * k
            for k in range(int((base_max - base_min) / 0.5) + 1)
        ]

        def coste_base(b: float) -> float:
            diff = b - preferida
            return diff * COSTE_ARRIBA if diff < 0 else diff * COSTE_ABAJO

        bases.sort(key=coste_base)

        xc = (nota.cabeza[0] + nota.cabeza[2]) / 2.0
        mejor: Optional[tuple] = None

        for tam0, pen_t in TAMANOS:
            if mejor is not None and mejor[0] <= pen_t:
                break
            margen = MARGEN_TINTA if tam0 > 7 else MARGEN_TINTA_PEQUENO
            for dx, pen_x in DESPLAZAMIENTOS:
                if mejor is not None and mejor[0] <= pen_t + pen_x:
                    continue
                for base in bases:
                    coste = coste_base(base) + pen_t + pen_x
                    if mejor is not None and coste >= mejor[0]:
                        break
                    r, x, tam_ef = _caja(nota.texto, xc + dx, base, tam0, fuente)
                    if tinta.pixeles(r, margen) == 0 and not _choca_con_colocadas(r, colocadas):
                        mejor = (coste, base, r, x, tam_ef)
                        break

        if mejor is None:
            # Sin hueco libre: minimizar impacto, priorizando no tapar cosas prioritarias
            cands = []
            extra_bases = [base_max + 0.5 * k for k in range(1, 12)]
            for base in bases + extra_bases:
                for dx, _ in DESPLAZAMIENTOS:
                    r, x, tam_ef = _caja(
                        nota.texto, xc + dx, base, TAMANOS[-1][0], fuente
                    )
                    pen_prio = PESO_PRIORITARIO * prioritaria.pixeles(r, 0.4)
                    pen_tinta = tinta.pixeles(r, 0)
                    pen_choque = 1000.0 if _choca_con_colocadas(r, colocadas) else 0.0
                    cands.append((pen_prio + pen_tinta + pen_choque, abs(base - preferida), base, r, x, tam_ef))
            _, _, base, r, x, tam_ef = min(cands, key=lambda c: (c[0], c[1]))
            mejor = (None, base, r, x, tam_ef)
            nota.sin_hueco = True

        _, base, r, x, tam_ef = mejor
        nota.x = x
        nota.base = base
        nota.tam = tam_ef
        colocadas.append(r)


# ---------------------------------------------------------------------------
# Funciones de la API pública
# ---------------------------------------------------------------------------

SILENCIOS_CLASICOS = set("Œ‰≈Ó∑®")            # negra, corchea, semicorchea, blanca, compases, fusa
SILENCIOS_SMUFL = range(0xE4E0, 0xE4F0)


def _cabeza_anterior(heads: list[Cabeza], i: int) -> Optional[int]:
    """Índice de la cabeza anterior en el mismo pentagrama (saltando las del mismo acorde)."""
    h = heads[i]
    for k in range(i - 1, -1, -1):
        if heads[k].pent != h.pent:
            return None
        if heads[k].x < h.x - 1.0:
            return k
    return None


def _hay_silencio_entre(
    chars: list[tuple[int, str, float, float]], pent: Pentagrama, x0: float, x1: float
) -> bool:
    """True si hay un silencio dibujado en el pentagrama entre las x indicadas."""
    margen = 2 * pent.espacio
    for codepoint, fuente, ox, oy in chars:
        if not (x0 < ox < x1 and pent.arriba - margen <= oy <= pent.abajo + margen):
            continue
        if codepoint in SILENCIOS_SMUFL:
            return True
        if _es_fuente_musica_clasica(fuente) and chr(codepoint) in SILENCIOS_CLASICOS:
            return True
    return False


def _pitch_por_paso(elemento, paso: int):
    """Pitch de la nota de ``elemento`` (nota o acorde) que está en ese paso del pentagrama."""
    from music21 import clef as m21clef

    cl = elemento.getContextByClass(m21clef.Clef) or m21clef.BassClef()
    for p in elemento.pitches:
        if p.diatonicNoteNum - cl.lowestLine == paso:
            return p
    return None


def _nombre_por_paso(elemento, paso: int) -> Optional[str]:
    """Nombre de la nota de ``elemento`` (nota o acorde) que está en ese paso del pentagrama."""
    from nombres import nombre_nota

    p = _pitch_por_paso(elemento, paso)
    return nombre_nota(p) if p is not None else None


def analizar(pdf: Path, partitura) -> Analisis:
    """Detecta pentagramas y cabezas, alinea con Audiveris e infiere nombres.

    No realiza colocación visual ni escribe ningún PDF.
    Devuelve un :class:`Analisis` listo para :func:`colocar_nombres`.
    """
    from nombres import describir_cambios, MARCA_LIGADA

    pdf = Path(pdf)
    doc = pymupdf.open(str(pdf))

    # Paso 1: detectar pentagramas y cabezas
    pents: list[Pentagrama] = []
    heads: list[Cabeza] = []
    chars: dict[int, list] = {}
    paginas: list[tuple[float, float]] = []

    for num, page in enumerate(doc):
        paginas.append((page.rect.width, page.rect.height))
        ps = detectar_pentagramas(page, num)
        hs = detectar_cabezas(page, ps)
        for h in hs:
            h.pent += len(pents)
        pents += ps
        heads += hs
        chars[num] = _extraer_chars_pagina(page)

    if not heads:
        doc.close()
        raise SinCabezasError(
            "No se detectaron cabezas de nota en el PDF "
            "(¿PDF escaneado o fuente musical no reconocida?)."
        )

    # Paso 2: notas Audiveris
    sistemas = _notas_omr_con_ref(partitura)

    # Paso 3: alineación por sistema o global
    if len(sistemas) == len(pents):
        grupos = [
            ([i for i, h in enumerate(heads) if h.pent == k], sistemas[k])
            for k in range(len(pents))
        ]
    else:
        print(
            f"Aviso: {len(pents)} pentagramas en el PDF "
            f"y {len(sistemas)} sistemas en Audiveris; alineación global."
        )
        grupos = [(list(range(len(heads))), [x for s in sistemas for x in s])]

    textos: list[Optional[str]] = [None] * len(heads)
    estados: list[str] = ["ok"] * len(heads)
    motivos: list[str] = [""] * len(heads)
    ref: list[Optional[object]] = [None] * len(heads)

    for idx, omr in grupos:
        pares = _alinear(
            [heads[i].paso for i in idx],
            [x[0] for x in omr],
        )
        for i_loc, j in pares:
            hi = idx[i_loc]
            if j is not None:
                textos[hi] = omr[j][1]
                ref[hi] = omr[j][2]

    # Paso 4: cross-check de accidentales en notas ya emparejadas
    for i, h in enumerate(heads):
        if textos[i] is None or ref[i] is None:
            continue
        num_pagina = pents[h.pent].pagina
        alt_dibujada = _alteracion_impresa(chars[num_pagina], h, pents[h.pent])
        if alt_dibujada is None:
            continue
        # En un acorde, la nota de esta cabeza es la que está a su altura
        omr_pitch = _pitch_por_paso(ref[i], h.paso)
        if omr_pitch is None:
            continue
        omr_alter = int(round(omr_pitch.alter)) if omr_pitch.accidental is not None else 0
        if alt_dibujada != omr_alter:
            from music21 import pitch as m21pitch
            from nombres import nombre_nota
            p = m21pitch.Pitch()
            p.step = omr_pitch.step
            p.octave = omr_pitch.octave
            if alt_dibujada != 0:
                p.accidental = m21pitch.Accidental(alt_dibujada)
            textos[i] = nombre_nota(p)
            estados[i] = "dudosa"
            motivos[i] = "alteración distinta"

    # Paso 4b: una ligadura de unión no puede saltar un silencio dibujado en el PDF
    # (Audiveris a veces se salta el silencio y toma la ligadura de expresión por una de unión)
    for i, h in enumerate(heads):
        if textos[i] != MARCA_LIGADA or ref[i] is None:
            continue
        anterior = _cabeza_anterior(heads, i)
        if anterior is None:
            continue
        pent = pents[h.pent]
        if _hay_silencio_entre(chars[pent.pagina], pent, heads[anterior].x, h.x):
            nombre = _nombre_por_paso(ref[i], h.paso)
            if nombre is not None:
                textos[i] = nombre

    # Paso 5: detectar armadura PDF y comparar con Audiveris
    arm_pdf = _detectar_armadura_por_sistema(doc, pents, heads, chars)
    arm_omr = _armadura_omr_por_sistema(partitura, pents)
    cambios_arm_pdf = _cambios_armadura_por_sistema(doc, pents, heads, chars)

    avisos: list[str] = []
    arm_pdf_efectiva_por_pent: dict[int, int] = {}
    for k, (arm_p, arm_o) in enumerate(zip(arm_pdf, arm_omr)):
        arm_pdf_efectiva_por_pent[k] = arm_p
        if arm_p != arm_o:
            def _desc(v: int) -> str:
                if v == 0:
                    return "sin alteraciones"
                n = abs(v)
                return f"{n} {'bemol' if n == 1 else 'bemoles'}" if v < 0 else f"{n} {'sostenido' if n == 1 else 'sostenidos'}"
            avisos.append(
                f"Línea {k + 1}: el PDF tiene armadura de {_desc(arm_p)} "
                f"y Audiveris ha leído {_desc(arm_o)}"
            )
            # Marcar notas de esta línea como dudosas si el step está afectado
            _marcar_dudosas_por_armadura(k, heads, textos, estados, motivos, arm_p, arm_o)

    # Propagar cambios mid-línea a los sistemas siguientes
    arm_vigente = 0
    for k in range(len(pents)):
        arm_vigente = arm_pdf[k]
        if k in cambios_arm_pdf:
            for x_dbl, nuevo_arm in cambios_arm_pdf[k]:
                arm_vigente = nuevo_arm
        # Para el sistema siguiente al cambio, actualizar
        # (ya incluido en arm_pdf del sistema siguiente si arranca con esa armadura)

    # Paso 6: inferir nombres para cabezas sin pareja
    for i, h in enumerate(heads):
        if textos[i] is not None:
            continue
        num_pagina = pents[h.pent].pagina
        vecinas = sorted(
            (abs(k - i), k)
            for k in range(len(heads))
            if ref[k] is not None and heads[k].pent == h.pent
        )
        if not vecinas:
            textos[i] = "?"
            estados[i] = "dudosa"
            motivos[i] = "no se pudo inferir"
        else:
            nombre_inf = _inferir_nombre(
                h, ref[vecinas[0][1]], chars[num_pagina], pents[h.pent]
            )
            textos[i] = nombre_inf
            estados[i] = "deducida"
            motivos[i] = "Audiveris no la leyó"

    doc.close()

    # Paso 7: cambios de clave/armadura desde Audiveris
    cambios_clave = describir_cambios(partitura)

    # Paso 8: construir lista de NotaColocada
    notas_colocadas: list[NotaColocada] = []
    for i, h in enumerate(heads):
        pent = pents[h.pent]
        compas_nota: Optional[int] = None
        if ref[i] is not None:
            compas_nota = _numero_compas(ref[i])
        elif estados[i] == "deducida":
            # Buscar vecina para obtener compás
            vecinas = sorted(
                (abs(k - i), k)
                for k in range(len(heads))
                if ref[k] is not None and heads[k].pent == h.pent
            )
            if vecinas:
                compas_nota = _numero_compas(ref[vecinas[0][1]])

        notas_colocadas.append(NotaColocada(
            id=i,
            pagina=pent.pagina,
            linea=h.pent + 1,
            compas=compas_nota,
            cabeza=h.bbox,
            texto=textos[i] or "?",
            estado=estados[i],
            motivo=motivos[i],
        ))

    # Paso 8b: detectar acordes por geometría del PDF
    _detectar_acordes(notas_colocadas, heads)

    # Avisos de armadura (desde cambios mid-línea)
    for k, cambios in cambios_arm_pdf.items():
        for x_dbl, nuevo_arm in cambios:
            def _desc2(v: int) -> str:
                if v == 0:
                    return "sin alteraciones"
                n = abs(v)
                return f"{n} {'bemol' if n == 1 else 'bemoles'}" if v < 0 else f"{n} sostenidos"
            avisos.append(f"Línea {k + 1}: cambio de armadura a {_desc2(nuevo_arm)} (mid-línea)")

    return Analisis(
        pdf=pdf,
        paginas=paginas,
        notas=notas_colocadas,
        cambios=cambios_clave,
        avisos=avisos,
        _pentagramas=pents,
    )


def _detectar_acordes(notas: list[NotaColocada], heads: list[Cabeza]) -> None:
    """Detecta acordes por geometría del PDF usando criterio no transitivo.

    Dos criterios de par (con ancho medio = (w1+w2)/2):
    (a) mismo-tallo:       |Δxc| ≤ 0.35 × ancho_medio
    (b) segunda-desplazada: 0.75 × ancho_medio ≤ |Δxc| ≤ 1.05 × ancho_medio
                            Y |Δpaso| == 1

    Un acorde = «columna» (heads que cumplen (a) respecto al anchor izquierdo)
    más las «segundas» directamente adyacentes a la columna por criterio (b).
    Sin encadenamiento transitivo: las segundas no expanden la columna.
    Modifica ``notas`` in-place.
    """
    from collections import defaultdict

    # Agrupar índices por linea (pentagrama)
    por_linea: dict[int, list[int]] = defaultdict(list)
    for i, nota in enumerate(notas):
        por_linea[nota.linea].append(i)

    siguiente_id_acorde = 0
    for idx_linea in por_linea.values():
        # Ordenar por centro x de la cabeza
        idx_linea.sort(key=lambda i: (notas[i].cabeza[0] + notas[i].cabeza[2]) / 2.0)
        asignado: set[int] = set()

        for anchor_i in idx_linea:
            if anchor_i in asignado:
                continue
            anchor_xc = (notas[anchor_i].cabeza[0] + notas[anchor_i].cabeza[2]) / 2.0
            anchor_w  = notas[anchor_i].cabeza[2] - notas[anchor_i].cabeza[0]

            # Paso 1: columna — todos los heads no asignados dentro de 0.35×ancho_medio
            columna = [anchor_i]
            for other_i in idx_linea:
                if other_i == anchor_i or other_i in asignado:
                    continue
                other_xc = (notas[other_i].cabeza[0] + notas[other_i].cabeza[2]) / 2.0
                other_w  = notas[other_i].cabeza[2] - notas[other_i].cabeza[0]
                w_medio  = (anchor_w + other_w) / 2.0
                if abs(other_xc - anchor_xc) <= 0.35 * w_medio:
                    columna.append(other_i)

            # Paso 2: segundas desplazadas — criterio (b) respecto a cualquier miembro
            # de la columna; sin propagar a partir de ellas
            segundas: list[int] = []
            for other_i in idx_linea:
                if other_i in asignado or other_i in columna:
                    continue
                other_xc = (notas[other_i].cabeza[0] + notas[other_i].cabeza[2]) / 2.0
                other_w  = notas[other_i].cabeza[2] - notas[other_i].cabeza[0]
                for col_i in columna:
                    col_xc  = (notas[col_i].cabeza[0] + notas[col_i].cabeza[2]) / 2.0
                    col_w   = notas[col_i].cabeza[2] - notas[col_i].cabeza[0]
                    w_medio = (other_w + col_w) / 2.0
                    delta_x    = abs(other_xc - col_xc)
                    delta_paso = abs(heads[other_i].paso - heads[col_i].paso)
                    if 0.75 * w_medio <= delta_x <= 1.05 * w_medio and delta_paso == 1:
                        segundas.append(other_i)
                        break

            acorde = columna + segundas
            if len(acorde) >= 2:
                # Ordenar de agudo a grave (menor y = más agudo)
                acorde.sort(key=lambda i: notas[i].cabeza[1])
                id_acorde = siguiente_id_acorde
                siguiente_id_acorde += 1
                for i in acorde:
                    notas[i].acorde = id_acorde
                    # Marcar como dudosa solo si no hay ya un motivo más informativo
                    if notas[i].estado == "ok":
                        notas[i].estado = "dudosa"
                        notas[i].motivo = "Acorde: comprueba sus notas"
                    elif notas[i].estado not in ("deducida", "dudosa"):
                        notas[i].estado = "dudosa"
                        notas[i].motivo = "Acorde: comprueba sus notas"
                asignado.update(acorde)


def _marcar_dudosas_por_armadura(
    k: int,
    heads: list[Cabeza],
    textos: list[Optional[str]],
    estados: list[str],
    motivos: list[str],
    arm_pdf: int,
    arm_omr: int,
) -> None:
    """Marca como dudosas las notas de la línea k cuyo step está afectado por la diferencia de armadura."""
    from music21 import key as m21key

    ks_pdf = m21key.KeySignature(arm_pdf) if arm_pdf != 0 else None
    ks_omr = m21key.KeySignature(arm_omr) if arm_omr != 0 else None

    pasos_afectados_pdf = set()
    pasos_afectados_omr = set()
    if ks_pdf:
        for p in ks_pdf.alteredPitches:
            pasos_afectados_pdf.add(p.step)
    if ks_omr:
        for p in ks_omr.alteredPitches:
            pasos_afectados_omr.add(p.step)

    pasos_afectados = pasos_afectados_pdf.symmetric_difference(pasos_afectados_omr)
    if not pasos_afectados:
        return

    for i, h in enumerate(heads):
        if h.pent != k:
            continue
        if textos[i] is None:
            continue
        if estados[i] in ("deducida",):
            continue
        # Comprobar si el texto de la nota tiene el step afectado
        t = textos[i] or ""
        # Nombres: Do, Re, Mi, Fa, Sol, La, Si
        nombres_steps = {"Do": "C", "Re": "D", "Mi": "E", "Fa": "F",
                         "Sol": "G", "La": "A", "Si": "B"}
        for nom, step in nombres_steps.items():
            if t.startswith(nom) and step in pasos_afectados:
                if estados[i] == "ok":
                    estados[i] = "dudosa"
                    motivos[i] = "armadura distinta en la línea"
                break


def colocar_nombres(analisis: Analisis) -> None:
    """Calcula la posición (x, base, tam, sin_hueco) para cada nota del análisis.

    Modifica ``analisis.notas`` in-place.
    Puede llamarse varias veces (por ejemplo tras correcciones del usuario).
    """
    doc = pymupdf.open(str(analisis.pdf))
    pents = analisis._pentagramas
    fuente = pymupdf.Font(FUENTE_NOMBRE)

    # Resetear estado de colocación anterior (solo notas NO fijas)
    for nota in analisis.notas:
        if not nota.fija:
            nota.x = None
            nota.base = None
            nota.tam = None
            nota.sin_hueco = False

    for num, page in enumerate(doc):
        notas_pag = [n for n in analisis.notas if n.pagina == num]
        # Ordenar igual que las cabezas: por línea, x, y
        notas_pag.sort(key=lambda n: (n.linea, n.cabeza[0]))
        _colocar_en_pagina(page, pents, notas_pag, fuente)

    doc.close()


def escribir_pdf(
    analisis: Analisis,
    salida: Path,
    color_dudosas: bool = True,
) -> None:
    """Escribe el PDF con los nombres sobreimpresos.

    Requiere haber llamado antes a :func:`colocar_nombres`.
    """
    salida = Path(salida)
    doc = pymupdf.open(str(analisis.pdf))
    fuente = pymupdf.Font(FUENTE_NOMBRE)

    for num, page in enumerate(doc):
        notas_pag = [n for n in analisis.notas if n.pagina == num]
        notas_pag.sort(key=lambda n: (n.linea, n.cabeza[0]))
        for nota in notas_pag:
            if nota.x is None or nota.base is None or nota.tam is None:
                continue
            if color_dudosas and nota.estado in ("deducida", "dudosa"):
                color = COLOR_DEDUCIDA
            else:
                color = COLOR_NORMAL
            page.insert_text(
                (nota.x, nota.base),
                nota.texto,
                fontsize=nota.tam,
                fontname=FUENTE_NOMBRE,
                color=color,
            )

    doc.save(str(salida), garbage=3, deflate=True)
    doc.close()


def superponer_nombres(
    pdf_original: Path,
    partitura,
    pdf_salida: Path,
    color_dudosas: bool = True,
) -> Analisis:
    """Atajo para CLI: analiza, coloca y escribe en una sola llamada.

    Devuelve el :class:`Analisis` para inspección o uso posterior.
    """
    pdf_original = Path(pdf_original)
    pdf_salida = Path(pdf_salida)

    analisis = analizar(pdf_original, partitura)
    colocar_nombres(analisis)
    escribir_pdf(analisis, pdf_salida, color_dudosas=color_dudosas)
    return analisis
