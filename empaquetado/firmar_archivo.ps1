# firmar_archivo.ps1 — Firma un archivo con el certificado de código de Atril de San Juan.
# Uso: powershell -ExecutionPolicy Bypass -File firmar_archivo.ps1 <ruta_archivo>
param(
    [Parameter(Mandatory=$true)]
    [string]$Archivo
)

$HuellaDigital = "D577DBF9FC4285E6AE32FD7CD85816090D2C8BC4"
$ServidorTimestamp = "http://timestamp.digicert.com"

$cert = Get-Item "Cert:\CurrentUser\My\$HuellaDigital" -ErrorAction Stop
$resultado = Set-AuthenticodeSignature `
    -FilePath $Archivo `
    -Certificate $cert `
    -HashAlgorithm SHA256 `
    -TimestampServer $ServidorTimestamp

if ($resultado.Status -ne "Valid" -and $resultado.Status -ne "UnknownError") {
    Write-Error "La firma de '$Archivo' falló: $($resultado.Status)"
    exit 1
}
Write-Host "Firmado: $Archivo  [$($resultado.Status)]"
