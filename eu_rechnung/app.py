"""Einstiegspunkt der EU-Rechnung-Anwendung (PySide6).

Startet die grafische Oberfläche. Das Fenster öffnet im Leerzustand ohne aktive Firma
(dokument-basiertes Modell, S-0003); war beim letzten Mal eine Firma aktiv und ist ihre
Datei ladbar, wird sie automatisch geladen und aktiviert. Wurde die Firma dagegen
bewusst geschlossen (S-0083), startet die Anwendung leer. Andernfalls führt die
Leerfläche des Fensters zum Anlegen oder Öffnen einer Firma. Die fachliche Logik liegt
in `services`, die Norm- und Erzeugungslogik in `export`; die Oberfläche ruft nur.
"""

from __future__ import annotations

import importlib.resources
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QLibraryInfo,
    QLocale,
    QStandardPaths,
    QTranslator,
)
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QApplication

from eu_rechnung.domain import Datenbestand
from eu_rechnung.persistence import PersistenzFehler, lade, sperre
from eu_rechnung.persistence.konfiguration import lade_konfiguration
from eu_rechnung.ui.hauptfenster import HauptFenster
from eu_rechnung.ui.sprache import setze_ui_sprache

_ANWENDUNGSNAME = "SCG EU E-Rechnung Generator"
_ORGANISATION = "Stumm-Consulting"
_KONFIG_DATEINAME = "konfiguration.json"

# Der aktuell installierte Qt-Translator. Qt stapelt Translatoren, statt sie zu ersetzen,
# und befragt sie der Reihe nach; ein zuvor installierter bliebe also wirksam, wo der neue
# nichts liefert. Beim Anwendungsstart fällt das nicht auf (ein einziger Aufruf), wohl aber
# in Tests und Prüfskripten, die mehrere Sprachen durchlaufen.
_qt_translator: QTranslator | None = None


def lade_programm_icon() -> QIcon:
    """Das Programm-Icon aus der gebündelten Ressource (S-0086).

    Gelesen werden die **Bytes**, nicht ein Dateipfad. Ein `QIcon`, das nur einen Pfad
    hält, lädt sein Bild erst bei Bedarf; in der späteren `.exe` liegt die Ressource im
    Bundle, und ein zwischenzeitlich nicht mehr erreichbarer Pfad ergäbe ein leeres
    Symbol. Über die Bytes ist das Icon vollständig geladen, sobald diese Funktion
    zurückkehrt, unabhängig davon, wie das Bundle seine Ressourcen bereitstellt. Der
    Zugriff läuft über denselben Weg wie bei Sprachdateien und ICC-Profil
    (`importlib.resources`).

    Die Datei trägt mehrere Auflösungen (16 bis 256 px). Alle werden übernommen, damit
    Windows je Zusammenhang (Taskleiste, Fenstertitel, Alt-Tab) die passende wählt,
    statt eine einzige zu skalieren.
    """
    roh = (
        importlib.resources.files("eu_rechnung")
        .joinpath("ressourcen", "icon.ico")
        .read_bytes()
    )
    # Das QByteArray muss eine eigene Variable sein und bis zum letzten Lesezugriff
    # leben: QBuffer hält in Qt nur einen Zeiger darauf. Inline geschrieben
    # (`QBuffer(QByteArray(roh))`) sammelt Python das Zwischenergebnis sofort ein, und
    # der Lesezugriff läuft in eine Speicherschutzverletzung.
    daten = QByteArray(roh)
    puffer = QBuffer(daten)
    puffer.open(QIODevice.ReadOnly)
    leser = QImageReader(puffer)
    icon = QIcon()
    while True:
        bild = leser.read()
        if bild.isNull():
            break
        icon.addPixmap(QPixmap.fromImage(bild))
        if not leser.jumpToNextImage():
            break
    return icon


def standard_konfig_pfad() -> Path:
    """Plattformgerechter Pfad der App-Konfigurationsdatei (Zuletzt-geöffnet-Liste)."""
    basis = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    return Path(basis) / _KONFIG_DATEINAME


