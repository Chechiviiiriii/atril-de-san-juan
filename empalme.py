# Shim de compatibilidad: re-exporta desde atril.empalme
# Este archivo permite que test_interfaz.py use 'from empalme import ...'
# sin modificar ese archivo de test.
from atril.empalme import *  # noqa: F401, F403
from atril.empalme import contar_paginas  # noqa: F401
