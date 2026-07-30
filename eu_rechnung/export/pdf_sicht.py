"""PDF/A-Sichtteil-Erzeugung über ReportLab.

Erzeugt aus einer Rechnung des Domänenmodells den menschenlesbaren Sicht-PDF
als PDF/A-taugliche Vorstufe: ReportLab (Platypus) baut die Seite mit
eingebetteter Schrift, pypdf ergänzt den für PDF/A zwingenden OutputIntent
(sRGB-ICC) und die Dokumentsprache. Die PDF/A-3-Finalisierung (das `pdfaid`-XMP)
übernimmt factur-x bei der ZUGFeRD-Einbettung (4T-0015); dieser Schritt liefert die
Vorstufe, nicht das fertige PDF/A. Der Weg ist im Spike 4T-0006 verifiziert (E-007).

Das sRGB-ICC-Profil wird aus `eu_rechnung/ressourcen/` gebündelt geladen, damit
die Anwendung unabhängig vom Windows-Systemprofil arbeitet (Folge aus E-007).

Beide Steuerfälle wie `cii_xml.py`: Reverse-Charge (Kategorie AE) und der
Normalsteuerfall (Kategorie S mit Steuersatz, S-0079). Anschreibentext und aktive
individuelle Felder erscheinen ausschließlich hier im Sichtteil, nicht im XML
(Datenmodell.md, „Strukturiert versus nur Sichtteil").

**Sprache (S-0060).** Alle festen Texte und alle Zahlen- und Datumsformate folgen
`rechnung.rechnungssprache`, nicht der Sprache der Bedienoberfläche: Ein Anwender
arbeitet auf Deutsch und erzeugt zugleich eine englische Rechnung. Der Sichtteil ist
damit die einzige Stelle, an der die Rechnungssprache sichtbar wird, denn die Norm
lässt im CII-XML keine Sprachangabe zu (E-010); das PDF trägt sie zusätzlich als
Dokumentsprache. Sämtliche Texte kommen aus `eu_rechnung.texte`, im Modul steht
keiner fest (S-0061 AK2). Dynamische Inhalte (Anschreiben, Artikelbezeichnungen,
individuelle Felder) werden unverändert übernommen (S-0060 AK5).

Schriften: keine Standard-14-Schriften (PDF/A-Verbot). Alle Tabellen-Stile
setzen daher explizit die eingebettete Vera-Schrift, sonst fiele ReportLab auf
das nicht eingebettete Helvetica zurück.
"""

from __future__ import annotations

import functools
import importlib.resources
import os
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    create_string_object,
)

from eu_rechnung.domain import Bankverbindung, EigeneFirma, Rechnung, Skonto
from eu_rechnung.texte import Sprachkontext, normierte_sprache

# ReportLab-eigene, frei lizenzierte Schrift (Bitstream Vera), als Subset
# eingebettet. Deckt die Umlaute und Akzente der fünf Sprachen ab.
_FONTS = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
_SCHRIFT = "Vera"
_SCHRIFT_FETT = "VeraBd"
_schriften_registriert = False

# Dezente Farben für Tabellenkopf und Linien.
_FARBE_KOPF = colors.HexColor("#33475b")
_FARBE_LINIE = colors.HexColor("#999999")

# Rundungseinheit Cent (BR-CO-17), konsistent zu services.berechne_summen.
_CENT = Decimal("0.01")

# Kopfbereich: Adressfeld und Metadaten-Block nebeneinander, zusammen die Satzbreite
# (A4 minus 2 x 25 mm Rand). Die Aufteilung ist auf die *längsten* Beschriftungen aller
# fünf Sprachen ausgelegt, nicht auf die deutschen: „Periodo di riferimento" und
# „Numéro de commande" sind rund 15 % breiter als „Leistungszeitraum" und brächen in der
# ursprünglich deutschen Aufteilung (36/44 mm) um. `test_pdf_sicht` prüft, dass die
# Beschriftungen in jeder Sprache einzeilig bleiben.
_BREITE_ADRESSE = 75 * mm
_BREITE_META = 85 * mm
_BREITE_META_LABEL = 38 * mm
_BREITE_META_WERT = 47 * mm
# Innenabstand rechts in der Metadaten-Tabelle; von der Label-Breite abzuziehen.
_META_PADDING = 3


