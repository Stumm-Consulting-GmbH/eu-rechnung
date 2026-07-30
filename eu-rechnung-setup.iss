; Setup-Programm des SCG EU E-Rechnung Generators (4T-0186, S-0054 und S-0086)
;
; Diese Datei ist die Quelle des Installers und liegt versioniert im Repository. Sie
; verpackt das Ergebnis von `eu-rechnung.spec` (Verzeichnis-Variante) zu einer
; installierbaren Setup-Datei. Anleitung und Beschaffung des Übersetzers stehen in der
; Architektur, Abschnitt „Bau des Setup-Programms".
;
; Bauen (im Projekt-Wurzelverzeichnis):
;   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" eu-rechnung-setup.iss
;
; Ergebnis: `dist\setup\SCG-EU-E-Rechnung-Generator-Setup-<Version>.exe`
;
; Der Uebersetzer liegt je nach Installationsart unter
; `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (benutzerbezogen, so von winget
; installiert) oder unter `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` (systemweit).

#define Quelle "dist\SCG-EU-E-Rechnung-Generator"
#define Programm "SCG-EU-E-Rechnung-Generator.exe"
; Produktangaben aus der ausführbaren Datei lesen, die sie ihrerseits zur Build-Zeit aus
; `eu_rechnung/__init__.py` erhält (siehe skripte/build_gemeinsam.py). So gibt es weiterhin
; nur eine Pflegestelle für Version, Produktname und Herausgeber.
#define Version GetStringFileInfo(Quelle + "\" + Programm, FILE_VERSION)
#define Produkt GetStringFileInfo(Quelle + "\" + Programm, PRODUCT_NAME)
#define Herausgeber GetStringFileInfo(Quelle + "\" + Programm, COMPANY_NAME)
; Dateiname-Stamm ohne Leerzeichen, abgeleitet vom Programm-Dateinamen: Der Anzeigename
; mit Leerzeichen gehört in den Assistenten, nicht in Dateinamen und Befehlszeilen.
#define DateiStamm RemoveFileExt(Programm)
; Eigener Dateityp der Firma-Dateien (S-0071: eine Firma je Datei, Endung .scgr)
#define DateiTyp "SCGEURechnung.Firma"

[Setup]
; Feste Kennung, einmalig erzeugt: Daran erkennt Windows die Anwendung bei einem Update
; und beim Deinstallieren. Sie darf sich nie ändern.
AppId={{19B1315C-7B07-48E6-9CF9-1984149D1E9B}
AppName={#Produkt}
AppVersion={#Version}
AppPublisher={#Herausgeber}
VersionInfoVersion={#Version}

; Installation ins Benutzerprofil: Ein Ziel unterhalb von `Programme` verlangt
; Administratorrechte, und S-0054 will gerade keinen Zwang dazu. Das Zielverzeichnis
; bleibt im Assistenten wählbar.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#Produkt}
DefaultGroupName={#Produkt}
DisableProgramGroupPage=yes

; Der Assistent zeigt eine Seite zur Auswahl des Zielverzeichnisses (S-0054 AK1).
DisableDirPage=no
AllowNoIcons=yes
SetupIconFile=eu_rechnung\ressourcen\icon.ico
UninstallDisplayIcon={app}\{#Programm}
UninstallDisplayName={#Produkt}
; Der Explorer soll die neue Dateizuordnung sofort übernehmen (S-0054 AK2).
ChangesAssociations=yes
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
OutputDir=dist\setup
OutputBaseFilename={#DateiStamm}-Setup-{#Version}
; Windows 11 als Zielplattform (S-0052).
MinVersion=10.0.22000
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; Dieselben fünf Sprachen, die die Anwendung selbst führt (F-0016). Deutsch steht zuerst
; und ist damit die Vorauswahl.
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "englisch"; MessagesFile: "compiler:Default.isl"
Name: "italienisch"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "franzoesisch"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanisch"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Das gesamte Build-Verzeichnis, samt Unterordner `_internal` mit Bibliotheken und
; gebündelten Assets. `ignoreversion` gilt bewusst für alles: Die Dateien gehören zu
; diesem Bundle und werden gemeinsam ersetzt, nicht einzeln nach Version verglichen.
Source: "{#Quelle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Produkt}"; Filename: "{app}\{#Programm}"
Name: "{group}\{cm:UninstallProgram,{#Produkt}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Produkt}"; Filename: "{app}\{#Programm}"; Tasks: desktopicon

[Registry]
; Dateizuordnung der Firma-Dateien. `HKA` wählt bei einer Installation ohne
; Administratorrechte automatisch den Benutzerzweig (HKCU), sodass die Zuordnung ohne
; Rechte-Anhebung gesetzt werden kann.
;
; Beim Deinstallieren werden ausschließlich diese Einträge entfernt. Die `.scgr`-Dateien
; des Anwenders liegen außerhalb des Installationsverzeichnisses (E-012) und werden nie
; angefasst; ebenso bleibt die App-Konfiguration (Zuletzt-geöffnet-Liste,
; Autostart-Vermerk) erhalten: Ihr Verlust wäre nur Komfortverlust, ihr Entfernen aber
; nicht rückholbar.
Root: HKA; Subkey: "Software\Classes\.scgr"; ValueType: string; ValueName: ""; ValueData: "{#DateiTyp}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#DateiTyp}"; ValueType: string; ValueName: ""; ValueData: "{cm:DateiTypName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#DateiTyp}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#Programm},0"
; Der Öffnen-Befehl übergibt den Dateipfad als erstes Argument; die Programmseite dazu
; ist 4T-0185 (`app.ermittle_uebergabe_pfad`).
Root: HKA; Subkey: "Software\Classes\{#DateiTyp}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#Programm}"" ""%1"""

[CustomMessages]
deutsch.DateiTypName=SCG EU E-Rechnung Firma-Datei
englisch.DateiTypName=SCG EU E-Rechnung company file
italienisch.DateiTypName=File aziendale SCG EU E-Rechnung
franzoesisch.DateiTypName=Fichier de société SCG EU E-Rechnung
spanisch.DateiTypName=Archivo de empresa SCG EU E-Rechnung

[Run]
Filename: "{app}\{#Programm}"; Description: "{cm:LaunchProgram,{#Produkt}}"; Flags: nowait postinstall skipifsilent
