# Atril de San Juan

Programa gratuito para Windows hecho para la **Agrupación Musical Stmo. Cristo de la Salud**
(Alcalá la Real, 1984). Pone el **nombre de cada nota** (Do, Reb, Fa#…) debajo de las notas de
una partitura en PDF y **empalma marchas** en un único PDF. Todo funciona en el ordenador, sin
internet, sin cuentas y sin coste.

> La partitura **no se redibuja**: los nombres se escriben encima del PDF original, que queda
> exactamente igual (matices, reguladores, textos, maquetación). Así no hay versiones distintas
> de una misma marcha.

---

## Índice

1. [Qué se puede hacer](#qué-se-puede-hacer)
2. [Instalación (músicos)](#instalación-músicos)
3. [Cómo se usa](#cómo-se-usa)
4. [Cómo funciona por dentro](#cómo-funciona-por-dentro)
5. [Estructura del proyecto](#estructura-del-proyecto)
6. [Desarrollo](#desarrollo)
7. [Crear el instalador](#crear-el-instalador)
8. [Limitaciones conocidas](#limitaciones-conocidas)
9. [Licencias y créditos](#licencias-y-créditos)

---

## Qué se puede hacer

### 1. Poner nombres a las notas

- Se sube el PDF de una partitura (exportado de **Sibelius, MuseScore o Finale**) y se obtiene el
  **mismo PDF** con el nombre de cada nota debajo, en solfeo español: `Do Re Mi Fa Sol La Si`,
  bemol `b`, sostenido `#` (`Mib`, `Fa#`, `Sibb`, `Fa##`).
- Respeta **clave** (sol, fa, do), **armadura**, **alteraciones accidentales** hasta la barra de
  compás, **becuadros** y **cambios de clave y de armadura** a mitad de la obra.
- **Ligaduras**: la primera nota lleva su nombre; las siguientes, un punto alto `·`, solo si la
  misma nota va justo detrás y en el mismo compás. Si hay un silencio o una barra en medio, se
  escribe el nombre.
- **Acordes** (dos o más notas a la vez): se nombran todas, de la más aguda a la más grave, y se
  marcan para revisar.
- **Los matices y reguladores mandan**: un nombre nunca tapa un matiz, un regulador, un texto,
  una letra de ensayo ni una ligadura. Si cabe, va entre el pentagrama y el regulador; si no,
  debajo; si hace falta, algo más pequeño o desplazado.
- **Notas dudosas** (en rojo/ámbar): las que el lector de partituras no leyó (se deducen del PDF),
  las que tienen una alteración dibujada distinta de la leída, las de una línea cuya armadura no
  cuadra y los acordes. El usuario las confirma o corrige antes de descargar.
- **Revisión a mano**: clic en cualquier nombre para cambiarlo (`Cambiar nota`), arrastrarlo para
  moverlo, cambiar su tamaño (A−/A+, esquina azul o Ctrl + rueda), deshacer (Ctrl+Z) y rehacer
  (Ctrl+Y). Lo que se ve en pantalla es exactamente lo que sale en el PDF.

### 2. Empalmar marchas

- Se arrastran varias marchas (PDF), se ordenan arrastrando o con ↑ ↓, se quitan con ✕ y se
  unen en un único PDF, **tal cual**, una detrás de otra.
- Muestra miniatura, título (detectado del propio PDF y editable) y número de páginas. Avisa si
  una marcha está repetida.

### 3. Guía y tutorial

- Un músico de la banda en pixel art vive abajo a la izquierda. La primera vez que se entra en
  cada pantalla explica cada botón con un **foco** (pantalla oscurecida salvo el botón que
  explica), señalándolo y con un bocadillo (`Anterior`, `Siguiente`, `Saltar`).
- Al pinchar en él, resume lo que se puede hacer en esa pantalla y repite el recorrido.
- «Volver a ver los tutoriales» al pie de la pantalla de inicio.

---

## Instalación (músicos)

1. Descargar `Instalar Atril de San Juan 0.1.0.exe`.
2. Abrirlo. Si Windows muestra **«Windows protegió su PC»**, pulsar
   **«Más información» → «Ejecutar de todas formas»** (el programa está firmado por su autor,
   pero no por una entidad comercial; ver [Firma](#firma)).
3. «Siguiente → Instalar». No pide permisos de administrador. Crea un acceso directo con el
   escudo y aparece en «Agregar o quitar programas» para desinstalarlo.

**Requisitos**: Windows 10 u 11 de 64 bits. La ventana usa Microsoft Edge WebView2, que viene
con Windows 11 y con Windows 10 actualizado (si no se abre la ventana, instalar «WebView2
Runtime» de Microsoft). No hace falta instalar nada más: el lector de partituras (Audiveris) y
su Java van dentro.

---

## Cómo se usa

**Poner nombres**: Inicio → *Poner nombres a las notas* → arrastrar el PDF → esperar unos
segundos → revisar las notas marcadas (lista a la derecha, `Anterior`/`Siguiente` o teclas
N/P) → **Confirmar y descargar PDF** → Guardar.

**Empalmar**: Inicio → *Empalmar marchas* → arrastrar los PDF → ordenar → nombre del archivo →
**Unir y descargar PDF**.

Atajos en la pantalla de revisión:

| Acción | Atajo |
| --- | --- |
| Siguiente / anterior nota dudosa | N / P (o Tab / Mayús+Tab) |
| Mover el nombre seleccionado | Flechas (Mayús: más rápido) |
| Cambiar tamaño | Ctrl + rueda del ratón |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y |
| Aceptar en el selector | Enter · Cerrar: Esc |

---

## Cómo funciona por dentro

```
PDF original ──► Audiveris (OMR) ──► MusicXML ──► music21: nombres por nota
     │                                                     │
     └──► PyMuPDF: pentagramas, cabezas de nota, ──► alineación PDF ↔ Audiveris
          líneas adicionales, alteraciones,                │
          armaduras, silencios                             ▼
                                         dudosas + colocación sin tapar matices
                                                           │
                                     revisión en la interfaz (opcional) ──► PDF original
                                                                            + nombres
```

1. **Lectura musical (`atril/omr.py`)**: Audiveris convierte el PDF en MusicXML. El resultado se
   guarda en caché por huella SHA-256 del PDF, así que repetir una partitura es instantáneo.
2. **Nombres (`atril/nombres.py`)**: music21 da la altura real de cada nota (armadura y
   alteraciones ya aplicadas) y se traduce a solfeo. Aquí vive la regla de ligaduras y la
   descripción de claves, armaduras y cambios.
3. **Lectura del PDF vectorial (`atril/superponer.py`)**:
   - **Pentagramas**: grupos de 5 líneas largas equiespaciadas (las líneas adicionales y las
     barras de corchea no cuentan).
   - **Cabezas de nota**: glifos de fuentes musicales clásicas (Opus de Sibelius, Maestro de
     Finale…) y SMuFL (Leland/Bravura de MuseScore/Dorico). El origen del glifo es el centro de la
     cabeza, lo que da su posición exacta en el pentagrama.
   - **Notas fuera del pentagrama**: se asignan a su pentagrama por su «escalera» de líneas
     adicionales, aunque estén más cerca del de arriba.
   - **Acordes**: cabezas en la misma plica o segundas desplazadas, ordenadas de agudo a grave.
4. **Alineación**: programación dinámica entre las cabezas del PDF y las notas de Audiveris, por
   línea. Las cabezas sin pareja se **deducen** del PDF (clave y armadura vigentes, alteración
   dibujada a la izquierda o previa en el compás).
5. **Comprobaciones**: alteración dibujada frente a la leída, armadura de cada línea (y cambios
   tras doble barra) frente a la de Audiveris, ligaduras imposibles (con silencio en medio o desde
   una nota en staccato).
6. **Colocación**: se renderiza la página, se calcula una máscara de tinta y otra «prioritaria»
   (textos, matices, reguladores, ligaduras) y cada nombre busca el hueco de menor coste (tamaños
   9,5 → 6,5 pt, pequeños desplazamientos). Nunca se coloca sobre lo prioritario.
7. **Salida**: PyMuPDF escribe el texto sobre el PDF original sin modificar nada más.
8. **Verificación (`atril/verificacion.py`)**: compara cabezas dibujadas y notas leídas por línea
   para avisar de dónde puede faltar algo.

La **interfaz** es una página web local (`interfaz/web/`) servida por un pequeño servidor HTTP de
la biblioteca estándar (`interfaz/servidor.py`) y mostrada en una ventana propia con
**pywebview** (Edge WebView2). Las preferencias (tutoriales vistos) se guardan en
`%LOCALAPPDATA%\Atril de San Juan\preferencias.json`.

---

## Estructura del proyecto

```
Abrir Atril de San Juan.bat   Abre la aplicación en un equipo con Python (desarrollo)
app.py                        Arranque de la interfaz (servidor local + ventana pywebview)
config.toml                   Rutas opcionales a Audiveris/MuseScore y opciones
requirements.txt / pyproject.toml
atril/                        Motor
  nombres.py                  Nombres en solfeo, ligaduras, claves y armaduras
  omr.py                      Llamada a Audiveris (incluido o instalado)
  superponer.py               Lectura del PDF, alineación, dudosas y colocación de nombres
  verificacion.py             Recuento de notas por línea PDF ↔ Audiveris
  empalme.py                  Unión de PDF
  render.py                   Modo antiguo: redibujar con MuseScore (opcional)
  config.py                   Carga de config.toml y búsqueda de programas
  estilo_nombres.mss          Estilo de MuseScore para el modo antiguo
interfaz/
  servidor.py, cache.py       API local y caché de lecturas
  web/                        index.html, app.js, estilo.css, guia.js, guia.css, tutorial.json
  web/img/                    Escudo, cartel y poses del guía (img/guia/)
herramientas/
  pdf2notas.py                Línea de comandos
  comparar.py                 Compara un PDF con nombres frente a una referencia numerada a mano
empaquetado/                  PyInstaller, Inno Setup, firma, icono (ver más abajo)
recursos/guia/                Hoja original del guía (Gemini) y script para recortarla
tests/                        Pruebas (pytest)
```

Los textos del tutorial están en `interfaz/web/tutorial.json` (se pueden cambiar sin tocar código).
El nombre, la versión y el enlace del programa están en `empaquetado/datos_app.json`.

---

## Desarrollo

Requisitos: Python 3.10+ (probado con 3.13), Windows, y Audiveris 5.11 instalado
(`winget install audiveris.org.Audiveris`). MuseScore solo hace falta para el modo `--redibujar`.

```bash
python -m pip install -r requirements.txt
python app.py                      # abre la aplicación
python app.py --navegador          # en el navegador en vez de ventana propia
python -m pytest -q -m "not lento" # pruebas rápidas
python -m pytest -q                # todas (las «lentas» usan Audiveris)
```

Línea de comandos:

```bash
python herramientas/pdf2notas.py partitura.pdf            # genera partitura_notas.pdf
python herramientas/pdf2notas.py --carpeta CARPETA        # todos los PDF de una carpeta
python herramientas/pdf2notas.py partitura.pdf --revisar  # corregir antes en MuseScore
python herramientas/pdf2notas.py partitura.pdf --redibujar  # modo antiguo (MuseScore)
python herramientas/comparar.py salida_notas.pdf referencia_numerada.pdf --diffs
```

**Partituras de prueba**: las partituras reales tienen derechos de autor y **no se suben al
repositorio** (`.gitignore`). Las pruebas que las usan se saltan si no están en `tests/datos/`.
Sí se incluyen partituras generadas por nosotros: `sintetica.pdf` (clave de fa, 4 bemoles) y
`agudas.pdf` (notas con muchas líneas adicionales y sistemas muy juntos).

---

## Crear el instalador

```powershell
powershell -ExecutionPolicy Bypass -File empaquetado\construir.ps1
```

Hace, en orden: pruebas → icono y imágenes del asistente → PyInstaller (modo carpeta, sin
consola) → copia de Audiveris dentro del programa → firma del `.exe` → Inno Setup (firma del
instalador y del desinstalador) → comprobación de firmas. Resultado:
`empaquetado\salida\Instalar Atril de San Juan <versión>.exe` (~125 MB).

Necesita PyInstaller (`pip install pyinstaller`) e Inno Setup 6 (`winget install JRSoftware.InnoSetup`).
Para comprobar un programa instalado sin abrir ventanas:
`AtrilDeSanJuan.exe --diagnostico informe.txt` o `--solo-servidor 8790`.

### Firma

El programa y el instalador se firman con un certificado **autofirmado** del autor
(`empaquetado/certificado_publico.cer` es su parte pública; la clave privada nunca sale del
equipo). Garantiza la autoría y que el archivo no se ha modificado, pero Windows sigue mostrando
el aviso de SmartScreen porque no es de una entidad reconocida. Cuando el repositorio sea
público se puede solicitar la firma gratuita de **SignPath Foundation** para proyectos de código
abierto.

---

## Limitaciones conocidas

- Solo PDF **vectoriales** (exportados de un editor de partituras). Con PDF escaneados se usa el
  modo antiguo (MuseScore redibuja la partitura) y el resultado no es idéntico al original.
- Solo Windows 10/11 de 64 bits.
- Partituras de una sola parte por pentagrama (las partichelas de banda). Partituras de director
  con varios pentagramas por sistema no están contempladas.
- El lector de partituras puede equivocarse en pasajes muy densos; por eso existen las notas
  dudosas y la revisión a mano.

---

## Licencias y créditos

- **Atril de San Juan**: José María Funes Jiménez, para la A.M. Stmo. Cristo de la Salud.
- **Audiveris** (lector de partituras) y **PyMuPDF** (lectura y escritura de PDF) se
  distribuyen bajo **AGPL-3.0**; por eso el código fuente de este programa está disponible en
  este repositorio.
- **music21** (BSD), **pywebview** (BSD), **NumPy** (BSD).
- Escudo y cartel: propiedad de la A.M. Stmo. Cristo de la Salud.
- Guía pixel art: generado con Gemini a partir de referencias de la banda.

Código fuente y actualizaciones: <https://github.com/Chechiviiiriii/atril-de-san-juan>