def erzeuge_sichtteil(rechnung: Rechnung, bestellnummer: str, waehrung: str) -> bytes:
    """Erzeugt den PDF/A-tauglichen Sichtteil als `bytes`.

    `bestellnummer` (BT-13) und `waehrung` (die Belegwährung) stammen aus der
    übergeordneten Bestellung; die Rechnung selbst hält sie nicht. Texte und Formate folgen
    `rechnung.rechnungssprache` (S-0060), die Währung ist davon unabhängig (S-0064 AK4).
    Rückgabe ist der Sicht-PDF mit eingebetteten Schriften, sRGB-OutputIntent und
    Dokumentsprache, aber noch ohne PDF/A-Finalisierung (die folgt über factur-x in 4T-0015).
    """
    _registriere_schriften()
    sprache = normierte_sprache(rechnung.rechnungssprache)
    roh = _baue_pdf(rechnung, bestellnummer, sprache, waehrung)
    return _ergaenze_output_intent_und_sprache(roh, sprache)


# --- Schrift und ICC ---------------------------------------------------------


def _registriere_schriften() -> None:
    global _schriften_registriert
    if _schriften_registriert:
        return
    pdfmetrics.registerFont(TTFont(_SCHRIFT, os.path.join(_FONTS, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont(_SCHRIFT_FETT, os.path.join(_FONTS, "VeraBd.ttf")))
    _schriften_registriert = True


@functools.lru_cache(maxsize=1)
def _lade_icc() -> bytes:
    """Lädt das gebündelte sRGB-ICC-Profil aus den Paket-Ressourcen."""
    return (
        importlib.resources.files("eu_rechnung")
        .joinpath("ressourcen", "sRGB2014.icc")
        .read_bytes()
    )


# --- Nutzertext-Aufbereitung -------------------------------------------------


def _p(text_: str | None) -> str:
    """Escaped einzeiligen Nutzertext für ReportLab-Paragraphen (XML-Markup)."""
    return escape(text_ or "")


def _mehrzeilig(text_: str | None) -> str:
    """Wie `_p`, aber Zeilenumbrüche werden zu <br/>."""
    return escape(text_ or "").replace("\n", "<br/>")


# --- Layout -----------------------------------------------------------------


def _stile() -> dict[str, ParagraphStyle]:
    return {
        "normal": ParagraphStyle("normal", fontName=_SCHRIFT, fontSize=9, leading=12),
        "klein": ParagraphStyle("klein", fontName=_SCHRIFT, fontSize=7.5, leading=10),
        "fett": ParagraphStyle("fett", fontName=_SCHRIFT_FETT, fontSize=9, leading=12),
        "meta_label": ParagraphStyle(
            "meta_label", fontName=_SCHRIFT_FETT, fontSize=8, leading=10
        ),
        "meta_wert": ParagraphStyle(
            "meta_wert", fontName=_SCHRIFT, fontSize=8, leading=10
        ),
        "titel": ParagraphStyle(
            "titel", fontName=_SCHRIFT_FETT, fontSize=14, leading=17, spaceAfter=8
        ),
        "rc": ParagraphStyle(
            "rc",
            fontName=_SCHRIFT_FETT,
            fontSize=9,
            leading=12,
            spaceBefore=6,
            spaceAfter=2,
        ),
    }


def _kopfbereich(rechnung: Rechnung, bestellnummer: str, st: dict, sp: Sprachkontext) -> Table:
    """Empfänger-Adressfeld links, Rechnungs-Metadaten rechts daneben."""
    kauf = rechnung.kaeufer
    adresszeilen = [kauf.name, *kauf.namenszusatz, kauf.adresse.adresszeile(),
                    f"{kauf.adresse.plz} {kauf.adresse.ort}", sp.land(kauf.adresse.land)]
    adresszeilen = [z for z in adresszeilen if z and z.strip()]
    adresse = Paragraph("<br/>".join(_p(z) for z in adresszeilen), st["normal"])

    meta = [
        (sp.t("sichtteil.rechnungsnummer"), rechnung.rechnungsnummer),
        (sp.t("sichtteil.rechnungsdatum"), sp.datum(rechnung.rechnungsdatum)),
        (sp.t("sichtteil.kundennummer"), kauf.kundennummer),
        (sp.t("sichtteil.bestellnummer"), bestellnummer),
        (
            sp.t("sichtteil.leistungszeitraum"),
            sp.t(
                "sichtteil.zeitraum",
                von=sp.datum(rechnung.leistungszeitraum.von),
                bis=sp.datum(rechnung.leistungszeitraum.bis),
            ),
        ),
    ]
    if kauf.umsatzsteuer_id:
        meta.append((sp.t("sichtteil.ust_id_kunde"), kauf.umsatzsteuer_id))
    meta_rows = [
        [Paragraph(_p(label), st["meta_label"]), Paragraph(_p(wert), st["meta_wert"])]
        for label, wert in meta
    ]
    meta_table = Table(meta_rows, colWidths=[_BREITE_META_LABEL, _BREITE_META_WERT])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _SCHRIFT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), _META_PADDING),
            ]
        )
    )

    kopf = Table([[adresse, meta_table]], colWidths=[_BREITE_ADRESSE, _BREITE_META])
    kopf.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _SCHRIFT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return kopf


