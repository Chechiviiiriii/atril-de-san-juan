"""
posiciones.py — Posiciones de pistones en lugar de los nombres de las notas.

Cada instrumento tiene una tabla «altura MIDI → texto que se escribe». La altura
se calcula a partir del nombre en solfeo (``Mib``, ``Fa#``…) y de la octava de la
letra, así que los enarmónicos (La#/Sib) comparten posición.

Reglas:
- Solo se escribe lo que está en la tabla; una nota sin entrada no lleva nada.
- La ligadura conserva su marca «·» (posición en la primera nota y «·» en las siguientes).
- La combinación exacta «1/2» se escribe con el símbolo configurable (``x`` por defecto);
  «1/2/3» y demás se escriben tal cual.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Notas y alturas
# ---------------------------------------------------------------------------

_CLASE_DE_PASO: dict[str, int] = {
    "Do": 0, "Re": 2, "Mi": 4, "Fa": 5, "Sol": 7, "La": 9, "Si": 11,
}
# Orden de prueba: "Sol" antes que "Si" no importa, pero sí que ninguno sea prefijo de otro.
_PASOS_ORDENADOS = sorted(_CLASE_DE_PASO, key=len, reverse=True)
_ALTER_DE_SUFIJO: dict[str, int] = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}

_NOMBRES_SOSTENIDO = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]
_NOMBRES_BEMOL = ["Do", "Reb", "Re", "Mib", "Mi", "Fa", "Solb", "Sol", "Lab", "La", "Sib", "Si"]

SIMBOLO_12_DEFECTO = "x"


def midi_de_nombre(nombre: str, octava: Optional[int]) -> Optional[int]:
    """Altura MIDI (Do4 = 60) de un nombre en solfeo con la octava de su letra.

    Devuelve None si el nombre no es una nota (``?``, ``·``…) o falta la octava.
    """
    if octava is None or not nombre:
        return None
    for paso in _PASOS_ORDENADOS:
        if nombre.startswith(paso):
            alter = _ALTER_DE_SUFIJO.get(nombre[len(paso):])
            if alter is None:
                return None
            return (octava + 1) * 12 + _CLASE_DE_PASO[paso] + alter
    return None


def etiqueta_de_midi(midi: int) -> str:
    """Etiqueta para la lista de configuración: «Do3», «Do#3 / Reb3»…"""
    octava = midi // 12 - 1
    clase = midi % 12
    sos, bem = _NOMBRES_SOSTENIDO[clase], _NOMBRES_BEMOL[clase]
    if sos == bem:
        return f"{sos}{octava}"
    return f"{sos}{octava} / {bem}{octava}"


# ---------------------------------------------------------------------------
# Tablas por defecto
# ---------------------------------------------------------------------------

def _tabla(desde: int, valores: list[str]) -> dict[int, str]:
    """Tabla cromática a partir de ``desde``; las cadenas vacías se omiten."""
    return {desde + i: v for i, v in enumerate(valores) if v}


# Trombón de pistones y bombardino de 3 pistones: de Sol2 a Fa#4.
_TABLA_3_PISTONES = _tabla(43, [
    "1/3", "2/3", "1/2", "1", "2",                                   # Sol2 – Si2
    "0", "1/2/3", "1/3", "2/3", "1/2", "1", "2", "0", "2/3", "1/2", "1", "2",  # Do3 – Si3
    "0", "1/2", "1", "2", "0", "1", "2",                             # Do4 – Fa#4
])

# Tuba (4 pistones): gráfico de tuba en Do sin el 5.º pistón, de Do1 a Do5.
_TABLA_TUBA = _tabla(24, [
    "0", "", "", "1/3/4", "2/3/4", "1/2/4", "2/4", "4", "2/3", "1/2", "1", "2",   # Do1 – Si1
    "0", "2/4", "4", "2/3", "1/2", "1", "2", "0", "2/3", "1/2", "1", "2",        # Do2 – Si2
    "0", "1/2", "1", "2/3", "0", "1", "2", "0", "2/3", "1/2", "1", "2",          # Do3 – Si3
    "0", "1/2", "0", "2/3", "0", "1", "2", "0", "2/3", "1/2", "1", "2",          # Do4 – Si4
    "0",                                                                          # Do5
])

# Bombardino de 4 pistones: la de 3 pistones más el 4.º (baja una cuarta justa),
# que da las notas graves hasta Reb2 y sustituye a 1-3 y 1-2-3 en Sol2, Re3 y Reb3.
# De Reb2 a Do5.
_TABLA_BOMBARDINO_4 = _tabla(37, [
    "1/2/3/4", "1/3/4", "2/3/4", "1/2/4", "1/4", "2/4", "4", "2/3", "1/2", "1", "2",  # Reb2 – Si2
    "0", "2/4", "4", "2/3", "1/2", "1", "2", "0", "2/3", "1/2", "1", "2",            # Do3 – Si3
    "0", "1/2", "1", "2", "0", "1", "2", "0", "2/3", "1/2", "1", "2",                # Do4 – Si4
    "0",                                                                              # Do5
])

