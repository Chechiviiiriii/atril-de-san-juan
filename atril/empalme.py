"""empalme.py — Unión de múltiples PDFs de partitura en uno solo.

API pública:
    titulo_pdf(pdf) → str
    contar_paginas(pdf) → int
    unir_pdfs(pdfs, salida) → Path

CLI:
    python empalme.py a.pdf b.pdf c.pdf -o salida.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------

class PDFDaniadoError(ValueError):
    """El PDF está dañado o no se puede abrir."""


class PDFProtegidoError(ValueError):
    """El PDF está protegido con contraseña."""


# ---------------------------------------------------------------------------
# Fuentes musicales a excluir en la búsqueda de título
# ---------------------------------------------------------------------------

_PALABRAS_MUSICA: tuple[str, ...] = (
    "opus", "sibelius", "petrucci", "maestro", "engraver",
    "helsinki", "reprise", "inkpen", "jazz", "broadway", "sonata",
    "leland", "bravura", "petaluma", "sebastian", "gonville",
    "emmentaler", "november2", "smufl",
)


def _es_fuente_musical(fontname: str) -> bool:
    base = fontname.split("+", 1)[-1].lower()
    if "text" in base:
        return False
    return any(k in base for k in _PALABRAS_MUSICA)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def titulo_pdf(pdf: Path) -> str:
    """Detecta el título de la partitura en la primera página del PDF.

    Busca el span de texto con la fuente más grande que no sea de tipo musical.
    Elimina las comillas envolventes si las hay.
    Si no encuentra ningún texto adecuado, devuelve el nombre del archivo sin extensión.
    """
    pdf = Path(pdf)
    try:
        doc = _abrir_pdf(pdf)
    except Exception:
        return pdf.stem

    try:
        if doc.page_count == 0:
            return pdf.stem

        page = doc[0]
        bloques = page.get_text("dict")["blocks"]

        mejor_tam: float = 0.0
        mejor_texto: str = ""

        for bloque in bloques:
            if bloque.get("type") != 0:   # solo bloques de texto
                continue
            for linea in bloque.get("lines", []):
                for span in linea.get("spans", []):
                    fontname = span.get("font", "")
                    if _es_fuente_musical(fontname):
                        continue
                    texto = span.get("text", "").strip()
                    if not texto:
                        continue
                    tam = float(span.get("size", 0))
                    if tam > mejor_tam:
                        mejor_tam = tam
                        mejor_texto = texto

        if not mejor_texto:
            return pdf.stem

        # Eliminar comillas envolventes de varios tipos
        for par in ('""', "''", "«»", "“”", "‘’"):
            if (len(par) >= 2 and mejor_texto.startswith(par[0])
                    and mejor_texto.endswith(par[-1]) and len(mejor_texto) > 2):
                mejor_texto = mejor_texto[1:-1].strip()
                break

        return mejor_texto or pdf.stem

    finally:
        doc.close()


def contar_paginas(pdf: Path) -> int:
    """Devuelve el número de páginas del PDF."""
    pdf = Path(pdf)
    doc = _abrir_pdf(pdf)
    try:
        return doc.page_count
    finally:
        doc.close()


def unir_pdfs(pdfs: list[Path], salida: Path) -> Path:
    """Une los PDFs en el orden dado y escribe el resultado en *salida*.

    Las páginas se copian sin modificar.
    Devuelve la ruta al archivo generado.
    """
    if not pdfs:
        raise ValueError("Se necesita al menos un PDF para unir.")

    salida = Path(salida)
    doc_salida = pymupdf.open()

    try:
        for pdf in pdfs:
            doc = _abrir_pdf(Path(pdf))
            try:
                doc_salida.insert_pdf(doc)
            finally:
                doc.close()

        doc_salida.save(str(salida), garbage=3, deflate=True)
    finally:
        doc_salida.close()

    return salida


# ---------------------------------------------------------------------------
# Auxiliar interno
# ---------------------------------------------------------------------------

def _abrir_pdf(pdf: Path) -> pymupdf.Document:
    """Abre el PDF y lanza errores descriptivos si falla."""
    try:
        doc = pymupdf.open(str(pdf))
    except Exception as exc:
        raise PDFDaniadoError(
            f"No se puede abrir el PDF «{pdf.name}»: {exc}"
        ) from exc

    if doc.needs_pass:
        doc.close()
        raise PDFProtegidoError(
            f"El PDF «{pdf.name}» está protegido con contraseña."
        )

    return doc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="empalme",
        description="Une varios PDFs de partitura en uno solo.",
    )
    parser.add_argument(
        "pdfs", nargs="+", type=Path, metavar="PDF",
        help="Archivos PDF a unir (en orden).",
    )
    parser.add_argument(
        "-o", "--salida", type=Path, default=Path("salida.pdf"),
        help="Archivo de salida (por defecto: salida.pdf).",
    )
    args = parser.parse_args(argv)

    for p in args.pdfs:
        if not p.exists():
            parser.error(f"No encontrado: {p}")

    resultado = unir_pdfs(args.pdfs, args.salida)
    n = contar_paginas(resultado)
    print(f"PDF generado: {resultado}  ({n} página{'s' if n != 1 else ''})")


if __name__ == "__main__":
    main()