def _positionstabelle(rechnung: Rechnung, st: dict, sp: Sprachkontext) -> Table:
    kopf = [
        sp.t("sichtteil.spalte_pos"),
        sp.t("sichtteil.spalte_bezeichnung"),
        sp.t("sichtteil.spalte_menge"),
        sp.t("sichtteil.spalte_einzelpreis"),
        sp.t("sichtteil.spalte_gesamtpreis"),
    ]
    zeilen = [kopf]
    for index, pos in enumerate(rechnung.positionen, start=1):
        bezeichnung = [Paragraph(_p(pos.bezeichnung), st["normal"])]
        # Positions-Leistungszeitraum (BG-26) nur zeigen, wenn er vom Kopf-Zeitraum abweicht
        # (S-0070 AK3): Der Kopf-Zeitraum steht bereits im Metadaten-Block; sonst stünde er
        # bei jeder vorbelegten Leistungs-Position erneut.
        lz = pos.leistungszeitraum
        if lz is not None and (
            lz.von != rechnung.leistungszeitraum.von
            or lz.bis != rechnung.leistungszeitraum.bis
        ):
            zeitraum = sp.t("sichtteil.zeitraum", von=sp.datum(lz.von), bis=sp.datum(lz.bis))
            bezeichnung.append(
                Paragraph(
                    _p(f"{sp.t('sichtteil.leistungszeitraum')}: {zeitraum}"), st["klein"]
                )
            )
        zeilen.append(
            [
                str(index),
                bezeichnung,
                sp.menge(pos.menge),
                sp.geld(pos.einzelpreis),
                sp.geld(pos.gesamtpreis),
            ]
        )
    tabelle = Table(zeilen, colWidths=[12 * mm, 78 * mm, 20 * mm, 25 * mm, 25 * mm])
    tabelle.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _SCHRIFT),
                ("FONTNAME", (0, 0), (-1, 0), _SCHRIFT_FETT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), _FARBE_KOPF),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#cccccc")),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, _FARBE_KOPF),
            ]
        )
    )
    return tabelle


def _summenblock(
    netto: Decimal,
    steuerbetrag: Decimal,
    brutto: Decimal,
    satz: Decimal,
    reverse_charge: bool,
    waehrung: str,
    st: dict,
    sp: Sprachkontext,
) -> Table:
    """Summenblock je Steuerfall.

    Reverse-Charge: netto = brutto = Zahlbetrag, Steuer 0. Normalfall: Nettobetrag,
    ausgewiesene Umsatzsteuer (mit Satz) und Bruttobetrag als Zahlbetrag (S-0079). Die
    Beträge tragen die Belegwährung der Bestellung (S-0064).
    """
    if reverse_charge:
        rows = [
            [sp.t("sichtteil.nettobetrag"), f"{sp.geld(netto)} {waehrung}"],
            [sp.t("sichtteil.umsatzsteuer_reverse_charge"), f"{sp.geld(Decimal('0.00'))} {waehrung}"],
            [sp.t("sichtteil.zahlbetrag"), f"{sp.geld(netto)} {waehrung}"],
        ]
    else:
        rows = [
            [sp.t("sichtteil.nettobetrag"), f"{sp.geld(netto)} {waehrung}"],
            [
                sp.t("sichtteil.umsatzsteuer_satz", satz=sp.menge(satz)),
                f"{sp.geld(steuerbetrag)} {waehrung}",
            ],
            [sp.t("sichtteil.zahlbetrag"), f"{sp.geld(brutto)} {waehrung}"],
        ]
    tabelle = Table(rows, colWidths=[55 * mm, 35 * mm], hAlign="RIGHT")
    tabelle.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _SCHRIFT),
                ("FONTNAME", (0, -1), (-1, -1), _SCHRIFT_FETT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ]
        )
    )
    return tabelle