def installiere_qt_uebersetzung(app: QApplication, sprache: str) -> bool:
    """Lädt die Qt-Standard-Übersetzungen der UI-Sprache (Ja/Nein/Abbrechen in Standarddialogen).

    Ohne sie zeigen Qt-eigene Dialoge (die Knöpfe von QMessageBox, Dateidialoge) englische
    Beschriftungen, was neben der übersetzten Oberfläche uneinheitlich wirkt. Betrifft nur
    die von Qt mitgebrachten Texte; die Texte der Anwendung selbst kommen aus dem
    Sprachkatalog (`eu_rechnung.texte`). Der Translator wird an die App gebunden (Parent),
    damit er nicht vorzeitig eingesammelt wird.

    Ein zuvor installierter Translator wird zuvor entfernt, damit die Funktion wiederholbar
    ist: Qt stapelt Translatoren und befragt sie der Reihe nach, sodass sonst ein alter
    einspränge, wo der neue nichts liefert. Für Englisch ist das der Regelfall, weil
    `qtbase_en.qm` als Quellsprache keine eigenen Texte trägt; ohne das Entfernen zeigte
    eine englische Oberfläche die deutschen Knöpfe des Vorgängers.

    Gibt zurück, ob die Übersetzung geladen und installiert wurde. `False` ist kein Fehler:
    Fehlt eine `qtbase`-Datei für die Sprache, bleiben die Qt-Dialoge bei ihrer
    Quellsprache Englisch und die Anwendung läuft normal weiter.
    """
    global _qt_translator
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    translator = QTranslator(app)
    pfad = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(sprache), "qtbase", "_", pfad):
        app.installTranslator(translator)
        _qt_translator = translator
        return True
    return False


def ermittle_start_firma(konfig_pfad: Path | str) -> tuple[Datenbestand, Path] | None:
    """Lädt die zuletzt aktive Firma-Datei, falls vermerkt und ladbar.

    Maßgeblich ist der Vermerk `zuletzt_aktiv`, **nicht** die Zuletzt-geöffnet-Liste:
    Wurde die Firma bewusst geschlossen (S-0083), steht dort nichts, und die Anwendung
    startet leer, obwohl die Firma als Komfort-Eintrag in der Liste bleibt. Ohne diese
    Trennung machte der nächste Start das Schließen wieder rückgängig.

    Ist die vermerkte Datei verschwunden oder defekt, wird ebenfalls leer gestartet,
    statt ersatzweise eine ältere Firma zu öffnen: Ein stiller Wechsel auf einen anderen
    Datenbestand wäre überraschender als eine leere Anwendung. Der Anwender wählt dann
    über „Zuletzt geöffnet".
    """
    konfig = lade_konfiguration(konfig_pfad)
    if konfig.zuletzt_aktiv is None:
        return None
    pfad = Path(konfig.zuletzt_aktiv)
    if not pfad.is_file():
        return None
    try:
        return lade(pfad), pfad
    except PersistenzFehler:
        return None


def ermittle_uebergabe_pfad(argv: Sequence[str]) -> Path | None:
    """Der beim Aufruf übergebene Dateipfad, falls vorhanden (S-0054).

    Betrachtet wird ausschließlich das **erste** Argument, denn genau so ruft Windows die
    Anwendung bei einem Doppelklick auf eine verknüpfte Datei auf. Beginnt es mit einem
    Bindestrich, ist es ein Schalter (etwa Qt-eigene Optionen) und kein Dateipfad; dann
    startet die Anwendung wie ohne Argument. Weitere Argumente werden nicht ausgewertet,
    was zugleich verhindert, dass der Wert einer Option als Dateipfad missdeutet wird.
    """
    if len(argv) < 2 or not argv[1] or argv[1].startswith("-"):
        return None
    return Path(argv[1])


def ui_sprache_der_datei(pfad: Path | str) -> str | None:
    """Die UI-Sprache einer Firma-Datei, ohne sie zu aktivieren; `None` wenn unlesbar.

    Kostet einen zusätzlichen Lesevorgang, und das ist beabsichtigt: Die UI-Sprache steht
    in den Einstellungen der Firma-Datei (S-0058) und muss **vor** dem Fensteraufbau
    feststehen, während die übergebene Datei erst danach über den gemeinsamen Ladeweg
    geöffnet wird (mit Sperre und Meldungen). Ohne diesen Vorgriff stünde eine spanisch
    eingestellte Firma hinter einer deutschen Oberfläche.

    Fehler werden geschluckt: Ist die Datei nicht lesbar, bleibt es bei der
    Standardsprache, und die Meldung dazu gibt später der Ladeweg.
    """
    try:
        return lade(pfad).einstellungen.ui_sprache
    except PersistenzFehler:
        return None


