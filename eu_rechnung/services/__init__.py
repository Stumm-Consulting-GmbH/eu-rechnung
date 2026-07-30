"""Anwendungslogik: Datenbestand, Rechnungserfassung und -erstellung.

Die Service-Schicht ist UI-frei und kapselt für die Oberfläche das Laden des
Datenbestands (mit Erstlauf-Seed), die Vorbelegung und das Anlegen einer Rechnung
sowie die Erstellung der Ausgabedateien mit Statusfortschreibung. Sie arbeitet auf
`domain`, nutzt `persistence` und reicht bei der Erstellung an `export`.
"""

from eu_rechnung.services.anschreiben import effektiver_anschreibentext
from eu_rechnung.services.artikel import artikel_referenziert, pruefe_artikel
from eu_rechnung.services.befund import Befund
from eu_rechnung.services.bestellung import (
    pruefe_bestellung,
    verbrauch_artikel,
    verbrauch_gesamt,
)
from eu_rechnung.services.datenbestand import erzeuge_leeren_datenbestand, erzeuge_seed
from eu_rechnung.services.einstellungen import pruefe_einstellungen, waehrung_referenziert
from eu_rechnung.services.firma import pruefe_firma
from eu_rechnung.services.kunde import pruefe_kunde
from eu_rechnung.services.sprache import (
    STANDARD_RECHNUNGSSPRACHE,
    effektive_rechnungssprache,
)
from eu_rechnung.services.waehrung import effektive_waehrung
from eu_rechnung.services.erstellung import (
    STANDARD_AUSGABE,
    ErstellungsErgebnis,
    Format,
    erstelle_ausgaben,
    zielordner_der_rechnung,
)
from eu_rechnung.services.uebersicht import RechnungsZeile, alle_rechnungen
from eu_rechnung.services.rechnung import (
    RechnungsnummerDublette,
    ValidierungsFehler,
    berechne_gesamtpreis,
    berechne_summen,
    finde_rechnungsnummer_dublette,
    lege_rechnung_an,
    obergrenzen_warnungen,
    pruefe_kaeufer,
    pruefe_rechnung,
    pruefe_rechnung_fuer_ausgabe,
    vorbelege_rechnung,
    warne_rechnung,
)

__all__ = [
    "Befund",
    "erzeuge_seed",
    "erzeuge_leeren_datenbestand",
    "STANDARD_AUSGABE",
    "ErstellungsErgebnis",
    "Format",
    "RechnungsZeile",
    "alle_rechnungen",
    "erstelle_ausgaben",
    "zielordner_der_rechnung",
    "ValidierungsFehler",
    "berechne_gesamtpreis",
    "berechne_summen",
    "lege_rechnung_an",
    "pruefe_kaeufer",
    "pruefe_rechnung",
    "pruefe_rechnung_fuer_ausgabe",
    "warne_rechnung",
    "obergrenzen_warnungen",
    "finde_rechnungsnummer_dublette",
    "RechnungsnummerDublette",
    "pruefe_firma",
    "pruefe_artikel",
    "artikel_referenziert",
    "pruefe_kunde",
    "pruefe_bestellung",
    "verbrauch_gesamt",
    "verbrauch_artikel",
    "vorbelege_rechnung",
    "effektiver_anschreibentext",
    "effektive_rechnungssprache",
    "effektive_waehrung",
    "STANDARD_RECHNUNGSSPRACHE",
    "pruefe_einstellungen",
    "waehrung_referenziert",
]