def _skonto_absatz(
    skonto: Skonto, brutto: Decimal, rechnungsdatum: date, waehrung: str, st: dict, sp: Sprachkontext
) -> Paragraph:
    """Menschenlesbarer Skonto-Hinweis für unter die Zahlungsbedingung (S-0051 AK5).

    Weist Satz, Frist samt Stichtag, den Abzugsbetrag und den dann verbleibenden Zahlbetrag
    aus. Basis ist der fällige Betrag (BT-115, brutto), den BR-DE-18 ohne eigenes
    `BASISBETRAG`-Segment zugrunde legt; der angezeigte Abzug entspricht damit genau der ins
    XML kodierten Skonto-Zeile. Die Frist läuft ab dem Rechnungsdatum. Der Hinweis ist
    konditional und lässt die EN-Summen unberührt: Der Zahlbetrag im Summenblock bleibt
    ungekürzt (S-0051 AK3), deshalb steht der Hinweis bewusst außerhalb des Summenblocks.
    """
    abzug = (brutto * skonto.prozent / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)
    stichtag = rechnungsdatum + timedelta(days=skonto.tage)
    einheit = sp.t(
        "sichtteil.skonto_einheit_singular"
        if skonto.tage == 1
        else "sichtteil.skonto_einheit_plural"
    )
    hinweis = sp.t(
        "sichtteil.skonto_text",
        prozent=sp.prozent(skonto.prozent),
        tage=skonto.tage,
        einheit=einheit,
        stichtag=sp.datum(stichtag),
        abzug=f"{sp.geld(abzug)} {waehrung}",
        zahlbetrag=f"{sp.geld(brutto - abzug)} {waehrung}",
    )
    return Paragraph(f"<b>{sp.t('sichtteil.skonto_label')}:</b> {hinweis}", st["normal"])


def _mach_fusszeile(verk: EigeneFirma, bank: Bankverbindung | None, sp: Sprachkontext):
    """onPage-Callback: Bankverbindung und Verkäuferangaben als Fußzeile.

    `bank` ist die für die Ausgabe aufgelöste Bankverbindung (die an der Rechnung gewählte
    oder der Rückfall auf die erste, S-0065).
    """

    def zeichne(c, doc) -> None:
        c.saveState()
        links = 25 * mm
        rechts = A4[0] - 25 * mm
        y0 = 22 * mm
        c.setStrokeColor(_FARBE_LINIE)
        c.setLineWidth(0.5)
        c.line(links, y0, rechts, y0)
        c.setFont(_SCHRIFT, 7.5)
        c.setFillColor(colors.HexColor("#333333"))
        z1 = (
            f"{verk.name}, {verk.adresse.adresszeile()}, {verk.adresse.plz} "
            f"{verk.adresse.ort}, {sp.t('sichtteil.fuss_ust_id', id=verk.mehrwertsteuer_id)}"
        )
        z2 = (
            sp.t(
                "sichtteil.fuss_bank",
                bank=bank.bank,
                iban=bank.iban,
                bic=bank.bic,
                kontoinhaber=bank.kontoinhaber,
            )
            if bank
            else ""
        )
        z3 = sp.t(
            "sichtteil.fuss_kontakt",
            name=verk.kontakt_name,
            telefon=verk.telefon,
            email=verk.email,
        )
        c.drawString(links, y0 - 4 * mm, z1)
        c.drawString(links, y0 - 7.5 * mm, z2)
        c.drawString(links, y0 - 11 * mm, z3)
        c.drawRightString(rechts, y0 - 11 * mm, sp.t("sichtteil.fuss_seite", seite=doc.page))
        c.restoreState()

    return zeichne


