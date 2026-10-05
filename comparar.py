"""
comparar.py — Compara los nombres de notas de dos PDFs: el generado por pdf2notas
y una referencia numerada a mano.

Uso:
    python comparar.py salida_notas.pdf referencia_numerada.pdf

El script extrae los nombres de notas (Do, Re, Mi, … con sus alteraciones) y el
marcador de ligadura "·" de ambos PDFs usando PyMuPDF, los ordena por pentagrama y x,
los alinea con difflib y muestra el porcentaje de coincidencia y las diferencias.

Tratamiento especial de "·":
    "·" frente a cualquier nombre de nota se considera coincidencia aceptable
    (la referencia pone el nombre en las notas ligadas, nosotros ponemos "·").
"""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

import pymupdf

# Patrón para nombres de nota en texto ordinario
_PAT_NOMBRE = re.compile(
    r"^(Do|Re|Mi|Fa|Sol|La|Si)(##?|bb?|#|b)?$",
    re.IGNORECASE,
)

# Patrón más flexible: nombre al inicio de una palabra
_PAT_NOMBRE_INICIO = re.compile(
    r"(Do|Re|Mi|Fa|Sol|La|Si)(##?|bb?|#|b)?",
)

MARCA_LIGADA = "·"


def _detectar_pentagramas(page: pymupdf.Page) -> list[tuple[float, float]]:
    """Detecta grupos de 5 líneas horizontales y devuelve (y_sup, y_inf) por pentagrama."""
    segs: dict[float, float] = {}
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.3:
                y = round(it[1].y, 1)
                lon = abs(it[2].x - it[1].x)
            elif it[0] == "re" and it[1].height < 1.2 and it[1].width > 20:
                y = round((it[1].y0 + it[1].y1) / 2, 1)
                lon = it[1].width
            else:
                continue
            segs[y] = segs.get(y, 0.0) + lon

    ys = sorted(y for y, lon in segs.items() if lon > page.rect.width * 0.35)
    grupos: list[list[float]] = []
    grupo: list[float] = []
    for y in ys:
        if grupo and (len(grupo) == 5 or y - grupo[-1] > 12):
            if len(grupo) == 5:
                grupos.append(grupo)
            grupo = []
        grupo.append(y)
    if len(grupo) == 5:
        grupos.append(grupo)
    return [(g[0], g[-1]) for g in grupos]


