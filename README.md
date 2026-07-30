# SCG EU E-Rechnung Generator

Windows-Werkzeug, das elektronische Rechnungen nach der EU-Norm **EN 16931** aus
strukturiert erfassten Daten erzeugt, in den beiden in Deutschland gängigen
Ausprägungen:

- **XRechnung** als reines XML (Syntax CII, XRechnung 3.0.2),
- **ZUGFeRD** als PDF/A-3 mit eingebettetem XML, Profil EN 16931 (Comfort).

Die Daten werden in einer Oberfläche erfasst (eigene Firma, Artikel, Kunden,
Bestellungen, Rechnungen) und liegen lokal in einer Datei je Firma. Es gibt keine
Cloud, keinen Server und keine Netzwerkverbindung.

## Einordnung

Dieses Werkzeug ist für den **eigenen Gebrauch eines Einzelunternehmens** entstanden und
wird hier als Quellcode veröffentlicht, weil er für andere nützlich sein kann. Es ist
kein Produkt:

- **Einzelplatz unter Windows 11**, ein Benutzer, kein Mehrbenutzerbetrieb, keine
  Rechteverwaltung, kein Server.
- **Kein Versand.** Das Werkzeug erzeugt die Dateien; das Verschicken geschieht außerhalb.
- **Keine Buchhaltung.** Keine offenen Posten, kein Mahnwesen, keine Schnittstelle zu
  einer Finanzbuchhaltung.
- **Keine automatische Aktualisierung**, keine Code-Signatur.

## Umfang

- Stammdaten: eigene Firma mit mehreren Bankverbindungen, Artikel, Kunden, Bestellungen
  mit gültigen Artikeln und Obergrenzen.
- Rechnungserfassung mit Vorbelegung aus der Bestellung, freien und aus Artikeln
  übernommenen Positionen sowie einem Leistungszeitraum je Position.
- **Reverse-Charge** (Steuerschuldnerschaft des Leistungsempfängers) und Normalsteuerfall.
- **Skonto** und Zahlungsmodalitäten, vererbt von der Bestellung.
- **Mehrwährungsfähigkeit** mit Vererbungskaskade und währungsabhängiger Bankverbindung.
- **Fünf Sprachen** (Deutsch, Englisch, Italienisch, Französisch, Spanisch), getrennt für
  Oberfläche und Rechnung: Aus einer deutschen Oberfläche entsteht eine spanische Rechnung.
- Rechnungsübersicht über alle Belege mit Status und Ablageort.
- Ablage je Firma in einer Datei (Endung `.scgr`, Inhalt JSON), atomar geschrieben und
  gegen Parallelzugriff gesperrt.

Die Programmversion steht in `eu_rechnung/__init__.py`.

## Bauen und Ausführen