# id → (nombre visible, (midi mínimo, midi máximo) de la lista de configuración, tabla)
INSTRUMENTOS: dict[str, tuple[str, tuple[int, int], dict[int, str]]] = {
    "tuba": ("Tuba", (24, 72), _TABLA_TUBA),
    "bombardino4": ("Bombardino 4 pistones", (36, 72), _TABLA_BOMBARDINO_4),
    "bombardino3": ("Bombardino 3 pistones", (40, 72), _TABLA_3_PISTONES),
    "trombon": ("Trombón de pistones", (40, 72), _TABLA_3_PISTONES),
}


# ---------------------------------------------------------------------------
# Configuración del usuario
# ---------------------------------------------------------------------------

def tabla_defecto(instrumento: str) -> dict[int, str]:
    return dict(INSTRUMENTOS[instrumento][2])


def tablas_usuario(config: Optional[dict], instrumento: str) -> dict[int, str]:
    """Tabla guardada por el usuario (sin aplicar el símbolo), o la de defecto."""
    guardadas = ((config or {}).get("tablas") or {}).get(instrumento)
    if not isinstance(guardadas, dict):
        return tabla_defecto(instrumento)
    tabla: dict[int, str] = {}
    for k, v in guardadas.items():
        try:
            midi = int(k)
        except (TypeError, ValueError):
            continue
        texto = str(v).strip()
        if texto:
            tabla[midi] = texto
    return tabla


def simbolo_12(config: Optional[dict]) -> str:
    s = (config or {}).get("simbolo_12")
    return str(s) if isinstance(s, str) else SIMBOLO_12_DEFECTO


def texto_final(valor: str, simbolo: str) -> str:
    """Aplica la regla de la «x»: solo la combinación exacta 1/2."""
    v = valor.strip()
    if v.replace(" ", "") == "1/2":
        return simbolo
    return v


def tabla_efectiva(config: Optional[dict], instrumento: str) -> dict[int, str]:
    """Tabla lista para imprimir (con el símbolo de 1/2 aplicado)."""
    simbolo = simbolo_12(config)
    return {
        midi: t
        for midi, valor in tablas_usuario(config, instrumento).items()
        if (t := texto_final(valor, simbolo))
    }


def describir_configuracion(config: Optional[dict]) -> dict:
    """Datos para la ventana de configuración (JSON)."""
    instrumentos = []
    for id_, (nombre, (lo, hi), _defecto) in INSTRUMENTOS.items():
        tabla = tablas_usuario(config, id_)
        defecto = tabla_defecto(id_)
        lo = min([lo, *tabla])
        hi = max([hi, *tabla])
        instrumentos.append({
            "id": id_,
            "nombre": nombre,
            "filas": [
                {
                    "midi": m,
                    "etiqueta": etiqueta_de_midi(m),
                    "valor": tabla.get(m, ""),
                    "defecto": defecto.get(m, ""),
                }
                for m in range(hi, lo - 1, -1)   # de agudo a grave
            ],
        })
    return {
        "simbolo_12": simbolo_12(config),
        "simbolo_12_defecto": SIMBOLO_12_DEFECTO,
        "instrumentos": instrumentos,
    }


def normalizar_configuracion(datos: dict) -> dict:
    """Valida lo que envía la interfaz y lo deja listo para guardar."""
    simbolo = datos.get("simbolo_12", SIMBOLO_12_DEFECTO)
    if not isinstance(simbolo, str):
        simbolo = SIMBOLO_12_DEFECTO
    tablas: dict[str, dict[str, str]] = {}
    for id_, tabla in (datos.get("tablas") or {}).items():
        if id_ not in INSTRUMENTOS or not isinstance(tabla, dict):
            continue
        limpia: dict[str, str] = {}
        for k, v in tabla.items():
            try:
                midi = int(k)
            except (TypeError, ValueError):
                continue
            texto = str(v).strip()[:12] if v is not None else ""
            if texto:
                limpia[str(midi)] = texto
        tablas[id_] = limpia
    return {"simbolo_12": simbolo.strip()[:6], "tablas": tablas}


# ---------------------------------------------------------------------------
# Aplicar a un análisis
# ---------------------------------------------------------------------------

def texto_posicion(nombre: str, octava: Optional[int], tabla: dict[int, str]) -> str:
    """Texto a imprimir para una nota: su posición, «·» o cadena vacía."""
    from .nombres import MARCA_LIGADA

    if nombre == MARCA_LIGADA:
        return MARCA_LIGADA
    midi = midi_de_nombre(nombre, octava)
    if midi is None:
        return ""
    return tabla.get(midi, "")


def aplicar_posiciones(analisis, tabla: Optional[dict[int, str]]) -> None:
    """Rellena ``impreso`` de cada nota. Con ``tabla=None`` se vuelve a los nombres."""
    for nota in analisis.notas:
        if tabla is None:
            nota.impreso = None
        else:
            nota.impreso = texto_posicion(nota.texto, nota.octava, tabla)
