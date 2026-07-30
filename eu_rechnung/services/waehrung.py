"""Auflösung der effektiven Währung entlang der Vererbungskaskade (S-0063).

UI-frei und rein lesend: liefert die Währung der speziellsten gesetzten Ebene und fällt
sonst auf die Standardwährung zurück. Dient der Vorbelegung der Belegwährung beim
Bestellung-Anlegen und der geerbten Vorschau in der Kunde-Maske.

Dieselbe Mechanik wie beim Anschreibentext (`services.anschreiben`, S-0034) mit einem
Wurzelwert in den Einstellungen, anders als bei der Sprache (`services.sprache`): Die
Standardwährung ist eine echte fachliche Vorgabe. Die Kaskade endet an der Bestellung; deren
`waehrung` ist nach dem Speichern der feste Wert des Belegs (S-0017, S-0023). Die Funktion
nimmt daher bewusst keine Bestellung entgegen: Ein Beleg löst nichts auf, er trägt seine
Währung selbst.
"""

from __future__ import annotations

from eu_rechnung.domain import Einstellungen, Kunde


def effektive_waehrung(einstellungen: Einstellungen, *, kunde: Kunde | None = None) -> str:
    """Die Währung der speziellsten gesetzten Ebene, sonst die Standardwährung.

    Reihenfolge speziell → allgemein: Kunde, globale Standardwährung. Eine nicht übergebene
    oder auf `None` gesetzte Kundenebene wird übersprungen (Erben); die Standardwährung ist
    der garantierte Rückfall. Die Funktion verändert keine Ebenen-Werte.

    Für die Vorschau je Ebene wird die eigene Ebene weggelassen: Die für einen Kunden geerbte
    Währung ist `effektive_waehrung(einstellungen)` (nur die Standardwährung).
    """
    if kunde is not None and kunde.waehrung is not None:
        return kunde.waehrung
    return einstellungen.standardwaehrung