Voraussetzung ist **Python 3.13 oder neuer**. Die Abhängigkeiten stehen in
`pyproject.toml` und werden mit dem Paket installiert.

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m eu_rechnung.app
```

Die ausführbare Datei entsteht mit **PyInstaller** aus der versionierten Spec-Datei; sie
ist die einzige Quelle des Builds, eine Befehlszeile mit Schaltern wird nicht gepflegt:

```
.\.venv\Scripts\python.exe -m pip install -e .[build]
.\.venv\Scripts\pyinstaller.exe --noconfirm eu-rechnung.spec
```

Ergebnis ist ein Verzeichnis unter `dist/` mit der `.exe` und ihren Begleitdateien, rund
256 MB. Der Umfang stammt zum größten Teil aus zwei Abhängigkeiten (Saxon über factur-x,
Qt über PySide6) und lässt sich nicht sinnvoll drücken. Die Verzeichnis-Variante ist
bewusst gewählt: Eine Einzeldatei entpackt bei jedem Start rund 250 MB und braucht knapp
dreimal so lange bis zum sichtbaren Fenster.

Das Setup-Programm entsteht mit **Inno Setup 6** aus `eu-rechnung-setup.iss` und verpackt
das Ergebnis des vorherigen Schritts:

```
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" eu-rechnung-setup.iss
```

## Tests

```
.\.venv\Scripts\python.exe -m pytest
```

Die Suite läuft **ohne Java** durch: Domänenmodell, Persistenz, Erzeugungskette (CII,
Sichtteil, ZUGFeRD), die eingebaute XSD-Prüfung und die Oberfläche (offscreen, ohne
sichtbares Fenster).

Die **Goldstandard-Prüfungen** gegen den KoSIT-Validator (XRechnung) und veraPDF (PDF/A)
sind über die Marker `kosit` und `verapdf` angebunden. Sie brauchen eine Java-Laufzeit und
die beiden Werkzeuge in einem projektlokalen Ordner `werkzeuge/`, der nicht Teil dieses
Repositorys ist. Fehlt beides, **überspringt** die Suite diese Tests mit Begründung, statt
zu scheitern. Die erwarteten Pfade stehen in `tests/conftest.py`:

- `werkzeuge/kosit/validator-<Version>-standalone.jar` und die XRechnung-Prüfkonfiguration
  unter `werkzeuge/kosit/config/` (entwickelt gegen Validator 1.6.2 und die Konfiguration
  für XRechnung 3.0.2),
- `werkzeuge/verapdf/verapdf.bat` (entwickelt gegen veraPDF 1.30.2).

Zusätzlich lässt sich die **gefrorene Anwendung** selbst prüfen: `bundle-selbsttest.spec`
baut ein Prüf-Binary mit derselben Datensammlung wie die Auslieferung, das die
Erzeugungskette ohne Oberfläche fährt; `skripte/bundle_validieren.py` prüft dessen
Ausgaben gegen XSD, KoSIT und veraPDF. Damit ist belegbar, dass die gebündelten Ressourcen
zur Laufzeit auch gefunden werden.

## Normkonformität

Die Konformität ist geprüft, nicht behauptet. Der Maßstab ist im Test der KoSIT-Validator
für XRechnung und veraPDF für PDF/A-3b; beide laufen als Teil der Suite über die
erzeugten Dateien. Zwei Punkte, die dabei gelernt wurden und im Code festgehalten sind:

- Das XML trägt **keine Sprachangabe**. Das EN-16931-CII-Schematron verbietet sie
  (CII-SR-019, CII-DT-013, CII-DT-014); ein Gegentest hält fest, dass KoSIT dasselbe XML
  mit gesetztem `ram:LanguageID` ablehnt. Die Rechnungssprache wirkt deshalb auf den
  sichtbaren PDF-Teil und auf die Dokumentsprache des PDF, nicht auf das XML.
- Die Schematron-Prüfung von factur-x ist beim Einbetten **abgeschaltet**, die
  XSD-Prüfung bleibt aktiv: factur-x prüft gegen die generische Factur-X-Variante und
  lehnt die XRechnung-CIUS-Kennung ab. Maßgeblich ist hier KoSIT.

## Aufbau

```
eu_rechnung/
├── app.py            Einstiegspunkt
├── texte.py          Sprachkatalog (JSON je Sprache, kein Qt-tr())
├── ui/               PySide6-Oberfläche: sieben Reiter, Masken, geteilte Bausteine
├── domain/           Datenmodell
├── persistence/      JSON-Repository, Schema, Dateisperre, App-Konfiguration
├── services/         Fachlogik, oberflächenfrei
├── ressourcen/       ICC-Profil, Icon, Sprachdateien (siehe ressourcen/README.md)
└── export/           CII-XML, PDF-Sichtteil, ZUGFeRD-Einbettung, Validierung
```

Die `export`- und `services`-Schichten kennen keine Oberfläche und sind eigenständig
testbar. Die Sprache wird jedem Aufruf explizit übergeben statt aus globalem Zustand
gezogen; nur so kann aus einer deutschen Oberfläche eine fremdsprachige Rechnung entstehen.

**Zu den Kennungen im Code:** Kommentare und Docstrings verweisen an vielen Stellen auf
Kennungen wie `S-0054`, `4T-0181` oder `E-008`. Das sind Anforderungen, Aufgaben und
Entscheidungen aus der projektinternen Ablage, die nicht mitveröffentlicht wird. Sie
belegen, warum eine Stelle so aussieht, wie sie aussieht; zum Verständnis des Codes sind
sie nicht nötig.

## Lizenz

Der Quellcode steht unter der **Apache-Lizenz 2.0**; der Text liegt unverändert in
[LICENSE](LICENSE). Nutzung, Veränderung und Weitergabe sind erlaubt, auch kommerziell,
solange Urheber- und Lizenzhinweis erhalten bleiben und Änderungen kenntlich gemacht
werden. Die Lizenz gewährt ausdrücklich eine Patentlizenz und schließt Gewährleistung und
Haftung aus.

Copyright 2026 Stumm-Consulting GmbH, Liestal (Schweiz).

Die eingebundenen Fremdkomponenten und ihre Lizenzen stehen in [NOTICE](NOTICE). Sie sind
**nicht** Teil dieses Repositorys: Hier liegt Quellcode, kein Programmpaket. Wer ein
gebautes Paket weitergibt, hat die Lizenzpflichten dieser Komponenten selbst zu erfüllen.

## Beiträge, Unterstützung, Haftung

Das Projekt entsteht für den eigenen Gebrauch. Es gibt **keine Zusage** für Unterstützung,
Fehlerbehebung, Weiterentwicklung oder die Bearbeitung von Anfragen und Beiträgen. Wer den
Code nutzt, tut das auf eigenes Risiko und in eigener Verantwortung, insbesondere was die
steuer- und handelsrechtliche Ordnungsmäßigkeit der erzeugten Rechnungen im eigenen
Anwendungsfall angeht. Es gelten die Haftungs- und Gewährleistungsausschlüsse der
Apache-Lizenz 2.0.
