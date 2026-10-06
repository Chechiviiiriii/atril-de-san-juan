"""CLI principal de pdf2notas: convierte partituras PDF en PDF con nombres de notas."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Añadir la raíz del proyecto al path para poder importar atril.*
_RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
if str(_RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROYECTO))

# Reconfigurar stdout para soportar caracteres UTF-8 en Windows (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _importar_nombres():
    """Importa atril.nombres; da error claro si no está disponible."""
    try:
        import atril.nombres as nombres  # type: ignore[import]
        return nombres
    except ImportError:
        print(
            "Error: no se encontró 'atril.nombres'. "
            "Ejecuta desde la raíz del proyecto.",
            file=sys.stderr,
        )
        raise


def poner_nombres(
    entrada_xml: Path,
    salida_xml: Path,
    titulo: str,
    partitura: object = None,
) -> object:
    """Parsea la partitura, limpia metadatos, añade nombres y escribe el MusicXML.

    Args:
        entrada_xml: Archivo MusicXML o MXL de entrada.
        salida_xml: Ruta donde se escribirá el MusicXML con nombres.
        titulo: Título a usar si la partitura no tiene uno propio.

    Returns:
        Objeto ``Resumen`` devuelto por ``nombres.anotar_partitura``.
    """
    import music21  # type: ignore[import]

    nombres_mod = _importar_nombres()

    if partitura is None:
        partitura = music21.converter.parse(str(entrada_xml))

    # Limpiar metadatos
    if partitura.metadata is None:
        partitura.metadata = music21.metadata.Metadata()

    titulo_actual = partitura.metadata.title or ""
    # Poner título solo si la partitura no tiene uno propio (o es el nombre del archivo)
    if not titulo_actual or titulo_actual in {entrada_xml.stem, str(entrada_xml)}:
        partitura.metadata.title = titulo

    # Quitar el compositor artificial "Music21"
    if partitura.metadata.composer == "Music21":
        partitura.metadata.composer = None

    # Limpiar nombre de parte si es genérico
    for parte in partitura.parts:
        if getattr(parte, "partName", None) in ("Voice", "", None):
            parte.partName = ""

    # Añadir nombres de notas como letras
    resumen = nombres_mod.anotar_partitura(partitura)

    # Escribir MusicXML de salida
    partitura.write("musicxml", fp=str(salida_xml))

    # music21 siempre añade "Music21" como compositor al serializar; eliminarlo del XML
    _limpiar_compositor_xml(salida_xml)

    return resumen


def _limpiar_compositor_xml(ruta_xml: Path) -> None:
    """Elimina el compositor 'Music21' que music21 añade automáticamente al serializar.

    Lee el archivo XML generado y sustituye cualquier elemento
    ``<creator type="composer">Music21</creator>`` por uno vacío.
    """
    import re as _re

    texto = ruta_xml.read_text(encoding="utf-8")
    texto_limpio = _re.sub(
        r'(<creator[^>]*type=["\']composer["\'][^>]*>)\s*Music21\s*(</creator>)',
        r'\1\2',
        texto,
    )
    if texto_limpio != texto:
        ruta_xml.write_text(texto_limpio, encoding="utf-8")


def _nombre_salida(pdf: Path) -> Path:
    """Devuelve la ruta de salida predeterminada: ``<stem>_notas.pdf``."""
    return pdf.with_name(pdf.stem + "_notas.pdf")


def _imprimir_resumen(resumen: object) -> None:
    """Imprime el resumen de nombres en la consola."""
    notas = getattr(resumen, "notas_nombradas", 0)
    # Tolerancia para ambas versiones de la API
    ligadas = (
        getattr(resumen, "ligadas_marcadas", None)
        or getattr(resumen, "ligadas_omitidas", 0)
    )
    cambios = getattr(resumen, "cambios", []) or []
    avisos = getattr(resumen, "avisos", []) or []

    # Primero: clave, armadura y cambios detectados (lo más útil para el usuario)
    for linea in cambios:
        print(linea)

    print(f"Notas nombradas: {notas} ({ligadas} ligadas marcadas con ·)")
    for aviso in avisos:
        print(f"⚠ {aviso}")


def _verificar_e_imprimir(pdf: Path, partitura: object, args: "argparse.Namespace") -> None:
    """Ejecuta la verificación de cabezas y muestra el resultado.

    Si hay error en la verificación, lo muestra como aviso pero no interrumpe
    el proceso.

    Args:
        pdf: PDF original (vectorial).
        partitura: Partitura ya parseada.
        args: Argumentos de la línea de comandos (para comprobar --revisar).
    """
    try:
        from atril.verificacion import verificar  # type: ignore[import]
    except ImportError:
        print("Verificación omitida: módulo 'verificacion' no disponible.")
        return

    try:
        resultado = verificar(pdf, partitura)
    except Exception as exc:
        print(f"⚠ Error en la verificación: {exc}")
        return

    if not resultado.comprobado:
        print(
            "Verificación omitida: el PDF no es vectorial o usa una fuente musical desconocida."
        )
        return

    print(
        f"Verificación: {resultado.total_pdf} notas en el PDF, "
        f"{resultado.total_omr} leídas por Audiveris."
    )
    for aviso in resultado.avisos:
        print(f"⚠ {aviso}")

    if resultado.avisos and not getattr(args, "revisar", False):
        print("  → Repite con --revisar para corregir manualmente.")


def _imprimir_resumen_superposicion(analisis: object, config: dict) -> None:
    """Imprime el resumen de la superposición de nombres en la consola."""
    notas = analisis.notas  # type: ignore[union-attr]
    n_total = len(notas)
    deducidas = [n for n in notas if n.estado in ("deducida", "dudosa")]
    n_audiveris = n_total - len(deducidas)

    print(f"Nombres: {n_audiveris} de Audiveris, {len(deducidas)} deducidos del PDF (en rojo, revísalos)")

    for n in deducidas:
        compas_str = f"compás ~{n.compas}" if n.compas else "compás desconocido"
        print(f"  línea {n.linea}, {compas_str}: {n.texto}  [{n.motivo}]")

    sin_hueco = [n for n in notas if n.sin_hueco]
    for n in sin_hueco:
        print(f"⚠ Sin hueco libre para '{n.texto}' en la línea {n.linea}")

    for aviso in getattr(analisis, "avisos", []):
        print(f"⚠ {aviso}")


def _unir_pdfs(pdfs: list[Path], salida: Path) -> None:
    """Une varios PDFs en uno con pypdf.

    Args:
        pdfs: Lista de PDFs a unir, en orden.
        salida: Ruta del PDF resultante.

    Raises:
        SystemExit: Si pypdf no está instalado.
    """
    try:
        from pypdf import PdfWriter  # type: ignore[import]
    except ImportError:
        print(
            "Error: se necesita pypdf para unir varios movimientos. "
            "Instálalo con: pip install pypdf",
            file=sys.stderr,
        )
        raise

    escritor = PdfWriter()
    for pdf in pdfs:
        escritor.append(str(pdf))
    with salida.open("wb") as f:
        escritor.write(f)


def _procesar_un_pdf_redibujar(
    pdf: Path,
    salida: Path,
    args: argparse.Namespace,
    config: dict,
    audiveris: Path,
    musescore: Path,
    carpeta_trabajo: Path,
    partitura_parseada: object = None,
    mxl_entrada: "Path | None" = None,
) -> None:
    """Modo clásico: OMR → nombres → renderizado con MuseScore.

    Args:
        pdf: Archivo PDF de entrada.
        salida: Ruta del PDF de salida.
        args: Argumentos de línea de comandos.
        config: Configuración cargada.
        audiveris: Ruta al ejecutable de Audiveris.
        musescore: Ruta al ejecutable de MuseScore.
        carpeta_trabajo: Directorio de intermedios.
        partitura_parseada: Partitura ya parseada (opcional).
        mxl_entrada: MXL ya generado (omite el paso OMR si se proporciona).
    """
    from atril.omr import pdf_a_musicxml
    from atril.render import musicxml_a_pdf, revisar_en_musescore

    timeout_omr = config.get("opciones", {}).get("timeout_omr", 900)
    timeout_render = config.get("opciones", {}).get("timeout_render", 300)

    if mxl_entrada is None:
        print("Reconociendo partitura con Audiveris… (puede tardar un minuto)")
        archivos_mxl = pdf_a_musicxml(pdf, carpeta_trabajo, audiveris, timeout_omr)
    else:
        archivos_mxl = [mxl_entrada]

    pdfs_movimientos: list[Path] = []

    for i, mxl in enumerate(archivos_mxl):
        sufijo = f"_mvt{i + 1}" if len(archivos_mxl) > 1 else ""

        if args.revisar:
            mxl = revisar_en_musescore(mxl, musescore, timeout_render)

        if partitura_parseada is None and len(archivos_mxl) == 1:
            try:
                import music21 as _m21  # type: ignore[import]
                partitura_parseada = _m21.converter.parse(str(mxl))
                _verificar_e_imprimir(pdf, partitura_parseada, args)
            except Exception as exc:
                print(f"⚠ Error en la verificación: {exc}")

        xml_con_nombres = carpeta_trabajo / f"{pdf.stem}{sufijo}_nombres.musicxml"
        resumen = poner_nombres(mxl, xml_con_nombres, titulo=pdf.stem, partitura=partitura_parseada)
        _imprimir_resumen(resumen)

        pdf_mov = carpeta_trabajo / f"{pdf.stem}{sufijo}_notas.pdf"
        musicxml_a_pdf(xml_con_nombres, pdf_mov, musescore, timeout_render)
        pdfs_movimientos.append(pdf_mov)

    if len(pdfs_movimientos) == 1:
        import shutil as _shutil
        _shutil.copy2(str(pdfs_movimientos[0]), str(salida))
    else:
        _unir_pdfs(pdfs_movimientos, salida)


def _esta_bloqueado(ruta: Path) -> bool:
    """True si el archivo existe y otro programa lo tiene abierto (p. ej. un visor de PDF)."""
    if not ruta.exists():
        return False
    try:
        with ruta.open("ab"):
            return False
    except OSError:
        return True


def _salida_disponible(salida: Path) -> Path:
    """Devuelve ``salida`` o, si está abierta en otro programa, ``<nombre> (2).pdf``, ``(3)``…"""
    if not _esta_bloqueado(salida):
        return salida
    n = 2
    while True:
        alternativa = salida.with_name(f"{salida.stem} ({n}){salida.suffix}")
        if not _esta_bloqueado(alternativa):
            print(
                f"⚠ '{salida.name}' está abierto en otro programa; "
                f"se guardará como '{alternativa.name}'."
            )
            return alternativa
        n += 1


def _procesar_un_pdf(
    pdf: Path,
    salida: Path,
    args: argparse.Namespace,
    config: dict,
    audiveris: Path,
    musescore: "Path | None",
    carpeta_trabajo: Path,
) -> None:
    """Procesa un único PDF: OMR y superposición (o redibujado si se pide).

    Args:
        pdf: Archivo PDF de entrada.
        salida: Ruta del PDF de salida.
        args: Argumentos de la línea de comandos.
        config: Configuración cargada.
        audiveris: Ruta al ejecutable de Audiveris.
        musescore: Ruta al ejecutable de MuseScore (None si no está instalado).
        carpeta_trabajo: Directorio donde se guardan los intermedios.
    """
    from atril.omr import pdf_a_musicxml

    timeout_omr = config.get("opciones", {}).get("timeout_omr", 900)
    timeout_render = config.get("opciones", {}).get("timeout_render", 300)

    usar_redibujar = getattr(args, "redibujar", False) or getattr(args, "revisar", False)

    if usar_redibujar and musescore is None:
        from atril.render import buscar_musescore
        from atril.config import HerramientaNoEncontrada
        try:
            musescore = buscar_musescore(config)
        except HerramientaNoEncontrada as exc:
            raise RuntimeError(
                f"--redibujar/--revisar requiere MuseScore pero no se encontró: {exc}"
            ) from exc

    # Paso 1: OMR
    print("Reconociendo partitura con Audiveris… (puede tardar un minuto)")
    archivos_mxl = pdf_a_musicxml(pdf, carpeta_trabajo, audiveris, timeout_omr)

    if usar_redibujar:
        _procesar_un_pdf_redibujar(
            pdf, salida, args, config, audiveris, musescore,
            carpeta_trabajo, mxl_entrada=archivos_mxl[0] if len(archivos_mxl) == 1 else None,
        )
        return

    # Modo por defecto: superposición sobre el PDF original
    import music21 as _m21  # type: ignore[import]

    pdfs_movimientos: list[Path] = []

    for i, mxl in enumerate(archivos_mxl):
        sufijo = f"_mvt{i + 1}" if len(archivos_mxl) > 1 else ""

        # Parsear partitura
        partitura = _m21.converter.parse(str(mxl))

        # Verificación
        if len(archivos_mxl) == 1:
            _verificar_e_imprimir(pdf, partitura, args)

        # Cambios de clave/armadura
        nombres_mod = _importar_nombres()
        for linea in nombres_mod.describir_cambios(partitura):
            print(linea)

        # Superposición
        try:
            from atril.superponer import superponer_nombres, SinCabezasError  # type: ignore[import]
            color_deducidas = config.get("salida", {}).get("color_deducidas", True)
            pdf_mov = carpeta_trabajo / f"{pdf.stem}{sufijo}_notas.pdf"
            analisis = superponer_nombres(
                pdf, partitura, pdf_mov, color_dudosas=color_deducidas
            )
            _imprimir_resumen_superposicion(analisis, config)
        except Exception as exc:
            # Fallback al modo redibujar si la superposición falla
            print(
                f"⚠ Superposición no disponible ({exc}).\n"
                "  Intentando modo --redibujar como alternativa…"
            )
            if musescore is None:
                from atril.render import buscar_musescore
                from atril.config import HerramientaNoEncontrada
                try:
                    musescore = buscar_musescore(config)
                except HerramientaNoEncontrada as exc2:
                    raise RuntimeError(
                        "La superposición falló y MuseScore no está instalado. "
                        "Instala MuseScore o proporciona un PDF vectorial con fuentes musicales reconocibles."
                    ) from exc2
            _procesar_un_pdf_redibujar(
                pdf, salida, args, config, audiveris, musescore,
                carpeta_trabajo, partitura_parseada=partitura,
                mxl_entrada=mxl,
            )
            return

        pdfs_movimientos.append(pdf_mov)

    # Unir movimientos
    if len(pdfs_movimientos) == 1:
        import shutil as _shutil
        _shutil.copy2(str(pdfs_movimientos[0]), str(salida))
    else:
        _unir_pdfs(pdfs_movimientos, salida)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI.

    Args:
        argv: Lista de argumentos (omitir para usar ``sys.argv``).

    Returns:
        Código de salida: 0 si todo fue bien, 1 si hubo errores.
    """
    analizador = argparse.ArgumentParser(
        prog="pdf2notas",
        description="Convierte partituras PDF en PDF con nombres de notas.",
    )
    analizador.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        help="Archivo PDF a procesar.",
    )
    analizador.add_argument(
        "-o", "--salida",
        type=Path,
        default=None,
        help="Ruta de salida del PDF con nombres (solo con un archivo).",
    )
    analizador.add_argument(
        "--carpeta",
        type=Path,
        default=None,
        help="Procesa todos los *.pdf de la carpeta (sin --pdf).",
    )
    analizador.add_argument(
        "--revisar",
        action="store_true",
        help="Abre en MuseScore para revisión manual antes de añadir nombres.",
    )
    analizador.add_argument(
        "--redibujar",
        action="store_true",
        help="Usa el modo clásico: redibujar la partitura completa con MuseScore (requiere MuseScore instalado).",
    )
    analizador.add_argument(
        "--conservar",
        action="store_true",
        help="Guarda los archivos intermedios en <stem>_pdf2notas/ junto a la salida.",
    )

    args = analizador.parse_args(argv)

    # Validaciones básicas de argumentos
    if args.pdf is None and args.carpeta is None:
        analizador.print_help()
        return 1

    if args.salida and args.carpeta:
        print(
            "Error: --salida solo es compatible con un único archivo PDF.",
            file=sys.stderr,
        )
        return 1

    # Con --revisar, los intermedios se conservan siempre
    if args.revisar:
        args.conservar = True

    # Cargar configuración y localizar herramientas
    try:
        from atril.config import cargar_config, HerramientaNoEncontrada
        from atril.omr import buscar_audiveris

        config = cargar_config()
        audiveris = buscar_audiveris(config)
    except HerramientaNoEncontrada as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1

    # MuseScore solo es necesario en modo --redibujar / --revisar
    musescore = None
    usar_musescore = getattr(args, "redibujar", False) or getattr(args, "revisar", False)
    if usar_musescore:
        try:
            from atril.render import buscar_musescore
            from atril.config import HerramientaNoEncontrada
            musescore = buscar_musescore(config)
        except HerramientaNoEncontrada as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error de configuración: {exc}", file=sys.stderr)
            return 1

    # Determinar lista de PDFs a procesar
    if args.carpeta:
        if not args.carpeta.is_dir():
            print(
                f"Error: '{args.carpeta}' no es una carpeta válida.",
                file=sys.stderr,
            )
            return 1
        pdfs = [
            p for p in sorted(args.carpeta.glob("*.pdf"))
            if not p.name.endswith("_notas.pdf")
            and not p.name.endswith("_objetivo.pdf")
        ]
        if not pdfs:
            print(f"No se encontraron archivos PDF en '{args.carpeta}'.")
            return 0
    else:
        if not args.pdf.exists():
            print(
                f"Error: el archivo '{args.pdf}' no existe.",
                file=sys.stderr,
            )
            return 1
        if args.pdf.suffix.lower() != ".pdf":
            print(
                f"Error: '{args.pdf}' no parece un archivo PDF.",
                file=sys.stderr,
            )
            return 1
        pdfs = [args.pdf]

    correctos: list[Path] = []
    fallidos: list[tuple[Path, str]] = []

    for pdf in pdfs:
        salida = _salida_disponible(
            args.salida if (args.salida and len(pdfs) == 1)
            else _nombre_salida(pdf)
        )

        if args.conservar:
            carpeta_trabajo = salida.parent / (pdf.stem + "_pdf2notas")
            carpeta_trabajo.mkdir(parents=True, exist_ok=True)
            ctx = None
        else:
            ctx = tempfile.TemporaryDirectory()
            carpeta_trabajo = Path(ctx.name)

        try:
            _procesar_un_pdf(
                pdf, salida, args, config,
                audiveris, musescore, carpeta_trabajo,
            )
            print(f"Listo: {salida}")
            correctos.append(pdf)
        except Exception as exc:
            mensaje = str(exc)
            print(f"Error procesando '{pdf.name}': {mensaje}", file=sys.stderr)
            fallidos.append((pdf, mensaje))
        finally:
            if ctx is not None:
                try:
                    ctx.cleanup()
                except Exception:
                    pass

    # Resumen al procesar carpeta
    if args.carpeta:
        print(
            f"\nResumen: {len(correctos)} correcto(s), {len(fallidos)} fallido(s)."
        )
        for pdf_fail, msg in fallidos:
            print(f"  - {pdf_fail.name}: {msg}", file=sys.stderr)

    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