def _spans_pagina(page: pymupdf.Page) -> list[tuple[str, float, float, float]]:
    """Devuelve lista de ``(texto, x, y, ancho)`` por span de la página.

    Usa ``rawdict`` para obtener spans con caracteres individuales. Cada span
    de ``rawdict`` contiene ``chars`` con la clave ``"c"`` para el carácter.
    La reconstrucción del texto desde chars evita pérdida de información.
    """
    resultado: list[tuple[str, float, float, float]] = []
    d = page.get_text("rawdict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                chars = sp.get("chars", [])
                texto = "".join(ch.get("c", "") for ch in chars).strip()
                if not texto:
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                ox = x0
                oy = (y0 + y1) / 2.0
                ancho = max(1.0, x1 - x0)
                resultado.append((texto, ox, oy, ancho))
    return resultado


def _extraer_nombres_pagina(
    page: pymupdf.Page,
    pentagramas: list[tuple[float, float]],
    es_referencia: bool = False,
) -> list[tuple[int, float, float, str]]:
    """Extrae nombres de nota de la página.

    Devuelve lista de ``(idx_pent, x, y, nombre)`` ordenada por pentagrama y x.

    Estrategia: obtiene spans del PDF y para cada span usa ``findall`` para
    extraer TODOS los nombres de nota presentes (maneja spans que fusionan
    varios nombres como "LaSiDo" → ["La", "Si", "Do"]).
    También detecta "·" como marca de ligadura.
    """
    if not pentagramas:
        return []

    mids = [(p[0] + p[1]) / 2.0 for p in pentagramas]
    resultados: list[tuple[int, float, float, str]] = []

    for texto, ox, oy, ancho in _spans_pagina(page):
        if mids:
            idx = min(range(len(mids)), key=lambda k: abs(mids[k] - oy))
        else:
            continue

        # Marca de ligadura "·"
        if texto == MARCA_LIGADA or texto == chr(0x00B7):
            resultados.append((idx, ox, oy, MARCA_LIGADA))
            continue

        # Extraer TODOS los nombres de nota presentes en el span
        # (puede haber varios si PyMuPDF fusionó spans adyacentes)
        matches = _PAT_NOMBRE_INICIO.findall(texto)
        if not matches:
            continue

        # Repartir el span uniformemente entre los nombres encontrados
        n = len(matches)
        paso = ancho / n
        for k, (base, alt_raw) in enumerate(matches):
            nombre = base.capitalize()
            alt = alt_raw.replace("♯", "#").replace("♭", "b")
            nombre_completo = nombre + alt
            x_nota = ox + k * paso
            resultados.append((idx, x_nota, oy, nombre_completo))

    # Ordenar por pentagrama y x
    resultados.sort(key=lambda t: (t[0], t[1]))
    return resultados



def extraer_nombres(
    pdf: Path,
    es_referencia: bool = False,
) -> list[str]:
    """Extrae todos los nombres de nota del PDF en orden de lectura.

    Devuelve lista de strings: "Do", "Mib", "Fa#", "·", etc.
    """
    pdf = Path(pdf)
    doc = pymupdf.open(str(pdf))
    resultado: list[str] = []

    for num, page in enumerate(doc):
        pents = _detectar_pentagramas(page)
        nombres = _extraer_nombres_pagina(page, pents, es_referencia=es_referencia)
        resultado.extend(n[3] for n in nombres)

    doc.close()
    return resultado


def _son_compatibles(a: str, b: str) -> bool:
    """True si dos nombres se consideran compatibles en la comparación.

    "·" frente a cualquier nombre se considera aceptable (ligadura marcada vs nombrada).
    """
    if a == b:
        return True
    if a == MARCA_LIGADA or b == MARCA_LIGADA:
        return True
    return False


def comparar(
    pdf_generado: Path,
    pdf_referencia: Path,
) -> dict:
    """Compara los nombres de nota de dos PDFs.

    Devuelve un diccionario con:
    - ``pct_coincidencia``: porcentaje de coincidencia estricta
    - ``pct_con_ligadas``: porcentaje con "·" tratado como coincidencia
    - ``n_generado``: número de nombres en el PDF generado
    - ``n_referencia``: número de nombres en la referencia
    - ``diferencias``: lista de strings describiendo diferencias
    - ``marcas_ligadas_ok``: número de "·" aceptados como coincidencia
    """
    generados = extraer_nombres(pdf_generado, es_referencia=False)
    referencia = extraer_nombres(pdf_referencia, es_referencia=True)

    n_gen = len(generados)
    n_ref = len(referencia)

    if n_ref == 0:
        return {
            "pct_coincidencia": 0.0,
            "pct_con_ligadas": 0.0,
            "n_generado": n_gen,
            "n_referencia": 0,
            "diferencias": ["La referencia no tiene nombres"],
            "marcas_ligadas_ok": 0,
        }

    matcher = difflib.SequenceMatcher(None, generados, referencia, autojunk=False)
    bloques = matcher.get_matching_blocks()
    iguales_estrictos = sum(b.size for b in bloques)

    # Calcular coincidencias con ligadas
    iguales_con_ligadas = 0
    marcas_ligadas_ok = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            iguales_con_ligadas += i2 - i1
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            for gi, ri in zip(range(i1, i2), range(j1, j2)):
                if _son_compatibles(generados[gi], referencia[ri]):
                    iguales_con_ligadas += 1
                    if generados[gi] == MARCA_LIGADA or referencia[ri] == MARCA_LIGADA:
                        marcas_ligadas_ok += 1

    pct = 100.0 * iguales_estrictos / n_ref
    pct_lig = 100.0 * iguales_con_ligadas / n_ref

    # Diferencias
    diffs: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        gen_parte = generados[i1:i2]
        ref_parte = referencia[j1:j2]
        diffs.append(f"{tag}: gen[{i1}:{i2}]={gen_parte} ref[{j1}:{j2}]={ref_parte}")

    return {
        "pct_coincidencia": pct,
        "pct_con_ligadas": pct_lig,
        "n_generado": n_gen,
        "n_referencia": n_ref,
        "diferencias": diffs,
        "marcas_ligadas_ok": marcas_ligadas_ok,
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la herramienta de comparación."""
    import argparse

    # Reconfigurar stdout para UTF-8 en Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    analizador = argparse.ArgumentParser(
        prog="comparar",
        description="Compara los nombres de nota de dos PDFs.",
    )
    analizador.add_argument("generado", type=Path, help="PDF generado por pdf2notas.")
    analizador.add_argument("referencia", type=Path, help="PDF de referencia numerado a mano.")
    analizador.add_argument(
        "--diffs",
        action="store_true",
        help="Mostrar lista detallada de diferencias.",
    )

    args = analizador.parse_args(argv)

    if not args.generado.exists():
        print(f"Error: '{args.generado}' no existe.", file=sys.stderr)
        return 1
    if not args.referencia.exists():
        print(f"Error: '{args.referencia}' no existe.", file=sys.stderr)
        return 1

    resultado = comparar(args.generado, args.referencia)

    print(
        f"Generado: {resultado['n_generado']} nombres | "
        f"Referencia: {resultado['n_referencia']} nombres"
    )
    print(f"Coincidencia estricta: {resultado['pct_coincidencia']:.1f}%")
    print(
        f"Coincidencia con '·' aceptado: {resultado['pct_con_ligadas']:.1f}%  "
        f"({resultado['marcas_ligadas_ok']} marcas de ligadura tratadas como coincidencia)"
    )

    if args.diffs or resultado["diferencias"]:
        print(f"\nDiferencias ({len(resultado['diferencias'])}):")
        for d in resultado["diferencias"][:50]:
            print(f"  {d}")
        if len(resultado["diferencias"]) > 50:
            print(f"  ... ({len(resultado['diferencias']) - 50} más)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
