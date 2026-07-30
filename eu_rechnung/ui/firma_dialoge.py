"""Datei-Dialoge der Firma-Verwaltung: Speicherort und Öffnen wählen, anlegen, laden.

Gemeinsame Bausteine für den Anwendungsstart (`app`) und das Menü „Datei" im
Hauptfenster, damit das Anlegen und Öffnen einer Firma an beiden Stellen identisch
abläuft (S-0071). Die Funktionen kapseln die Standard-Dialoge des Betriebssystems
(Speichern/Öffnen mit Endung `.scgr`, Startort „Dokumente") samt Fehler-Meldung und
liefern den geladenen beziehungsweise angelegten Datenbestand mit seinem Pfad.

Vor dem Laden oder Anlegen wird die Datei-Sperre gesichert (S-0073): eine bereits in
einer anderen Instanz geöffnete Datei wird nicht erneut geöffnet (Meldung), eine
verwaiste Sperre kann der Anwender nach Bestätigung übernehmen.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from eu_rechnung.domain import Datenbestand
from eu_rechnung.persistence import PersistenzFehler, lade, speichere, sperre
from eu_rechnung.services import erzeuge_leeren_datenbestand
from eu_rechnung.ui.sprache import ui_text

#: Dateiendung der Firma-Dateien (JSON-Inhalt mit eigener Endung). Technisch und daher
#: nicht übersetzt; die Beschreibung im Dateifilter kommt aus dem Sprachkatalog.
DATEI_ENDUNG = ".scgr"


def _dokumente_ordner() -> str:
    """Plattformgerechter „Dokumente"-Ordner als Startort der Datei-Dialoge."""
    return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or ""


def waehle_speicherort(parent: QWidget | None = None) -> Path | None:
    """Fragt Speicherort und Namen einer neuen Firma-Datei ab (Vorschlag `.scgr`).

    Gibt den Zielpfad zurück (Endung `.scgr` bei Bedarf ergänzt) oder `None` bei
    Abbruch.
    """
    vorschlag = str(
        Path(_dokumente_ordner())
        / f"{ui_text('firma_dialog.datei_vorschlag')}{DATEI_ENDUNG}"
    )
    name, _ = QFileDialog.getSaveFileName(
        parent,
        ui_text("firma_dialog.neue_firma_titel"),
        vorschlag,
        ui_text("firma_dialog.datei_filter"),
    )
    if not name:
        return None
    pfad = Path(name)
    if pfad.suffix.lower() != DATEI_ENDUNG:
        pfad = pfad.with_suffix(DATEI_ENDUNG)
    return pfad


def waehle_oeffnen(parent: QWidget | None = None) -> Path | None:
    """Fragt eine bestehende Firma-Datei über den Öffnen-Dialog ab (oder `None`)."""
    name, _ = QFileDialog.getOpenFileName(
        parent,
        ui_text("firma_dialog.oeffnen_titel"),
        _dokumente_ordner(),
        ui_text("firma_dialog.datei_filter"),
    )
    return Path(name) if name else None


def _stelle_sperre_sicher(pfad: Path, parent: QWidget | None) -> bool:
    """Sichert die Datei-Sperre vor dem Öffnen oder Anlegen einer Firma (S-0073).

    Gibt `True` zurück, wenn die Datei verwendet werden darf (Sperre erworben oder
    verwaiste Sperre nach Bestätigung übernommen), sonst `False` (in einer anderen
    Instanz belegt oder Übernahme abgelehnt).
    """
    status = sperre.erwerbe_sperre(pfad)
    if status is sperre.SperrStatus.ERWORBEN:
        return True
    if status is sperre.SperrStatus.BELEGT:
        QMessageBox.warning(
            parent,
            ui_text("firma_dialog.belegt_titel"),
            ui_text("firma_dialog.belegt_text"),
        )
        return False
    # VERWAIST: Sperr-Datei ohne laufende Instanz, Übernahme anbieten (AK3).
    antwort = QMessageBox.question(
        parent,
        ui_text("firma_dialog.verwaist_titel"),
        ui_text("firma_dialog.verwaist_text"),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if antwort == QMessageBox.Yes:
        sperre.uebernimm_sperre(pfad)
        return True
    return False


def lege_neue_firma_an(parent: QWidget | None = None) -> tuple[Datenbestand, Path] | None:
    """Wählt einen Speicherort, legt eine leere Firma an und schreibt sie (AK1).

    Der leere Datenbestand wird sofort in die gewählte Datei geschrieben, damit die
    Firma-Datei existiert und in die Zuletzt-geöffnet-Liste aufgenommen werden kann;
    der Anwender füllt die Firma anschließend über die Maske. Vor dem Schreiben wird
    die Datei-Sperre gesichert (S-0073), damit eine bereits in einer anderen Instanz
    geöffnete Datei nicht überschrieben wird. Gibt `(Datenbestand, Pfad)` zurück oder
    `None` bei Abbruch, Sperr-Konflikt oder Schreibfehler.
    """
    pfad = waehle_speicherort(parent)
    if pfad is None:
        return None
    if not _stelle_sperre_sicher(pfad, parent):
        return None
    bestand = erzeuge_leeren_datenbestand()
    try:
        speichere(bestand, pfad)
    except PersistenzFehler as fehler:
        sperre.gib_sperre_frei(pfad)
        QMessageBox.warning(
            parent,
            ui_text("firma_dialog.anlegen_fehler_titel"),
            ui_text("firma_dialog.anlegen_fehler_text", fehler=fehler),
        )
        return None
    return bestand, pfad


def oeffne_firma(parent: QWidget | None = None) -> tuple[Datenbestand, Path] | None:
    """Wählt eine bestehende Firma-Datei über den Öffnen-Dialog und lädt sie (AK2)."""
    pfad = waehle_oeffnen(parent)
    if pfad is None:
        return None
    return lade_firma(pfad, parent)


def lade_firma(pfad: Path, parent: QWidget | None = None) -> tuple[Datenbestand, Path] | None:
    """Sichert die Sperre und lädt eine Firma-Datei; bei Ladefehler Meldung und `None`.

    Ist die Datei in einer anderen Instanz belegt oder wird eine verwaiste Sperre
    nicht übernommen, wird nicht geladen (`None`). Schlägt das Laden fehl, wird die
    zuvor erworbene Sperre wieder freigegeben.
    """
    if not _stelle_sperre_sicher(pfad, parent):
        return None
    try:
        bestand = lade(pfad)
    except PersistenzFehler as fehler:
        sperre.gib_sperre_frei(pfad)
        QMessageBox.warning(
            parent,
            ui_text("firma_dialog.oeffnen_fehler_titel"),
            ui_text("firma_dialog.oeffnen_fehler_text", fehler=fehler),
        )
        return None
    return bestand, pfad
