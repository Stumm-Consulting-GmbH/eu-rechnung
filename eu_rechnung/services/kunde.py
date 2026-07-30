"""Kunde-Validierung (UI-frei): zweistufige Pflicht- und Eindeutigkeitsprüfung.

Prüft einen Kunden beim Speichern (S-0013/S-0014). Die Pflichtfelder richten sich – wie bei
der Firma – nach dem dokumentweiten Schalter `xrechnung_aktiv` der eigenen Firma: bei
inaktiver XRechnung nur die für den Käufer nach EN 16931 verpflichtenden Felder (Name,
Land; die USt-ID zusätzlich bei gesetztem Reverse-Charge), bei aktiver XRechnung zusätzlich
die strengeren (vollständige Adresse, E-Mail). Die Kundennummer ist Pflicht und eindeutig;
der Name wird nicht auf Eindeutigkeit geprüft (zwei Kunden dürfen gleich heißen). Die
Befunde tragen je einen Feldschlüssel für die feld-nahe Anzeige.
"""

from __future__ import annotations

import re

from eu_rechnung.domain import Datenbestand, Kunde
from eu_rechnung.services.befund import Befund

_EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _nummer_schluessel(nummer: str) -> str:
    """Vergleichsform der Kundennummer: getrimmt und ohne Groß-/Kleinschreibung (S-0013)."""
    return nummer.strip().casefold()


def pruefe_kunde(
    kunde: Kunde,
    datenbestand: Datenbestand,
    *,
    ignoriere_id: str | None = None,
) -> list[Befund]:
    """Prüft einen Kunden stufenabhängig und feldweise. Leere Liste bedeutet gültig.

    Feldschlüssel: ``"kundennummer"``, ``"name"``, ``"strasse"``, ``"plz"``, ``"ort"``,
    ``"land"``, ``"email"``, ``"umsatzsteuer_id"``. Die Pflicht-Stufe folgt
    ``datenbestand.eigene_firma.xrechnung_aktiv``; ``ignoriere_id`` nimmt beim Ändern den
    Kunden selbst von der Nummern-Dubletten-Prüfung aus (S-0014).
    """
    befunde: list[Befund] = []
    xr = datenbestand.eigene_firma.xrechnung_aktiv

    nummer = kunde.kundennummer.strip()
    if not nummer:
        befunde.append(Befund("kundennummer", "allgemein.fehlt_kundennummer"))
    else:
        schluessel = _nummer_schluessel(nummer)
        for anderer in datenbestand.kunden:
            if anderer.id == ignoriere_id:
                continue
            if _nummer_schluessel(anderer.kundennummer) == schluessel:
                befunde.append(Befund("kundennummer", "kunde.nummer_doppelt"))
                break

    # EN-Pflicht (immer)
    if not kunde.name.strip():
        befunde.append(Befund("name", "kunde.fehlt_name"))
    if not kunde.adresse.land.strip():
        befunde.append(Befund("land", "allgemein.fehlt_land"))
    if kunde.reverse_charge and not kunde.umsatzsteuer_id.strip():
        befunde.append(Befund("umsatzsteuer_id", "kunde.rc_pflicht_ustid"))

    # XRechnung-Pflicht (zusätzlich)
    if xr:
        if not kunde.adresse.strasse.strip():
            befunde.append(Befund("strasse", "allgemein.xr_pflicht_strasse"))
        if not kunde.adresse.plz.strip():
            befunde.append(Befund("plz", "allgemein.xr_pflicht_plz"))
        if not kunde.adresse.ort.strip():
            befunde.append(Befund("ort", "allgemein.xr_pflicht_ort"))
        if not kunde.email.strip():
            befunde.append(Befund("email", "allgemein.xr_pflicht_email"))

    # E-Mail-Format (wenn befüllt)
    if kunde.email.strip() and not _EMAIL_MUSTER.match(kunde.email.strip()):
        befunde.append(Befund("email", "allgemein.email_format"))

    return befunde
