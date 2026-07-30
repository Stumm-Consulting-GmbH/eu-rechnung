"""Tests der Befund-Brücke zwischen Fachlogik und Sprachkatalog (S-0061, 4T-0130).

Die `pruefe_*`-Funktionen nennen Katalog-Schlüssel statt fertiger Texte; aufgelöst wird
erst beim Anzeigen. Diese Naht ist zur Laufzeit still: Ein vertippter Schlüssel fällt erst
auf, wenn genau dieser Befund einmal auftritt, ein vergessener Platzhalter zeigt dem
Anwender ein rohes `{nr}` im Satz. Beide Fälle fängt hier der Quelltext-Scan, nicht der
Anwender.

Der Scan liest die `Befund(...)`-Aufrufe aus dem AST der Service-Module. Das erfasst auch
die Zweige, die kein Test je auslöst, und ist damit die Absicherung von AK1 und AK5:
`services` trägt nur noch Schlüssel, und jeder davon steht im Katalog.
"""

from __future__ import annotations

import ast
import pathlib
from string import Formatter

import pytest

from eu_rechnung.domain import Adresse, Bankverbindung, EigeneFirma
from eu_rechnung.services import pruefe_firma
from eu_rechnung.texte import RUECKFALL, SPRACHEN, katalog, text
from eu_rechnung.ui.sprache import befund_text, setze_ui_sprache

