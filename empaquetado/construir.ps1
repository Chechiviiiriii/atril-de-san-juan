# construir.ps1 — Script de construcción de Atril de San Juan
# Genera el instalador firmado para Windows.
#
# Requisitos previos:
#   - Python 3.13 con todas las dependencias instaladas (requirements.txt)
#   - PyInstaller 6.x  (pip install pyinstaller)
#   - Inno Setup 6 en C:\Users\josem\AppData\Local\Programs\Inno Setup 6\ISCC.exe
#   - Pillow instalado  (pip install pillow)
#   - Certificado de firma en Cert:\CurrentUser\My\D577DBF9FC4285E6AE32FD7CD85816090D2C8BC4
#   - Audiveris 5.11 en C:\Program Files\Audiveris\
#
# Uso:
#   Set-Location "<raíz_del_proyecto>"
#   .\empaquetado\construir.ps1

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

$RAIZ        = (Get-Item "$PSScriptRoot\..").FullName
$EMP         = $PSScriptRoot
$ISCC        = "C:\Users\josem\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
$AUDIVERIS   = "C:\Program Files\Audiveris"
$HUELLA      = "D577DBF9FC4285E6AE32FD7CD85816090D2C8BC4"
$TIMESTAMP   = "http://timestamp.digicert.com"
$SPEC        = Join-Path $EMP "AtrilDeSanJuan.spec"
$FIRMAR_PS1  = Join-Path $EMP "firmar_archivo.ps1"
$ISS         = Join-Path $EMP "instalador.iss"
$ICONO       = Join-Path $EMP "icono.ico"
$PNG_ORIG    = Join-Path $RAIZ "interfaz\web\img\escudo_transparente.png"
$DIST_DIR    = Join-Path $RAIZ "dist\AtrilDeSanJuan"
$SALIDA_DIR  = Join-Path $EMP "salida"

# Leer metadatos
$datos = Get-Content (Join-Path $EMP "datos_app.json") -Raw | ConvertFrom-Json
$NOMBRE_APP = $datos.nombre
$VERSION    = $datos.version
$EXE_NOMBRE = $datos.ejecutable

Write-Host ""
Write-Host "========================================================"
Write-Host "  Construcción: $NOMBRE_APP $VERSION"
Write-Host "========================================================"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Tests rápidos
# ---------------------------------------------------------------------------

Write-Host "[1/7] Ejecutando tests rápidos (pytest -m 'not lento')..."
Set-Location $RAIZ
python -m pytest -m "not lento" -q --tb=short
if ($LASTEXITCODE -ne 0) { throw "Los tests fallaron. Corrígelos antes de empaquetar." }
Write-Host "      Tests OK."
Write-Host ""

# ---------------------------------------------------------------------------
# 2. Limpiar directorios de construcción anteriores
# ---------------------------------------------------------------------------

Write-Host "[2/7] Limpiando directorios build/ y dist/..."
foreach ($dir in @("build", "dist")) {
    $ruta = Join-Path $RAIZ $dir
    if (Test-Path $ruta) {
        Remove-Item $ruta -Recurse -Force
        Write-Host "      Eliminado: $ruta"
    }
}
if (Test-Path $SALIDA_DIR) {
    Remove-Item $SALIDA_DIR -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $SALIDA_DIR | Out-Null
Write-Host "      Listo."
Write-Host ""

# ---------------------------------------------------------------------------
# 3. Generar icono .ico multitamaño
# ---------------------------------------------------------------------------

Write-Host "[3/7] Generando icono ICO desde $PNG_ORIG..."
python -c "
from PIL import Image
from pathlib import Path

src = Path(r'$PNG_ORIG')
dst = Path(r'$ICONO')

img = Image.open(src).convert('RGBA')
tamanios = [16, 32, 48, 64, 128, 256]
imagenes = [img.resize((t, t), Image.LANCZOS) for t in tamanios]
imagenes[0].save(dst, format='ICO', sizes=[(t, t) for t in tamanios],
                  append_images=imagenes[1:])
print(f'  Icono generado: {dst}  ({tamanios})')
"
if ($LASTEXITCODE -ne 0) { throw "Falló la generación del icono ICO." }
Write-Host ""

# ---------------------------------------------------------------------------
# 4. PyInstaller (modo onedir, sin consola)
# ---------------------------------------------------------------------------

Write-Host "[4/7] Ejecutando PyInstaller..."
Set-Location $RAIZ
python -m PyInstaller "$SPEC" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }
Write-Host "      PyInstaller completado."
Write-Host ""

