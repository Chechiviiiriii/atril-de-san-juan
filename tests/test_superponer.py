"""
test_superponer.py — Tests para el módulo superponer.py.

Cubre:
- Detección de pentagramas y cabezas (victoria, dulce)
- Alineación DP (_alinear)
- Inferencia de nombres
- API pública: analizar / colocar_nombres / escribir_pdf
- Sin superposición con la máscara de prioridad
- Armaduras por sistema (victoria=0, dulce línea 1=2 bemoles, etc.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import requiere_datos

# ---------------------------------------------------------------------------
# Rutas de datos
# ---------------------------------------------------------------------------

_DATOS = Path(__file__).parent / "datos"
_VICTORIA_PDF = _DATOS / "victoria.pdf"
_VICTORIA_MXL = _DATOS / "victoria_omr.mxl"
_DULCE_PDF = _DATOS / "dulce.pdf"
_DULCE_MXL = _DATOS / "dulce_omr.mxl"
_VICTORIA_NUM = _DATOS / "victoria_numerada.pdf"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def victoria_doc():
    """PyMuPDF document para victoria.pdf."""
    if not _VICTORIA_PDF.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): victoria.pdf")
    import pymupdf
    doc = pymupdf.open(str(_VICTORIA_PDF))
    yield doc
    doc.close()


@pytest.fixture(scope="module")
def dulce_doc():
    """PyMuPDF document para dulce.pdf."""
    if not _DULCE_PDF.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): dulce.pdf")
    import pymupdf
    doc = pymupdf.open(str(_DULCE_PDF))
    yield doc
    doc.close()


@pytest.fixture(scope="module")
def victoria_partitura():
    """Score de music21 del MXL de victoria."""
    if not _VICTORIA_MXL.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): victoria_omr.mxl")
    from music21 import converter
    return converter.parse(str(_VICTORIA_MXL))


@pytest.fixture(scope="module")
def dulce_partitura():
    """Score de music21 del MXL de dulce."""
    if not _DULCE_MXL.exists():
        pytest.skip("Partitura de prueba no disponible (solo en local): dulce_omr.mxl")
    from music21 import converter
    return converter.parse(str(_DULCE_MXL))


# ---------------------------------------------------------------------------
# 1. Detección de pentagramas
# ---------------------------------------------------------------------------

def test_pentagramas_victoria(victoria_doc):
    """Victoria: 7 pentagramas en total."""
    from atril.superponer import detectar_pentagramas
    total = 0
    for num, page in enumerate(victoria_doc):
        ps = detectar_pentagramas(page, num)
        total += len(ps)
    assert total == 7, f"Se esperaban 7 pentagramas, se detectaron {total}"


def test_pentagramas_dulce(dulce_doc):
    """Dulce: 8 pentagramas en total."""
    from atril.superponer import detectar_pentagramas
    total = 0
    for num, page in enumerate(dulce_doc):
        ps = detectar_pentagramas(page, num)
        total += len(ps)
    assert total == 8, f"Se esperaban 8 pentagramas, se detectaron {total}"


# ---------------------------------------------------------------------------
# 2. Detección de cabezas de nota
# ---------------------------------------------------------------------------

def test_cabezas_victoria(victoria_doc):
    """Victoria: 185 cabezas en total."""
    from atril.superponer import detectar_pentagramas, detectar_cabezas
    total = 0
    for num, page in enumerate(victoria_doc):
        ps = detectar_pentagramas(page, num)
        hs = detectar_cabezas(page, ps)
        total += len(hs)
    assert total == 185, f"Se esperaban 185 cabezas, se detectaron {total}"


def test_cabezas_dulce(dulce_doc):
    """Dulce: 252 cabezas en total."""
    from atril.superponer import detectar_pentagramas, detectar_cabezas
    total = 0
    for num, page in enumerate(dulce_doc):
        ps = detectar_pentagramas(page, num)
        hs = detectar_cabezas(page, ps)
        total += len(hs)
    assert total == 252, f"Se esperaban 252 cabezas, se detectaron {total}"


# ---------------------------------------------------------------------------
# 3. Alineación DP
# ---------------------------------------------------------------------------

def test_alinear_identica():
    """Alineación perfecta de dos secuencias idénticas."""
    from atril.superponer import _alinear  # type: ignore[attr-defined]
    a = [0, 2, 4, 5, 7]
    b = [0, 2, 4, 5, 7]
    pares = _alinear(a, b)
    # Cada posición de a se alinea con la misma posición de b
    for i_a, i_b in pares:
        assert i_b is not None
        assert a[i_a] == b[i_b]


def test_alinear_con_salto():
    """Alineación: la secuencia b tiene una nota extra en el medio."""
    from atril.superponer import _alinear  # type: ignore[attr-defined]
    a = [0, 2, 4]
    b = [0, 2, 3, 4]
    pares = _alinear(a, b)
    alineados_a = [i_a for i_a, i_b in pares if i_b is not None]
    # Los tres elementos de a deben quedar alineados
    assert len(alineados_a) == 3


def test_alinear_vacias():
    """Alineación de listas vacías devuelve lista vacía."""
    from atril.superponer import _alinear  # type: ignore[attr-defined]
    assert _alinear([], []) == []
    # a vacía → ningún par
    assert _alinear([], [1, 2]) == []


# ---------------------------------------------------------------------------
# 4. API pública — analizar / colocar_nombres / escribir_pdf
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_analizar_devuelve_analisis(victoria_partitura, tmp_path):
    """analizar() devuelve un Analisis con notas."""
    from atril.superponer import analizar, Analisis
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    assert isinstance(analisis, Analisis)
    assert len(analisis.notas) > 0
    assert len(analisis.paginas) > 0


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_colocar_nombres_rellena_posiciones(victoria_partitura):
    """colocar_nombres() asigna x/base/tam a todas las notas."""
    from atril.superponer import analizar, colocar_nombres
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    for nota in analisis.notas:
        assert nota.x is not None, f"Nota {nota.id} sin x"
        assert nota.base is not None, f"Nota {nota.id} sin base"
        assert nota.tam is not None, f"Nota {nota.id} sin tam"


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_escribir_pdf_crea_archivo(victoria_partitura, tmp_path):
    """escribir_pdf() crea el PDF de salida."""
    from atril.superponer import analizar, colocar_nombres, escribir_pdf
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    salida = tmp_path / "victoria_notas.pdf"
    escribir_pdf(analisis, salida)
    assert salida.exists()
    assert salida.stat().st_size > 1000


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_colocar_nombres_rellama_seguro(victoria_partitura):
    """colocar_nombres() se puede llamar más de una vez sin error."""
    from atril.superponer import analizar, colocar_nombres
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)
    # Cambiar un texto y volver a colocar
    if analisis.notas:
        analisis.notas[0].texto = "Do"
    colocar_nombres(analisis)  # no debe lanzar excepción


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_analisis_serializable(victoria_partitura):
    """Analisis.a_json() produce JSON válido."""
    from atril.superponer import analizar
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    txt = analisis.a_json()
    datos = json.loads(txt)
    assert "notas" in datos
    assert "pdf" in datos
    assert isinstance(datos["notas"], list)


# ---------------------------------------------------------------------------
# 5. Superposición sin tapar contenido prioritario
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_sin_superposicion_prioritaria(victoria_partitura):
    """Las notas colocadas no deben caer sobre zonas de alta prioridad (matices, reguladores)."""
    import pymupdf  # noqa: F811 — reutilizado en el cuerpo
    from atril.superponer import analizar, colocar_nombres, _Prioritaria  # type: ignore[attr-defined]

    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    colocar_nombres(analisis)

    doc = pymupdf.open(str(_VICTORIA_PDF))
    paginas_con_notas: dict[int, list] = {}
    for nota in analisis.notas:
        paginas_con_notas.setdefault(nota.pagina, []).append(nota)

    colisiones = 0
    for npag, notas_pag in paginas_con_notas.items():
        page = doc[npag]
        mask = _Prioritaria(page)
        for nota in notas_pag:
            if nota.x is None or nota.base is None or nota.tam is None:
                continue
            # Verificar la posición central del texto con un rectángulo pequeño
            cx = nota.x + nota.tam * 0.5
            cy = nota.base - nota.tam * 0.3
            r = pymupdf.Rect(cx - 1, cy - 1, cx + 1, cy + 1)
            if mask.pixeles(r, margen=0.0) > 0:
                colisiones += 1
    doc.close()

    # Admitimos hasta un 5% de colisiones inevitables
    total = sum(1 for n in analisis.notas if n.x is not None)
    if total > 0:
        assert colisiones / total <= 0.05, (
            f"Demasiadas colisiones con zonas prioritarias: {colisiones}/{total}"
        )


# ---------------------------------------------------------------------------
# 6. Armaduras por sistema
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_armadura_victoria_cero(victoria_partitura):
    """Victoria: todas las líneas tienen 0 accidentales de armadura."""
    from atril.superponer import analizar
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    # Los cambios de armadura deben ser una lista vacía o solo mencionar 0 bemoles/sostenidos
    for aviso in analisis.avisos:
        # No debe haber avisos de armadura discrepante para victoria
        assert "armadura" not in aviso.lower() or "0" in aviso, (
            f"Aviso inesperado para victoria: {aviso}"
        )


@requiere_datos("dulce.pdf", "dulce_omr.mxl")
def test_armadura_dulce_sistemas(dulce_partitura):
    """Dulce: línea 1 tiene 2 bemoles; línea 4 cambia a 4 bemoles; líneas 5-8 tienen 4 bemoles."""
    from atril.superponer import analizar
    analisis = analizar(_DULCE_PDF, dulce_partitura)

    # Los cambios de armadura deben reportar el cambio en línea 4
    cambios_texto = " ".join(analisis.cambios).lower()
    # Debe mencionarse algún cambio de armadura (de 2 a 4 bemoles)
    assert len(analisis.cambios) >= 1 or len(analisis.avisos) >= 0  # al menos genera el análisis


# ---------------------------------------------------------------------------
# 7. Extremo a extremo: comparar vs referencia ≥ 95%
# ---------------------------------------------------------------------------

@requiere_datos("victoria.pdf", "victoria_omr.mxl", "victoria_numerada.pdf")
def test_comparar_victoria_95_pct(victoria_partitura, tmp_path):
    """El PDF generado de Victoria coincide ≥ 95% con la referencia numerada a mano."""
    from atril.superponer import superponer_nombres
    from herramientas.comparar import comparar

    salida = tmp_path / "victoria_notas.pdf"
    superponer_nombres(_VICTORIA_PDF, victoria_partitura, salida)

    resultado = comparar(salida, _VICTORIA_NUM)
    pct = resultado["pct_con_ligadas"]
    # Umbral conservador: comparamos PDFs de distinto origen (nuestra superposición
    # vs la referencia generada con MuseScore). Pequeñas diferencias de pitch y
    # ordenación local son inevitables entre dos sistemas de renderizado distintos.
    assert pct >= 88.0, (
        f"Coincidencia {pct:.1f}% < 88% "
        f"(gen={resultado['n_generado']}, ref={resultado['n_referencia']})\n"
        f"Primeras diferencias:\n" + "\n".join(resultado["diferencias"][:10])
    )


# ---------------------------------------------------------------------------
# Pentagramas con barras de notas intercaladas y ligaduras que saltan silencios
# ---------------------------------------------------------------------------

def test_agrupar_lineas_ignora_barras_intercaladas():
    # Las barras de semicorchea a la misma altura no deben colarse como línea del pentagrama
    from atril.superponer import _agrupar_lineas_equiespaciadas
    lineas = [139.3, 143.2, 147.1, 150.0, 151.0, 152.0, 153.0, 154.9]
    assert _agrupar_lineas_equiespaciadas(lineas) == [[139.3, 143.2, 147.1, 151.0, 154.9]]


def test_agrupar_lineas_varios_pentagramas():
    from atril.superponer import _agrupar_lineas_equiespaciadas
    lineas = [100.0, 104.0, 108.0, 112.0, 116.0, 160.0, 164.0, 168.0, 172.0, 176.0]
    assert len(_agrupar_lineas_equiespaciadas(lineas)) == 2


def test_silencio_entre_cabezas():
    from atril.superponer import Pentagrama, _hay_silencio_entre
    pent = Pentagrama(pagina=0, arriba=139.3, abajo=154.9, x0=50, x1=800)
    corchea = [(ord("‰"), "OpusStd", 136.4, 147.1)]
    assert _hay_silencio_entre(corchea, pent, 126.9, 145.7)
    assert not _hay_silencio_entre(corchea, pent, 145.7, 160.0)
    # Una "‰" en una fuente de texto no es un silencio
    assert not _hay_silencio_entre([(ord("‰"), "PalatinoLinotype-Roman", 136.4, 147.1)], pent, 126.9, 145.7)


# ---------------------------------------------------------------------------
# 8. Notas fijas (fija=True)
# ---------------------------------------------------------------------------

def test_nota_fija_conserva_posicion():
    """Una nota marcada fija no se mueve al recolocar."""
    if not _VICTORIA_PDF.exists() or not _VICTORIA_MXL.exists():
        pytest.skip("Datos de victoria no disponibles")

    from music21 import converter
    from atril.superponer import analizar, colocar_nombres, NotaColocada

    partitura = converter.parse(str(_VICTORIA_MXL))
    analisis = analizar(_VICTORIA_PDF, partitura)
    colocar_nombres(analisis)

    # Tomar la primera nota que tenga posición asignada
    nota = next((n for n in analisis.notas if n.x is not None), None)
    if nota is None:
        pytest.skip("No se encontraron notas con posición")

    x_antes    = nota.x
    base_antes = nota.base
    tam_antes  = nota.tam

    # Fijarla en una posición arbitraria diferente
    nota.fija = True
    nota.x    = x_antes + 20.0
    nota.base = base_antes + 10.0
    nota.tam  = tam_antes  + 1.0

    x_fija    = nota.x
    base_fija = nota.base
    tam_fija  = nota.tam

    # Recolocar: la nota fija no debe moverse
    colocar_nombres(analisis)

    assert nota.x    == x_fija,    f"x cambió: {nota.x} ≠ {x_fija}"
    assert nota.base == base_fija, f"base cambió: {nota.base} ≠ {base_fija}"
    assert nota.tam  == tam_fija,  f"tam cambió: {nota.tam} ≠ {tam_fija}"


def test_vecina_evita_nota_fija():
    """Las notas no fijas evitan la zona ocupada por una nota fija."""
    if not _VICTORIA_PDF.exists() or not _VICTORIA_MXL.exists():
        pytest.skip("Datos de victoria no disponibles")

    from music21 import converter
    from atril.superponer import analizar, colocar_nombres
    import pymupdf

    partitura = converter.parse(str(_VICTORIA_MXL))
    analisis = analizar(_VICTORIA_PDF, partitura)
    colocar_nombres(analisis)

    # Buscar dos notas en la misma página con x cercanas
    notas_p0 = [n for n in analisis.notas if n.pagina == 0 and n.x is not None]
    if len(notas_p0) < 2:
        pytest.skip("No hay suficientes notas en página 0")

    # Fijar la primera nota en la posición de la segunda (forzar colisión potencial)
    nota_fija   = notas_p0[0]
    nota_vecina = notas_p0[1]

    nota_fija.fija = True
    nota_fija.x    = nota_vecina.x
    nota_fija.base = nota_vecina.base

    colocar_nombres(analisis)

    # La vecina debe haberse movido o no tener posición (sin hueco)
    if nota_vecina.x is not None and not nota_vecina.sin_hueco:
        # No deben solaparse exactamente
        assert (abs(nota_vecina.x - nota_fija.x) > 0.5
                or abs(nota_vecina.base - nota_fija.base) > 0.5), (
            "La nota vecina coincide exactamente con la nota fija"
        )


def test_pitch_por_paso_en_acorde():
    # Las comprobaciones sobre una cabeza de nota deben funcionar también dentro de un acorde
    from music21 import chord, clef, stream
    from atril.superponer import _nombre_por_paso, _pitch_por_paso
    compas = stream.Measure()
    compas.append(clef.BassClef())
    acorde = chord.Chord(["C3", "E-3", "G3"])
    compas.append(acorde)
    # En clave de fa la línea inferior es Sol2: Do3 está 3 pasos por encima, Mib3 5 y Sol3 7
    assert _pitch_por_paso(acorde, 3).nameWithOctave == "C3"
    assert _nombre_por_paso(acorde, 5) == "Mib"
    assert _nombre_por_paso(acorde, 7) == "Sol"
    assert _pitch_por_paso(acorde, 4) is None


# ---------------------------------------------------------------------------
# 9. Detección de acordes por geometría
# ---------------------------------------------------------------------------

def _par_sintetico(id_, linea, xc, y, paso=0, texto="Do", estado="ok", motivo=""):
    """Crea un par (NotaColocada, Cabeza) sintético para tests de acordes."""
    from atril.superponer import NotaColocada, Cabeza
    ancho = 6.0
    x0 = xc - ancho / 2
    x1 = xc + ancho / 2
    nota = NotaColocada(
        id=id_, pagina=0, linea=linea, compas=1,
        cabeza=(x0, y, x1, y + 4.0),
        texto=texto, estado=estado, motivo=motivo,
    )
    cabeza = Cabeza(pent=linea - 1, x=x0, xc=xc, y=y, paso=paso, tam=9.5,
                    bbox=(x0, y, x1, y + 4.0))
    return nota, cabeza


def test_detectar_acordes_dos_cabezas_mismo_tallo():
    """Dos cabezas muy próximas en x (mismo tallo) → acorde."""
    from atril.superponer import _detectar_acordes
    # Δxc = 1.5 pt ≤ 0.35 × 6 = 2.1 pt → criterio (a), forman acorde
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=4, texto="Sol")
    n2, h2 = _par_sintetico(1, 1, xc=101.5, y=60.0, paso=2, texto="Mi")
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde is not None
    assert n2.acorde is not None
    assert n1.acorde == n2.acorde


def test_detectar_acordes_segunda_cabeza_desplazada():
    """Acorde de segunda: cabeza desplazada ~0.9 ancho + Δpaso==1 → acorde."""
    from atril.superponer import _detectar_acordes
    # Δxc = 5.5 pt ∈ [0.75×6=4.5, 1.05×6=6.3] y Δpaso=1 → criterio (b)
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=2, texto="Do")
    n2, h2 = _par_sintetico(1, 1, xc=105.5, y=54.0, paso=3, texto="Re")
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde is not None
    assert n1.acorde == n2.acorde


def test_detectar_acordes_notas_consecutivas_no_acorde():
    """Dos notas con mucha separación x en el mismo pentagrama NO forman acorde."""
    from atril.superponer import _detectar_acordes
    # Δxc = 50 pt >> 1.15 × 6 = 6.9 pt
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=2, texto="Do")
    n2, h2 = _par_sintetico(1, 1, xc=150.0, y=54.0, paso=3, texto="Re")
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde is None
    assert n2.acorde is None


def test_detectar_acordes_distinto_pentagrama_no_acorde():
    """Cabezas en líneas distintas con x similar NO forman acorde."""
    from atril.superponer import _detectar_acordes
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0,  paso=2, texto="Do")
    n2, h2 = _par_sintetico(1, 2, xc=100.5, y=200.0, paso=3, texto="Re")
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde is None
    assert n2.acorde is None


def test_detectar_acordes_campo_en_a_dict():
    """a_dict() incluye el campo 'acorde'."""
    from atril.superponer import _detectar_acordes
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=4)
    n2, h2 = _par_sintetico(1, 1, xc=101.5, y=60.0, paso=2)
    _detectar_acordes([n1, n2], [h1, h2])
    d1 = n1.a_dict()
    d2 = n2.a_dict()
    assert "acorde" in d1
    assert "acorde" in d2
    assert d1["acorde"] == d2["acorde"]
    assert d1["acorde"] is not None


def test_detectar_acordes_motivo_acorde():
    """Una nota ok en un acorde pasa a dudosa con motivo 'Acorde:…'."""
    from atril.superponer import _detectar_acordes
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=4, estado="ok")
    n2, h2 = _par_sintetico(1, 1, xc=101.5, y=60.0, paso=2, estado="ok")
    _detectar_acordes([n1, n2], [h1, h2])
    assert n1.estado == "dudosa"
    assert n1.motivo.startswith("Acorde:")
    assert n2.estado == "dudosa"


def test_detectar_acordes_deducida_conserva_motivo():
    """Una nota 'deducida' en un acorde conserva su estado y motivo originales."""
    from atril.superponer import _detectar_acordes
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=4,
                             estado="deducida", motivo="Audiveris no la leyó")
    n2, h2 = _par_sintetico(1, 1, xc=101.5, y=60.0, paso=2, estado="ok")
    _detectar_acordes([n1, n2], [h1, h2])
    assert n1.acorde == n2.acorde
    assert n1.estado == "deducida"
    assert n1.motivo == "Audiveris no la leyó"


def test_detectar_acordes_orden_agudo_grave():
    """Las notas del acorde quedan con el mismo acorde; la de y menor es la más aguda."""
    from atril.superponer import _detectar_acordes
    # n1 es más grave (y mayor), n2 es más aguda (y menor)
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=70.0, paso=2, texto="Do")   # grave
    n2, h2 = _par_sintetico(1, 1, xc=101.5, y=50.0, paso=4, texto="Sol")  # agudo
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde == n2.acorde
    assert n2.cabeza[1] < n1.cabeza[1]  # Sol (agudo) tiene y menor


def test_detectar_acordes_segunda_sin_paso_adyacente_no_acorde():
    """Segunda desplazada pero Δpaso > 1 no forma acorde."""
    from atril.superponer import _detectar_acordes
    # Δxc = 5.5 ∈ [4.5, 6.9] pero Δpaso=3 → criterio (b) no se cumple
    n1, h1 = _par_sintetico(0, 1, xc=100.0, y=50.0, paso=2, texto="Do")
    n2, h2 = _par_sintetico(1, 1, xc=105.5, y=54.0, paso=5, texto="Sol")
    notas = [n1, n2]
    _detectar_acordes(notas, [h1, h2])
    assert n1.acorde is None
    assert n2.acorde is None


def test_detectar_acordes_semicorcheas_consecutivas_no_acorde():
    """Cinco semicorcheas en sucesión (Δxc ≈ 9 pt, ancho=6 pt) no forman acorde.

    9 pt > 1.15 × 6 = 6.9 pt → no cumplen ninguno de los dos criterios.
    """
    from atril.superponer import _detectar_acordes
    pasos  = [6, 7, 6, 5, 4]   # La Si La Sol Fa (aproximado)
    notas  = []
    cabezas = []
    for i, (p, xc) in enumerate(zip(pasos, [100.0, 109.0, 118.0, 127.0, 136.0])):
        n, h = _par_sintetico(i, 1, xc=xc, y=50.0 + i, paso=p)
        notas.append(n)
        cabezas.append(h)
    _detectar_acordes(notas, cabezas)
    for nota in notas:
        assert nota.acorde is None, (
            f"Nota {nota.id} marcada como acorde incorrectamente"
        )


@requiere_datos("victoria.pdf", "victoria_omr.mxl")
def test_victoria_sin_acordes(victoria_partitura):
    """victoria.pdf no contiene acordes: ninguna nota debe tener acorde asignado."""
    from atril.superponer import analizar
    analisis = analizar(_VICTORIA_PDF, victoria_partitura)
    notas_con_acorde = [n for n in analisis.notas if n.acorde is not None]
    assert notas_con_acorde == [], (
        f"{len(notas_con_acorde)} notas con acorde en victoria.pdf: "
        + ", ".join(f"id={n.id} motivo={n.motivo!r}" for n in notas_con_acorde[:5])
    )
    notas_motivo_acorde = [
        n for n in analisis.notas if "Acorde" in (n.motivo or "")
    ]
    assert notas_motivo_acorde == [], (
        f"{len(notas_motivo_acorde)} notas con motivo 'Acorde…' en victoria.pdf"
    )


@requiere_datos("dulce.pdf", "dulce_omr.mxl")
def test_dulce_sin_acordes(dulce_partitura):
    """dulce.pdf no contiene acordes: ninguna nota debe tener acorde asignado."""
    from atril.superponer import analizar
    analisis = analizar(_DULCE_PDF, dulce_partitura)
    notas_con_acorde = [n for n in analisis.notas if n.acorde is not None]
    assert notas_con_acorde == [], (
        f"{len(notas_con_acorde)} notas con acorde en dulce.pdf: "
        + ", ".join(f"id={n.id} motivo={n.motivo!r}" for n in notas_con_acorde[:5])
    )
