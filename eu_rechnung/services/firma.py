"""Firma-Validierung: zweistufige Pflicht- und Formatprüfung (S-0004).

Prüft die eigene Firma beim Speichern. Die Pflichtfelder richten sich nach dem
Schalter `xrechnung_aktiv`: bei inaktiver XRechnung nur die für den Verkäufer nach
EN 16931 verpflichtenden Felder (Firmenname, Land, USt-ID), bei aktiver zusätzlich
die strengeren XRechnung-Pflichtfelder (vollständige Adresse, Kontakt, E-Mail,
mindestens eine Bankverbindung). Zusätzlich werden Formate geprüft: IBAN über die
Modulo-97-Prüfziffer, E-Mail nach Grundmuster, BIC auf 8 oder 11 Stellen. Die übrigen
Felder werden nur auf Vorhandensein geprüft (S-0001, S-0004).
"""

from __future__ import annotations

import re

from eu_rechnung.domain import EigeneFirma
from eu_rechnung.services.befund import Befund

_EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _iban_gueltig(iban: str) -> bool:
    """Strukturprüfung plus Modulo-97-Prüfziffer nach ISO 13616."""
    wert = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{1,30}", wert):
        return False
    umgestellt = wert[4:] + wert[:4]
    # Buchstaben zu Zahlen (A=10 ... Z=35), Ziffern bleiben; dann Rest bei 97.
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    return int(zahl) % 97 == 1


def _bic_gueltig(bic: str) -> bool:
    """BIC hat 8 oder 11 alphanumerische Stellen (SWIFT-Format grob geprüft)."""
    return bool(re.fullmatch(r"[A-Z0-9]{8}([A-Z0-9]{3})?", bic.replace(" ", "").upper()))


def pruefe_firma(firma: EigeneFirma) -> list[Befund]:
    """Prüft die Firma stufenabhängig. Leere Liste bedeutet gültig.

    Die Feldschlüssel der Befunde decken sich mit den Maskenfeldern (``name``, ``land``,
    ``mwst``, ``strasse`` ...), damit die Oberfläche den Hinweis feld-nah darstellen kann.
    Alle Bankverbindungs-Befunde tragen den Sammelschlüssel ``bank``, weil die Maske die
    Bankverbindungen in einer Liste führt und nicht als Einzelfelder; die laufende Nummer
    steckt als Platzhalter ``nr`` im Befund. Die Prüf-Logik selbst (zweistufige Pflicht,
    IBAN/E-Mail/BIC-Format) ist unverändert.
    """
    befunde: list[Befund] = []
    xr = firma.xrechnung_aktiv

    # EN-Pflicht (immer)
    if not firma.name.strip():
        befunde.append(Befund("name", "firma.fehlt_name"))
    if not firma.adresse.land.strip():
        befunde.append(Befund("land", "allgemein.fehlt_land"))
    if not firma.mehrwertsteuer_id.strip():
        befunde.append(Befund("mwst", "firma.fehlt_mwst"))

    # XRechnung-Pflicht (zusätzlich)
    if xr:
        if not firma.adresse.strasse.strip():
            befunde.append(Befund("strasse", "allgemein.xr_pflicht_strasse"))
        if not firma.adresse.plz.strip():
            befunde.append(Befund("plz", "allgemein.xr_pflicht_plz"))
        if not firma.adresse.ort.strip():
            befunde.append(Befund("ort", "allgemein.xr_pflicht_ort"))
        if not firma.kontakt_name.strip():
            befunde.append(Befund("kontakt", "firma.xr_pflicht_kontakt"))
        if not firma.telefon.strip():
            befunde.append(Befund("telefon", "firma.xr_pflicht_telefon"))
        if not firma.email.strip():
            befunde.append(Befund("email", "allgemein.xr_pflicht_email"))

    # E-Mail-Format (wenn befüllt)
    if firma.email.strip() and not _EMAIL_MUSTER.match(firma.email.strip()):
        befunde.append(Befund("email", "allgemein.email_format"))

    # Bankverbindungen (Sammelschlüssel "bank")
    if xr and not firma.bankverbindungen:
        befunde.append(Befund("bank", "firma.xr_pflicht_bank"))
    for i, bank in enumerate(firma.bankverbindungen, start=1):
        if not bank.kontoinhaber.strip():
            befunde.append(Befund("bank", "firma.bank_fehlt_kontoinhaber", {"nr": i}))
        if not bank.iban.strip():
            befunde.append(Befund("bank", "firma.bank_fehlt_iban", {"nr": i}))
        elif not _iban_gueltig(bank.iban):
            befunde.append(Befund("bank", "firma.bank_iban_ungueltig", {"nr": i}))
        if not bank.waehrung.strip():
            befunde.append(Befund("bank", "firma.bank_fehlt_waehrung", {"nr": i}))
        if bank.bic.strip() and not _bic_gueltig(bank.bic):
            befunde.append(Befund("bank", "firma.bank_bic_ungueltig", {"nr": i}))
    return befunde