# ---------------------------------------------------------------------------
# 5. Copiar Audiveris al directorio de distribución
# ---------------------------------------------------------------------------

Write-Host "[5/7] Copiando Audiveris a dist\AtrilDeSanJuan\audiveris\..."
$DEST_AUDIVERIS = Join-Path $DIST_DIR "audiveris"
if (-not (Test-Path $AUDIVERIS)) {
    throw "No se encuentra Audiveris en '$AUDIVERIS'. Instálalo primero."
}
Copy-Item $AUDIVERIS -Destination $DEST_AUDIVERIS -Recurse -Force
Write-Host "      Audiveris copiado."
Write-Host ""

# ---------------------------------------------------------------------------
# 6. Firmar el ejecutable principal
# ---------------------------------------------------------------------------

Write-Host "[6/7] Firmando el ejecutable principal..."
$EXE_PATH = Join-Path $DIST_DIR "$EXE_NOMBRE.exe"
if (-not (Test-Path $EXE_PATH)) {
    throw "No se encuentra el ejecutable: $EXE_PATH"
}
& powershell.exe -ExecutionPolicy Bypass -File "$FIRMAR_PS1" "$EXE_PATH"
if ($LASTEXITCODE -ne 0) { throw "La firma del ejecutable falló." }

# Verificar firma
$firma = Get-AuthenticodeSignature -FilePath $EXE_PATH
if ($firma.SignerCertificate.Thumbprint -ne $HUELLA) {
    throw "El ejecutable no está firmado con el certificado esperado."
}
Write-Host "      Ejecutable firmado. Estado: $($firma.Status)"
Write-Host ""

# ---------------------------------------------------------------------------
# 7. Inno Setup — generar y firmar el instalador
# ---------------------------------------------------------------------------

Write-Host "[7/7] Generando el instalador con Inno Setup..."

# Construir la cadena de la herramienta de firma para ISCC.
# $f es reemplazado por Inno Setup con la ruta del archivo a firmar.
$ComandoFirma = "powershell.exe -ExecutionPolicy Bypass -File `"$FIRMAR_PS1`" `$f"

Set-Location $EMP
& "$ISCC" `
    "/SPSFirmar=$ComandoFirma" `
    "$ISS"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup (ISCC) falló." }
Write-Host "      Instalador generado."
Write-Host ""

# ---------------------------------------------------------------------------
# Verificación de firmas
# ---------------------------------------------------------------------------

Write-Host "Verificando firmas..."
$INSTALLER_PATH = Join-Path $SALIDA_DIR "Instalar $NOMBRE_APP $VERSION.exe"
if (-not (Test-Path $INSTALLER_PATH)) {
    throw "No se encuentra el instalador: $INSTALLER_PATH"
}

foreach ($archivo in @($EXE_PATH, $INSTALLER_PATH)) {
    $firma = Get-AuthenticodeSignature -FilePath $archivo
    $estado = $firma.Status
    $firmante = $firma.SignerCertificate.Subject
    Write-Host "  $([System.IO.Path]::GetFileName($archivo))"
    Write-Host "    Estado   : $estado"
    Write-Host "    Firmante : $firmante"
    if ($firma.SignerCertificate.Thumbprint -ne $HUELLA) {
        Write-Host "    AVISO: El certificado no coincide con la huella esperada."
    }
}
Write-Host ""

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------

$tamano_bytes = (Get-Item $INSTALLER_PATH).Length
$tamano_mb = [math]::Round($tamano_bytes / 1MB, 1)

Write-Host "========================================================"
Write-Host "  CONSTRUCCIÓN COMPLETADA"
Write-Host "========================================================"
Write-Host ""
Write-Host "  Instalador : $INSTALLER_PATH"
Write-Host "  Tamaño     : $tamano_mb MB"
Write-Host ""
Write-Host "  Nota: La firma es autofirmada. Windows mostrará el aviso"
Write-Host "  'Windows protegió su PC'. Los usuarios deben pulsar"
Write-Host "  'Más información' -> 'Ejecutar de todas formas'."
Write-Host ""
