; Script de Inno Setup para Atril de San Juan
; Requiere Inno Setup 6 — https://jrsoftware.org/isinfo.php
;
; Llamar con:
;   ISCC.exe /S"PSFirmar=powershell.exe -ExecutionPolicy Bypass -File <ruta_firmar_archivo.ps1> $f" instalador.iss

#define AppName      "Atril de San Juan"
#define AppExe       "AtrilDeSanJuan.exe"
#define AppVersion   "0.1.0"
#define AppPublisher "Jose Maria Funes Jimenez"
#define AppURL       "https://github.com/Chechiviiiriii/atril-de-san-juan"
#define AppId        "EB1E08E8-31FE-4ABE-8243-8DCC75B80E53"
#define DistDir      "..\dist\AtrilDeSanJuan"

[Setup]
AppId={{{#AppId}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=aviso.txt
OutputDir=salida
OutputBaseFilename=Instalar {#AppName} {#AppVersion}
SetupIconFile=icono.ico
WizardImageFile=asistente_grande_1x.bmp,asistente_grande_2x.bmp
WizardSmallImageFile=asistente_pequeno_1x.bmp,asistente_pequeno_2x.bmp
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
AppContact={#AppURL}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
; Instalación sin privilegios de administrador: usa {localappdata}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
; Idioma español por defecto sin preguntar
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=no
; Firma de código — la herramienta PSFirmar se pasa con /S en la línea de comandos
SignTool=PSFirmar $f
SignedUninstaller=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "Crear acceso directo en el Escritorio"; \
  GroupDescription: "Iconos adicionales:"; \
  Flags: checkedonce

[Files]
; Ejecutable principal (firmado individualmente con signonce)
Source: "{#DistDir}\{#AppExe}"; DestDir: "{app}"; \
  Flags: ignoreversion signonce

; Módulos Python empaquetados
Source: "{#DistDir}\_internal\*"; DestDir: "{app}\_internal"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Audiveris empaquetado (jpackage app: exe + app/ + runtime/)
Source: "{#DistDir}\audiveris\*"; DestDir: "{app}\audiveris"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menú de inicio
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\{#AppExe}"; \
  Comment: "Añadir nombres de notas a partituras en PDF"

; Escritorio (solo si el usuario marcó la tarea)
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\{#AppExe}"; \
  Comment: "Añadir nombres de notas a partituras en PDF"; \
  Tasks: desktopicon

[Run]
; Oferta de abrir la aplicación al finalizar
Filename: "{app}\{#AppExe}"; \
  Description: "Ejecutar {#AppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Eliminar caché de trabajo generada durante el uso
Type: filesandordirs; Name: "{localappdata}\{#AppName}"
