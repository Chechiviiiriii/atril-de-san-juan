"""Verificación de cabezas de nota: compara el PDF original con las notas leídas por Audiveris.

La detección de pentagramas y cabezas usa PyMuPDF a través de ``superponer.py``
(implementación única compartida).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # music21 solo se importa en tiempo de ejecución


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------

@dataclass
class Verificacion:
    """Resultado de la comparación entre cabezas PDF y notas OMR."""

    total_pdf: int
    total_omr: int
    avisos: list[str] = field(default_factory=list)
    comprobado: bool = True


# ---------------------------------------------------------------------------
# Conteo de cabezas por sistema
# ---------------------------------------------------------------------------

def contar_cabezas_pdf(pdf: Path) -> list[int] | None:
    """Cuenta las cabezas de nota del PDF vectorial por sistema, de arriba a abajo.

    Usa PyMuPDF para la detección de pentagramas y cabezas (función única
    compartida con ``superponer.py``).

    Devuelve:
        Lista con el número de cabezas por sistema, en orden de lectura.
        ``None`` si el PDF no es vectorial o no se reconoce ninguna cabeza.
    """
    try:
        import pymupdf  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("pymupdf es necesario para la verificación") from exc

    from .superponer import detectar_pentagramas, detectar_cabezas  # type: ignore[import]

    resultado: list[int] = []

    with pymupdf.open(str(pdf)) as doc:
        for num, page in enumerate(doc):
            ps = detectar_pentagramas(page, num)
            if not ps:
                continue
            hs = detectar_cabezas(page, ps)
            # Contar cabezas por pentagrama local
            conteos: dict[int, int] = {}
            for h in hs:
                conteos[h.pent] = conteos.get(h.pent, 0) + 1
            for i in range(len(ps)):
                resultado.append(conteos.get(i, 0))

    if not resultado:
        return None
    if sum(resultado) == 0:
        return None
    return resultado


# ---------------------------------------------------------------------------
# Conteo de notas por sistema en el MusicXML
# ---------------------------------------------------------------------------

def _indices_sistema(parte) -> list[int]:
    """Devuelve los índices de compás donde empieza cada sistema (incluye el 0)."""
    from music21 import layout  # type: ignore[import]

    compases = list(parte.getElementsByClass('Measure'))
    inicios = [
        i for i, m in enumerate(compases)
        if m.getElementsByClass(layout.SystemLayout)
    ]
    if not inicios or inicios[0] != 0:
        inicios = [0] + inicios
    return inicios


def contar_notas_omr(partitura) -> list[int]:
    """Cuenta las notas por sistema del MusicXML de Audiveris.

    Incluye notas de acordes y notas de adorno. Cada sistema empieza en un
    compás con ``layout.SystemLayout``; el primer compás también cuenta.

    Returns:
        Lista con el número de notas por sistema.
    """
    parte = partitura.parts[0]
    compases = list(parte.getElementsByClass('Measure'))
    inicios = _indices_sistema(parte)
    limites = inicios + [len(compases)]

    resultado: list[int] = []
    for k in range(len(limites) - 1):
        tramo = compases[limites[k]:limites[k + 1]]
        n = sum(len(nota.pitches) for m in tramo for nota in m.recurse().notes)
        resultado.append(n)
    return resultado


def rango_compases_sistema(partitura) -> list[tuple[int, int]]:
    """Devuelve el número de compás inicial y final de cada sistema.

    Returns:
        Lista de ``(primer_compas, ultimo_compas)`` según la numeración del MXL.
    """
    parte = partitura.parts[0]
    compases = list(parte.getElementsByClass('Measure'))
    inicios = _indices_sistema(parte)
    limites = inicios + [len(compases)]

    rangos: list[tuple[int, int]] = []
    for k in range(len(limites) - 1):
        tramo = compases[limites[k]:limites[k + 1]]
        if tramo:
            rangos.append((tramo[0].number, tramo[-1].number))
    return rangos


# ---------------------------------------------------------------------------
# Función principal de verificación
# ---------------------------------------------------------------------------

def verificar(pdf: Path, partitura) -> Verificacion:
    """Compara las cabezas de nota del PDF con las notas leídas por Audiveris.

    Args:
        pdf: Ruta al PDF original (vectorial).
        partitura: Objeto ``music21.stream.Score`` ya parseado.

    Returns:
        Instancia de :class:`Verificacion` con el resumen y los avisos.
    """
    cabezas_pdf = contar_cabezas_pdf(pdf)
    notas_omr = contar_notas_omr(partitura)
    total_omr = sum(notas_omr)

    if cabezas_pdf is None:
        return Verificacion(
            total_pdf=0,
            total_omr=total_omr,
            avisos=[],
            comprobado=False,
        )

    total_pdf = sum(cabezas_pdf)
    avisos: list[str] = []

    n_pdf = len(cabezas_pdf)
    n_omr = len(notas_omr)

    if n_pdf != n_omr:
        avisos.append(
            f"El PDF tiene {n_pdf} {'línea' if n_pdf == 1 else 'líneas'} "
            f"y Audiveris ha leído {n_omr} {'sistema' if n_omr == 1 else 'sistemas'}; "
            f"revisa la partitura con --revisar."
        )
        return Verificacion(
            total_pdf=total_pdf,
            total_omr=total_omr,
            avisos=avisos,
            comprobado=True,
        )

    rangos = rango_compases_sistema(partitura)

    for i, (n_p, n_o) in enumerate(zip(cabezas_pdf, notas_omr)):
        if n_p == n_o:
            continue
        diff = n_p - n_o
        if 1 <= len(rangos) > i:
            c1, c2 = rangos[i]
            where = f"Línea {i + 1} (compases {c1}–{c2} según Audiveris)"
        else:
            where = f"Línea {i + 1}"
        if diff > 0:
            accion = f"falta {diff}" if diff == 1 else f"faltan {diff}"
        else:
            nd = abs(diff)
            accion = f"sobra {nd}" if nd == 1 else f"sobran {nd}"
        avisos.append(
            f"{where}: el PDF tiene {n_p} notas y Audiveris ha leído {n_o} ({accion})."
        )

    return Verificacion(
        total_pdf=total_pdf,
        total_omr=total_omr,
        avisos=avisos,
        comprobado=True,
    )
