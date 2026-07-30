"""Auflösung des effektiven Anschreibentexts entlang der Vererbungskaskade (S-0034).

UI-frei und rein lesend: liefert den Text der speziellsten gesetzten Ebene und fällt
sonst auf den globalen Standard zurück. Dient der Vorbelegung beim Rechnung-Anlegen
(S-0029) und der Vorschau je Ebene in den Kunde- und Bestellungs-Masken (S-0036).
"""

from __future__ import annotations

from eu_rechnung.domain import Bestellung, Einstellungen, Kunde


def effektiver_anschreibentext(
    einstellungen: Einstellungen,
    *,
    kunde: Kunde | None = None,
    bestellung: Bestellung | None = None,
) -> str:
    """Der Anschreibentext der speziellsten gesetzten Ebene, sonst der globale Standard.

    Reihenfolge speziell → allgemein: Bestellung, Kunde, globaler Standard. Eine nicht
    übergebene oder auf `None` gesetzte Ebene wird übersprungen (Erben); der globale
    Standard ist der garantierte Rückfall. Die Funktion verändert keine Ebenen-Werte.

    Für die Vorschau je Ebene wird die eigene Ebene weggelassen: der für einen Kunden
    geerbte Text ist `effektiver_anschreibentext(einstellungen)` (nur der Standard), der
    für eine Bestellung `effektiver_anschreibentext(einstellungen, kunde=…)`.
    """
    if bestellung is not None and bestellung.anschreibentext is not None:
        return bestellung.anschreibentext
    if kunde is not None and kunde.anschreibentext is not None:
        return kunde.anschreibentext
    return einstellungen.standard_anschreibentext
