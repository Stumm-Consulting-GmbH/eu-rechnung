"""Lesende Gesamt-Übersicht aller Rechnungen der Firma-Datei (S-0055, UI-frei).

Stellt die Rechnungen aller Kunden und Bestellungen flach mit ihrem Kontext bereit. Die
Hierarchie Kunde → Bestellung → Rechnung trägt den Kontext strukturell, die Rechnung selbst
kennt weder Kunde noch Bestellnummer; dieses Modul bündelt beides, damit die Oberfläche
nicht selbst durch die Hierarchie laufen muss (Muster wie `_BestellZeile` im
Bestellung-Reiter, hier UI-frei und damit testbar ohne Qt).

Die Sicht ist rein lesend: Sie liefert Verweise auf die echten Objekte, verändert aber
nichts. Bearbeitet wird in der Rechnungserfassung (F-0005).
"""

from __future__ import annotations

from typing import NamedTuple

from eu_rechnung.domain import Bestellung, Datenbestand, Kunde, Rechnung


class RechnungsZeile(NamedTuple):
    """Eine Rechnung mit ihrem Kontext (Kunde und Bestellung) für die Übersicht."""

    kunde: Kunde
    bestellung: Bestellung
    rechnung: Rechnung


def alle_rechnungen(datenbestand: Datenbestand) -> list[RechnungsZeile]:
    """Alle Rechnungen der Firma-Datei, nach Rechnungsdatum absteigend (S-0055 AK1/AK2).

    Die Sortierung ist der Ausgangszustand der Übersicht (neueste zuerst); der Anwender
    kann in der Oberfläche umsortieren. Ohne Rechnungen ist das Ergebnis leer.
    """
    zeilen = [
        RechnungsZeile(kunde, bestellung, rechnung)
        for kunde in datenbestand.kunden
        for bestellung in kunde.bestellungen
        for rechnung in bestellung.rechnungen
    ]
    return sorted(zeilen, key=lambda z: z.rechnung.rechnungsdatum, reverse=True)