def _baue_pdf(rechnung: Rechnung, bestellnummer: str, sprache: str, waehrung: str) -> bytes:
    sp = Sprachkontext(sprache)
    st = _stile()
    verk = rechnung.verkaeufer
    netto = sum((pos.gesamtpreis for pos in rechnung.positionen), Decimal("0.00"))
    if rechnung.reverse_charge:
        steuerbetrag = Decimal("0.00")
    else:
        steuerbetrag = (netto * rechnung.steuersatz / Decimal("100")).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )
    brutto = netto + steuerbetrag

    story = []
    absender = (
        f"{verk.name}, {verk.adresse.adresszeile()}, "
        f"{verk.adresse.plz} {verk.adresse.ort}"
    )
    story.append(Paragraph(_p(absender), st["klein"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_kopfbereich(rechnung, bestellnummer, st, sp))
    story.append(Spacer(1, 10 * mm))

    story.append(
        Paragraph(
            _p(sp.t("sichtteil.titel", nummer=rechnung.rechnungsnummer)), st["titel"]
        )
    )
    if rechnung.anschreibentext and rechnung.anschreibentext.strip():
        story.append(Paragraph(_mehrzeilig(rechnung.anschreibentext), st["normal"]))
        story.append(Spacer(1, 4 * mm))

    story.append(_positionstabelle(rechnung, st, sp))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _summenblock(
            netto, steuerbetrag, brutto, rechnung.steuersatz, rechnung.reverse_charge,
            waehrung, st, sp
        )
    )

    if rechnung.reverse_charge:
        story.append(Paragraph(sp.t("sichtteil.reverse_charge_hinweis"), st["rc"]))

    if rechnung.zahlungsbedingung and rechnung.zahlungsbedingung.strip():
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"<b>{sp.t('sichtteil.zahlungsbedingung_label')}:</b> "
                f"{_p(rechnung.zahlungsbedingung)}",
                st["normal"],
            )
        )

    # Fälligkeitsdatum aus der Zahlungsfrist, dasselbe Datum wie BT-9 im XML (S-0081).
    if rechnung.zahlungsfrist > 0:
        faellig = rechnung.rechnungsdatum + timedelta(days=rechnung.zahlungsfrist)
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                f"<b>{sp.t('sichtteil.faellig_am_label')}:</b> {sp.datum(faellig)}",
                st["normal"],
            )
        )

    # Skonto menschenlesbar, weil es im XML nur maschinell kodiert steht (S-0051 AK5).
    if rechnung.skonto is not None:
        story.append(Spacer(1, 2 * mm))
        story.append(
            _skonto_absatz(rechnung.skonto, brutto, rechnung.rechnungsdatum, waehrung, st, sp)
        )

    aktive = [f for f in rechnung.individuelle_felder if f.aktiv]
    if aktive:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(_p(sp.t("sichtteil.weitere_angaben")), st["fett"]))
        for feld in aktive:
            story.append(
                Paragraph(f"{_p(feld.name)}: {_p(feld.wert)}", st["normal"])
            )

    puffer = BytesIO()
    doc = SimpleDocTemplate(
        puffer,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=20 * mm,
        bottomMargin=30 * mm,
        title=sp.t("sichtteil.titel", nummer=rechnung.rechnungsnummer),
        author=verk.name,
        subject=sp.t("sichtteil.dokumentart"),
        creator="EU-Rechnung",
    )
    bank = rechnung.bankverbindung or (
        verk.bankverbindungen[0] if verk.bankverbindungen else None
    )
    fuss = _mach_fusszeile(verk, bank, sp)
    doc.build(story, onFirstPage=fuss, onLaterPages=fuss)
    return puffer.getvalue()


# --- PDF/A-OutputIntent (verifizierter Spike-Pfad, E-007) -------------------


def _ergaenze_output_intent_und_sprache(pdf_bytes: bytes, sprache: str) -> bytes:
    """Ergänzt den OutputIntent mit gebündeltem sRGB-ICC und die Dokumentsprache.

    PDF/A verlangt einen OutputIntent mit eingebettetem Zielprofil; factur-x
    setzt ihn nicht (im Bibliotheks-Quellcode verifiziert, E-007). factur-x
    klont beim Einbetten das gesamte Dokument, der OutputIntent bleibt erhalten.

    Im selben Schritt wird `/Lang` gesetzt, die Dokumentsprache des PDF (S-0060). Sie
    tritt an die Stelle des normseitig unzulässigen XML-Sprachattributs (E-010) und ist
    die einzige Stelle, an der die Rechnungssprache maschinenlesbar im Beleg steht.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    icc_stream = DecodedStreamObject()
    icc_stream.set_data(_lade_icc())
    icc_stream[NameObject("/N")] = NumberObject(3)  # 3 Komponenten = RGB
    icc_ref = writer._add_object(icc_stream)

    output_intent = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): create_string_object(
                "sRGB IEC61966-2.1"
            ),
            NameObject("/Info"): create_string_object("sRGB IEC61966-2.1"),
            NameObject("/DestOutputProfile"): icc_ref,
        }
    )
    oi_ref = writer._add_object(output_intent)
    writer._root_object[NameObject("/OutputIntents")] = ArrayObject([oi_ref])
    writer._root_object[NameObject("/Lang")] = create_string_object(sprache)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
