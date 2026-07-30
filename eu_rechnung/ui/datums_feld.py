"""Programmweites Datums-Eingabefeld mit Kalender-Popup (S-0075).

Gemeinsamer `ui`-Baustein für alle Datumsfelder der Anwendung: ein `QDateEdit` mit
Kalender-Popup (Monat und Jahr anpassbar in der Navigationsleiste, die Tage des
Monats zum Anklicken; ein Klick übernimmt das Datum und schließt das Popup). Die
Umrechnung zwischen `datetime.date` und Qt-`QDate` kapselt der Baustein über
`setze_datum` und `datum`, damit die Masken nicht mit `QDate` hantieren müssen.

**Sprache (S-0059).** Anzeigeformat und Locale folgen der UI-Sprache: Eine englische
Oberfläche zeigt `31/12/2026` und englische Monatsnamen im Popup, eine deutsche
`31.12.2026`. Beides muss zusammenpassen, denn das Feld liest die Eingabe im selben
Format zurück; ein deutsches Format neben englischen Monatsnamen wäre nicht nur
uneinheitlich, sondern irreführend.

Das Anzeigeformat steht als eigener Katalog-Schlüssel (`format.datum_qt`) neben dem des
Sichtteils (`format.datum`): Qt und Pythons `strftime` schreiben dasselbe Muster
unterschiedlich (`dd.MM.yyyy` gegen `%d.%m.%Y`). Zwei Notationen, zwei Schlüssel; eine
Umrechnung wäre mehr Code als Nutzen.

Der Wochenstart bleibt fest Montag: Er ist in allen fünf Zielsprachen üblich, und die
Locale allein setzt ihn nicht überall gleich.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import QDateEdit, QWidget

from eu_rechnung.ui.sprache import ui_sprache, ui_text


class DatumsFeld(QDateEdit):
    """Datumsfeld mit Kalender-Popup als programmweiter Bedien-Standard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat(ui_text("format.datum_qt"))
        self.setLocale(QLocale(ui_sprache()))  # Monatsnamen im Popup
        kalender = self.calendarWidget()
        if kalender is not None:
            kalender.setFirstDayOfWeek(Qt.Monday)

    def setze_datum(self, d: date) -> None:
        """Setzt das angezeigte Datum aus einem `datetime.date`."""
        self.setDate(QDate(d.year, d.month, d.day))

    def datum(self) -> date:
        """Liefert das gewählte Datum als `datetime.date`."""
        q = self.date()
        return date(q.year(), q.month(), q.day())