class StartZustand(NamedTuple):
    """Woraus die Anwendung startet: übergebene Datei, Autostart-Firma, UI-Sprache."""

    uebergabe: Path | None
    start: tuple[Datenbestand, Path] | None
    ui_sprache: str | None


def ermittle_startzustand(argv: Sequence[str], konfig_pfad: Path | str) -> StartZustand:
    """Entscheidet, welche Firma den Start bestimmt, und woher die UI-Sprache kommt.

    **Ein übergebener Pfad hat Vorrang vor dem Autostart-Vermerk.** Wer eine Firma-Datei
    doppelklickt, will diese Firma sehen und nicht die zuletzt aktive. Ohne Argument
    bleibt das bisherige Verhalten unverändert (S-0083).

    Als reine Funktion herausgezogen, damit der Vorrang prüfbar ist, ohne die Anwendung
    zu starten.
    """
    uebergabe = ermittle_uebergabe_pfad(argv)
    if uebergabe is not None:
        return StartZustand(uebergabe, None, ui_sprache_der_datei(uebergabe))
    start = ermittle_start_firma(konfig_pfad)
    return StartZustand(None, start, start[0].einstellungen.ui_sprache if start else None)


def main() -> None:
    """Startet die Anwendung im Leerzustand, mit Programm-Icon und Startfirma.

    Das Hauptfenster öffnet ohne aktive Firma (Leerzustand, S-0003). Ist eine
    zuletzt geöffnete, noch ladbare Firma-Datei vorhanden und nicht bereits in einer
    anderen Instanz gesperrt (S-0073), wird sie beim Start automatisch aktiviert und
    ihre Sperre erworben. Andernfalls bleibt das Fenster leer, bis der Anwender über
    Menü oder Leerfläche eine Firma anlegt oder öffnet.

    Die UI-Sprache steht in den Einstellungen und damit in der Firma-Datei (S-0058).
    Deshalb wird die Startfirma **vor** dem Fensteraufbau ermittelt und die Sprache aus
    ihr gesetzt; ohne Startfirma bleibt es bei Deutsch (S-0059).

    Wird ein Dateipfad übergeben, etwa durch einen Doppelklick auf eine verknüpfte
    `.scgr`-Datei (S-0054), hat er Vorrang vor dem Autostart-Vermerk. Geöffnet wird er
    **nach** `show()` über den gemeinsamen Ladeweg des Hauptfensters, damit dessen
    Meldungen (belegte Datei, verwaiste Sperre, defekte Datei) ein sichtbares
    Elternfenster haben.
    """
    app = QApplication(sys.argv)
    app.setApplicationName(_ANWENDUNGSNAME)
    app.setOrganizationName(_ORGANISATION)
    # Anwendungsweit statt am Hauptfenster: So tragen auch Dialoge und der Leerzustand
    # das Symbol, ohne es einzeln setzen zu müssen (S-0086).
    app.setWindowIcon(lade_programm_icon())
    konfig_pfad = standard_konfig_pfad()
    zustand = ermittle_startzustand(sys.argv, konfig_pfad)
    sprache = setze_ui_sprache(zustand.ui_sprache)
    installiere_qt_uebersetzung(app, sprache)
    if zustand.start is not None:
        bestand, pfad = zustand.start
        if sperre.erwerbe_sperre(pfad) is sperre.SperrStatus.ERWORBEN:
            fenster = HauptFenster(bestand, daten_pfad=pfad, konfig_pfad=konfig_pfad)
        else:
            # In einer anderen Instanz aktiv oder verwaist gesperrt: leer starten;
            # die Konfliktbehandlung (Meldung/Übernahme) erfolgt bei manueller Öffnung.
            fenster = HauptFenster(konfig_pfad=konfig_pfad)
    else:
        fenster = HauptFenster(konfig_pfad=konfig_pfad)
    fenster.show()
    if zustand.uebergabe is not None:
        # Erst nach show(): Der gemeinsame Ladeweg kann Dialoge zeigen (belegte Datei,
        # verwaiste Sperre, defekte Datei), und die brauchen ein sichtbares Elternfenster.
        fenster.oeffne_uebergebene_firma(zustand.uebergabe)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
