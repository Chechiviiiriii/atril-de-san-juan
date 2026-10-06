# Empaquetado de Atril de San Juan

## Cómo construir el instalador

### Requisitos previos

- **Python 3.13** con todas las dependencias instaladas:
  ```
  pip install -r requirements.txt
  pip install pyinstaller pillow
  ```
- **Inno Setup 6** en `C:\Users\josem\AppData\Local\Programs\Inno Setup 6\`
  Descarga: https://jrsoftware.org/isinfo.php
- **Audiveris 5.11** en `C:\Program Files\Audiveris\`
  Descarga: https://github.com/Audiveris/audiveris/releases
- **Certificado de firma** en `Cert:\CurrentUser\My\D577DBF9FC4285E6AE32FD7CD85816090D2C8BC4`

### Ejecutar el script

Desde la raíz del proyecto, en PowerShell:

```powershell
.\empaquetado\construir.ps1
```

El script realiza en orden:
1. Tests rápidos (`pytest -m "not lento"`)
2. Limpieza de `build/` y `dist/`
3. Generación del icono `.ico` multitamaño (16–256 px)
4. PyInstaller en modo `onedir` (carpeta única, sin consola)
5. Copia de Audiveris a `dist\AtrilDeSanJuan\audiveris\`
6. Firma del ejecutable principal
7. Inno Setup: genera y firma el instalador

El instalador resultante estará en:
```
empaquetado\salida\Instalar Atril de San Juan 0.1.0.exe
```

---

## Cómo instalar la aplicación

1. Ejecuta `Instalar Atril de San Juan 0.1.0.exe`.
2. **Aviso de Windows**: al ser una firma autofirmada, Windows puede mostrar
   el mensaje *"Windows protegió su PC"*. Para continuar:
   - Haz clic en **"Más información"**
   - Haz clic en **"Ejecutar de todas formas"**

   Este aviso aparece porque el certificado no está firmado por una Autoridad
   Certificadora reconocida. El programa es seguro; el código fuente está
   disponible en:
   https://github.com/Chechiviiiriii/atril-de-san-juan

3. Sigue los pasos del asistente. La instalación **no requiere privilegios de
   administrador** y se instala en la carpeta personal del usuario:
   ```
   %LOCALAPPDATA%\Programs\Atril de San Juan\
   ```
4. Opcionalmente, crea un acceso directo en el escritorio.

### Nota sobre firmas en el futuro

En cuanto el repositorio sea público, se puede solicitar firma gratuita
a través de **SignPath Foundation** (https://signpath.io), que ofrece firma
de código para proyectos de código abierto. Esto eliminaría el aviso de
Windows.

---

## Desinstalación

Usa **"Agregar o quitar programas"** → busca *Atril de San Juan* →
**Desinstalar**.

---

## Licencias de componentes incluidos

| Componente | Licencia |
|---|---|
| **Audiveris** (OMR) | AGPL-3.0 |
| **PyMuPDF / MuPDF** (PDF) | AGPL-3.0 |
| **music21** (análisis musical) | BSD 3-Clause |
| **pywebview** (interfaz) | BSD 3-Clause |
| **Python** | PSF License |

Código fuente de Atril de San Juan:
https://github.com/Chechiviiiriii/atril-de-san-juan

---

## Estructura de los archivos de empaquetado

```
empaquetado/
  datos_app.json       — nombre, versión, autor, app_id (fuente única de verdad)
  lanzador.py          — entry point de PyInstaller (--diagnostico, --solo-servidor)
  AtrilDeSanJuan.spec  — configuración de PyInstaller
  instalador.iss       — script de Inno Setup
  construir.ps1        — script de construcción completo
  firmar_archivo.ps1   — helper para firmar un archivo con Set-AuthenticodeSignature
  icono.ico            — generado por construir.ps1
  aviso.txt            — texto de aviso legal mostrado en el instalador
  certificado_publico.cer — parte pública del certificado (no incluye clave privada)
  LEEME.md             — este archivo
  salida/              — instalador final (generado; no se sube a git)
```
