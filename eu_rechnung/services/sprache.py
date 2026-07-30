"""Auflösung der effektiven Rechnungssprache entlang der Vererbungskaskade (S-0060).

UI-frei und rein lesend: liefert die Sprache der speziellsten gesetzten Ebene und fällt
sonst auf Deutsch zurück. Dient der Vorbelegung beim Rechnung-Anlegen (S-0058 AK3) und der
Vorschau je Ebene in den Kunde- und Bestellungs-Masken.

Dieselbe Mechanik wie beim Anschreibentext (`services.anschreiben`, S-0034) mit einem
Unterschied: Die Kaskade hat keinen Wurzelwert in den Einstellungen. `Einstellungen.ui_sprache`
ist die Sprache der Bedienoberfläche (S-0059) und darf hier nicht einfließen, sonst würde ein
Wechsel der Arbeitssprache die Sprache erzeugter Belege verändern. Der garantierte Rückfall
ist stattdessen fest Deutsch.
"""

from __future__ import annotations

from eu_rechnung.domain import Bestellung, Kunde
from eu_rechnung.texte import RUECKFALL

#: Rückfall ohne jede gesetzte Ebene: Deutsch (S-0060 AK1).
STANDARD_RECHNUNGSSPRACHE = RUECKFALL


def effektive_rechnungssprache(
    *,
    kunde: Kunde | None = None,
    bestellung: Bestellung | None = None,
) -> str:
    """Die Rechnungssprache der speziellsten gesetzten Ebene, sonst Deutsch.

    Reihenfolge speziell → allgemein: Bestellung, Kunde, Rückfall Deutsch. Eine nicht
    übergebene oder auf `None` gesetzte Ebene wird übersprungen (Erben). Die Funktion
    verändert keine Ebenen-Werte.

    Für die Vorschau je Ebene wird die eigene Ebene weggelassen: Die für einen Kunden
    geerbte Sprache ist `effektive_rechnungssprache()` (nur der Rückfall), die für eine
    Bestellung `effektive_rechnungssprache(kunde=…)`.

    Die Rechnung selbst taucht hier nicht auf: Sie erbt nicht, sondern hält die beim Anlegen
    aufgelöste Sprache als eigene, editierbare Kopie (Kopie-Prinzip, S-0058).
    """
    if bestellung is not None and bestellung.rechnungssprache is not None:
        return bestellung.rechnungssprache
    if kunde is not None and kunde.rechnungssprache is not None:
        return kunde.rechnungssprache
    return STANDARD_RECHNUNGSSPRACHE
