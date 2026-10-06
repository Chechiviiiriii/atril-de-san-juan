# Shim de compatibilidad: re-exporta desde atril.superponer
# Este archivo permite que test_interfaz.py use 'from superponer import ...'
# sin modificar ese archivo de test.
from atril.superponer import *  # noqa: F401, F403
from atril.superponer import (  # noqa: F401
    analizar,
    colocar_nombres,
    escribir_pdf,
    superponer_nombres,
    detectar_pentagramas,
    detectar_cabezas,
    SinCabezasError,
    Analisis,
    _alinear,
)