_SERVICES = pathlib.Path(__file__).resolve().parent.parent / "eu_rechnung" / "services"


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Der UI-Sprach-Zustand ist prozessweit; nach jedem Test zurückstellen."""
    yield
    setze_ui_sprache(RUECKFALL)


def _befund_aufrufe() -> list[tuple[str, int, str, set[str] | None]]:
    """Alle `Befund(...)`-Aufrufe der Service-Module als (modul, zeile, schluessel, werte).

    `werte` ist `None`, wenn Schlüssel oder Werte nicht literal im Aufruf stehen und der
    Scan sie deshalb nicht lesen kann. Solche Aufrufe unterliefen die Prüfungen darunter
    stillschweigend, deshalb verbietet sie `test_alle_aufrufe_sind_statisch_lesbar`.
    """
    treffer = []
    for pfad in sorted(_SERVICES.glob("*.py")):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and getattr(knoten.func, "id", None) == "Befund"):
                continue
            schluessel_knoten = knoten.args[1] if len(knoten.args) > 1 else None
            if not isinstance(schluessel_knoten, ast.Constant):
                treffer.append((pfad.name, knoten.lineno, "<nicht literal>", None))
                continue
            werte: set[str] | None = set()
            if len(knoten.args) > 2:
                dict_knoten = knoten.args[2]
                if isinstance(dict_knoten, ast.Dict) and all(
                    isinstance(k, ast.Constant) for k in dict_knoten.keys
                ):
                    werte = {k.value for k in dict_knoten.keys}
                else:
                    werte = None
            treffer.append((pfad.name, knoten.lineno, schluessel_knoten.value, werte))
    return treffer


def _platzhalter(vorlage: str) -> set[str]:
    """Die Platzhalter-Namen einer Textvorlage."""
    return {name for _, name, _, _ in Formatter().parse(vorlage) if name}


def test_es_gibt_ueberhaupt_befund_aufrufe():
    """Absicherung des Scans selbst: Ein leerer Scan bestünde jeden Test darunter."""
    assert len(_befund_aufrufe()) > 50


def test_alle_aufrufe_sind_erfassbar():
    """Jeder `Befund(`-Aufruf im Quelltext wird vom AST-Scan auch erfasst.

    Sonst liefe der Schlüssel-Test an einem dynamisch gebauten Aufruf vorbei, ohne dass es
    auffiele.
    """
    im_text = sum(
        zeile.count("Befund(")
        for pfad in _SERVICES.glob("*.py")
        if pfad.name != "befund.py"
        for zeile in pfad.read_text(encoding="utf-8").splitlines()
        if not zeile.lstrip().startswith("#")
    )
    assert len(_befund_aufrufe()) == im_text


def test_alle_aufrufe_sind_statisch_lesbar():
    """Schlüssel und Werte stehen literal im Aufruf, sonst prüft hier niemand mehr mit.

    Ein über eine Variable gereichtes Werte-Wörterbuch ist zur Laufzeit gleichwertig, für
    den Scan aber blind: Der Platzhalter-Abgleich fiele für diesen Aufruf still aus.
    """
    blind = [
        f"{modul}:{zeile} {schluessel}"
        for modul, zeile, schluessel, werte in _befund_aufrufe()
        if werte is None
    ]
    assert not blind, "Befund-Aufrufe ohne literale Angaben:\n" + "\n".join(blind)


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_jeder_befund_schluessel_steht_im_katalog(sprache):
    """AK5: Ein Schlüssel ohne Eintrag zeigte dem Anwender einen Absturz statt einer Meldung."""
    fehlend = [
        f"{modul}:{zeile} -> {schluessel}"
        for modul, zeile, schluessel, _ in _befund_aufrufe()
        if schluessel not in katalog(sprache)
    ]
    assert not fehlend, f"{sprache}.json fehlen Befund-Schlüssel:\n" + "\n".join(fehlend)


def test_platzhalter_der_aufrufe_decken_sich_mit_dem_text():
    """Werte im Code und Platzhalter im Text müssen zueinander passen.

    Fehlt ein Wert, bliebe ein rohes `{nr}` im Satz stehen (`str.format` wird gar nicht erst
    aufgerufen); ein Wert zu viel wirft `KeyError` erst zur Anzeigezeit.
    """
    abweichungen = []
    for modul, zeile, schluessel, werte in _befund_aufrufe():
        erwartet = _platzhalter(katalog(RUECKFALL)[schluessel])
        if werte != erwartet:
            abweichungen.append(
                f"{modul}:{zeile} {schluessel}: Code {sorted(werte)} != Text {sorted(erwartet)}"
            )
    assert not abweichungen, "Platzhalter passen nicht:\n" + "\n".join(abweichungen)


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_platzhalter_stehen_in_jeder_sprache(sprache):
    """Eine Übersetzung, die `{nr}` verliert, verschluckt die Positionsangabe still."""
    abweichungen = []
    for _, _, schluessel, _ in _befund_aufrufe():
        deutsch = _platzhalter(katalog(RUECKFALL)[schluessel])
        eigene = _platzhalter(katalog(sprache)[schluessel])
        if deutsch != eigene:
            abweichungen.append(f"{schluessel}: {sorted(eigene)} != de {sorted(deutsch)}")
    assert not abweichungen, f"{sprache}.json:\n" + "\n".join(abweichungen)


def _firma_ohne_iban() -> EigeneFirma:
    """Firma mit einer Bankverbindung ohne IBAN: erzeugt einen parametrisierten Befund."""
    return EigeneFirma(
        name="Muster Consulting GmbH",
        adresse=Adresse(strasse="Musterstrasse", plz="4000", ort="Basel", land="CH"),
        mehrwertsteuer_id="CHE-999.999.999 MWST",
        email="kontakt@example.com",
        telefon="+41 44 123 45 67",
        kontakt_name="Max Muster",
        bankverbindungen=[
            Bankverbindung(
                kontoinhaber="Muster Consulting GmbH", bank="Beispielbank", iban="", bic="",
                waehrung="EUR",
            )
        ],
        xrechnung_aktiv=True,
    )


def test_parametrisierter_befund_traegt_die_laufende_nummer():
    """Die Nummer steckt als Wert im Befund, nicht im vorformatierten Text (AK3)."""
    befunde = pruefe_firma(_firma_ohne_iban())
    iban = next(b for b in befunde if b.schluessel == "firma.bank_fehlt_iban")
    assert iban.feld == "bank"
    assert iban.werte == {"nr": 1}


@pytest.mark.parametrize(
    "sprache, erwartet",
    [
        ("de", "Bankverbindung 1: Die IBAN fehlt."),
        ("en", "Bank account 1: The IBAN is missing."),
        ("it", "Coordinate bancarie 1: manca l'IBAN."),
        ("fr", "Coordonnées bancaires 1 : l'IBAN est absent."),
        ("es", "Datos bancarios 1: falta el IBAN."),
    ],
)
def test_parametrisierter_befund_loest_je_sprache_auf(sprache, erwartet):
    """AK2: Derselbe Befund aus derselben Prüfung, fünf Sprachen, Nummer an ihrem Platz."""
    befunde = pruefe_firma(_firma_ohne_iban())
    iban = next(b for b in befunde if b.schluessel == "firma.bank_fehlt_iban")
    assert text(iban.schluessel, sprache, **iban.werte) == erwartet


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_befund_text_folgt_der_eingestellten_ui_sprache(sprache):
    """Die Oberfläche löst in ihrer Sprache auf; die Prüfung selbst weiß davon nichts."""
    setze_ui_sprache(sprache)
    befunde = pruefe_firma(_firma_ohne_iban())
    iban = next(b for b in befunde if b.schluessel == "firma.bank_fehlt_iban")
    assert befund_text(iban) == text("firma.bank_fehlt_iban", sprache, nr=1)


def test_befund_ohne_werte_loest_zum_fertigen_satz_auf():
    """Der Regelfall ohne Platzhalter: Schlüssel rein, ganzer Satz raus."""
    setze_ui_sprache("es")
    firma = _firma_ohne_iban()
    firma.name = ""
    name = next(b for b in pruefe_firma(firma) if b.feld == "name")
    assert befund_text(name) == "Falta la razón social."
