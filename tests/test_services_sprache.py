"""Tests der Rechnungssprach-Kaskade (`services.sprache`, S-0060 AK1), Java-frei.

Spiegelt die Struktur von `test_services_anschreiben.py`: dieselbe Vererbungsmechanik
(speziellste gesetzte Ebene gewinnt, `None` erbt), aber mit festem Rückfall Deutsch statt
eines Wurzelwerts in den Einstellungen.
"""

from __future__ import annotations

from datetime import date

from eu_rechnung.domain import Adresse, Bestellung, Kunde
from eu_rechnung.services import effektive_rechnungssprache


def _kunde(**anpassungen) -> Kunde:
    basis = dict(
        id="kun-1",
        kundennummer="D10002",
        name="Beispiel Kunde GmbH",
        adresse=Adresse(strasse="Musterstraße 5", plz="80331", ort="München", land="DE"),
        email="rechnungseingang@example.org",
        umsatzsteuer_id="DE123456789",
        reverse_charge=True,
    )
    basis.update(anpassungen)
    return Kunde(**basis)


def _bestellung(**anpassungen) -> Bestellung:
    basis = dict(
        id="best-1",
        bestellnummer="4500000001",
        beginn_datum=date(2026, 5, 1),
        ende_datum=date(2026, 5, 31),
        zahlungsfrist=30,
        zahlungsbedingung="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
    )
    basis.update(anpassungen)
    return Bestellung(**basis)


def test_ohne_jede_ebene_deutsch():
    """Rückfall ohne Angabe ist Deutsch."""
    assert effektive_rechnungssprache() == "de"


def test_nicht_gesetzte_ebenen_erben():
    """Beide Ebenen auf None (Default): Rückfall Deutsch."""
    assert effektive_rechnungssprache(kunde=_kunde(), bestellung=_bestellung()) == "de"


def test_kunde_setzt_die_sprache():
    kunde = _kunde(rechnungssprache="en")
    assert effektive_rechnungssprache(kunde=kunde) == "en"
    # Die Bestellung erbt, weil sie selbst nichts setzt.
    assert effektive_rechnungssprache(kunde=kunde, bestellung=_bestellung()) == "en"


def test_bestellung_ueberschreibt_den_kunden():
    """Die speziellste gesetzte Ebene gewinnt."""
    ergebnis = effektive_rechnungssprache(
        kunde=_kunde(rechnungssprache="en"), bestellung=_bestellung(rechnungssprache="fr")
    )
    assert ergebnis == "fr"


def test_bestellung_allein_gesetzt():
    ergebnis = effektive_rechnungssprache(kunde=_kunde(), bestellung=_bestellung(rechnungssprache="it"))
    assert ergebnis == "it"


def test_vorschau_je_ebene_laesst_die_eigene_ebene_weg():
    """Die für einen Kunden geerbte Sprache ist der Rückfall, die für eine Bestellung der Kunde."""
    kunde = _kunde(rechnungssprache="es")
    assert effektive_rechnungssprache() == "de"  # was der Kunde erben würde
    assert effektive_rechnungssprache(kunde=kunde) == "es"  # was die Bestellung erben würde


def test_aufloesung_veraendert_die_ebenen_nicht():
    kunde = _kunde(rechnungssprache="en")
    bestellung = _bestellung()
    effektive_rechnungssprache(kunde=kunde, bestellung=bestellung)
    assert kunde.rechnungssprache == "en"
    assert bestellung.rechnungssprache is None
