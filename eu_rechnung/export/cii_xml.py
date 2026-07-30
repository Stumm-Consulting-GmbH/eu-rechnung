"""CII-XML-Export nach EN 16931 (XRechnung-CIUS) über drafthorse.

Erzeugt aus einer Rechnung des Domänenmodells das CII-XML, das sowohl als
reine XRechnung dient als auch von factur-x in das ZUGFeRD-PDF eingebettet
wird. Das Mapping folgt Datenmodell.md (Abschnitt EN-16931-Mapping).

Umgesetzt sind beide Steuerfälle: Reverse-Charge (Kategorie AE, Satz 0,
Befreiungsgrund VATEX-EU-AE) und der Normalsteuerfall (Kategorie S mit
Steuersatz, S-0079). Die Steuerkategorie ergibt sich aus dem Reverse-Charge-
Kennzeichen der Rechnung; alle Positionen tragen einheitlich dieselbe Kategorie.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem

from eu_rechnung.domain import Adresse, Rechnung

# XRechnung-CIUS-3.0-Kennung (BT-24). Steuert die Szenario-Auswahl im
# KoSIT-Validator.
GUIDELINE_XRECHNUNG = (
    "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
)

# Geschäftsprozess (BT-23), XRechnung-Pflicht (PEPPOL-EN16931-R001).
BUSINESS_PROCESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# UN/ECE-Einheit "one" (generisch); eine Einheit je Position folgt in v1.
EINHEIT_STUECK = "C62"

# Rundungseinheit Cent (BR-CO-17), konsistent zu services.berechne_summen.
_CENT = Decimal("0.01")


def _bt20_text(rechnung: Rechnung) -> str:
    r"""BT-20-Text: freie Zahlungsbedingung, bei gesetztem Skonto plus BR-DE-18-Zeile.

    Die Skonto-Zeile lautet `#SKONTO#TAGE=n#PROZENT=n.nn#` (Prozent mit genau zwei
    Nachkommastellen und Punkt als Trenner) und steht auf einer eigenen Zeile. BR-DE-18
    verlangt zusätzlich einen abschließenden Zeilenumbruch nach der Skonto-Angabe: KoSIT
    prüft `tokenize(., '#.+#')[last()]` gegen `^\s*\n` und wertet einen Verstoß als
    fatal. Ohne Skonto bleibt der Text unverändert.
    """
    if rechnung.skonto is None:
        return rechnung.zahlungsbedingung
    prozent = rechnung.skonto.prozent.quantize(_CENT, rounding=ROUND_HALF_UP)
    skonto_zeile = f"#SKONTO#TAGE={rechnung.skonto.tage}#PROZENT={prozent:f}#\n"
    freier_text = rechnung.zahlungsbedingung.rstrip()
    return f"{freier_text}\n{skonto_zeile}" if freier_text else skonto_zeile


def _setze_adresse(ziel, adresse: Adresse) -> None:
    ziel.line_one = adresse.strasse
    ziel.postcode = adresse.plz
    ziel.city_name = adresse.ort
    ziel.country_id = adresse.land


def erzeuge_cii(rechnung: Rechnung, bestellnummer: str, waehrung: str) -> bytes:
    """Erzeugt das EN-16931-CII-XML (XRechnung-CIUS) als bytes.

    `bestellnummer` (BT-13) und `waehrung` (BT-5, die Belegwährung) stammen aus der
    übergeordneten Bestellung; die Rechnung selbst hält sie nicht.
    """
    # Steuerkategorie aus dem Reverse-Charge-Kennzeichen: AE (Satz 0, Pflicht-
    # Befreiungsgrund VATEX-EU-AE) oder S (Normalsteuerfall mit Satz > 0, S-0079).
    if rechnung.reverse_charge:
        kategorie = "AE"
        satz = Decimal("0")
    else:
        kategorie = "S"
        satz = rechnung.steuersatz

    doc = Document()
    doc.context.guideline_parameter.id = GUIDELINE_XRECHNUNG
    doc.context.business_parameter.id = BUSINESS_PROCESS  # BT-23

    # Kopf (BT-1, BT-3, BT-2). Kein ram:Name: im EN-16931-CII-ExchangedDocument
    # nicht zugelassen (drafthorse markiert es irrefuehrend als required).
    doc.header.id = rechnung.rechnungsnummer
    doc.header.type_code = "380"
    doc.header.issue_date_time = rechnung.rechnungsdatum

    # Verkäufer (BG-4, BG-5, BT-31)
    verk = rechnung.verkaeufer
    doc.trade.agreement.seller.name = verk.name
    _setze_adresse(doc.trade.agreement.seller.address, verk.adresse)
    doc.trade.agreement.seller.tax_registrations.add(
        TaxRegistration(id=("VA", verk.mehrwertsteuer_id))
    )
    # Elektronische Adresse (BT-34) und Verkäuferkontakt (BG-6, Pflicht BR-DE-2)
    doc.trade.agreement.seller.electronic_address.uri_ID = ("EM", verk.email)
    doc.trade.agreement.seller.contact.person_name = verk.kontakt_name
    doc.trade.agreement.seller.contact.telephone.number = verk.telefon
    doc.trade.agreement.seller.contact.email.address = verk.email

    # Käufer (BG-7, BG-8, BT-48, BT-46)
    kauf = rechnung.kaeufer
    doc.trade.agreement.buyer.name = kauf.name
    _setze_adresse(doc.trade.agreement.buyer.address, kauf.adresse)
    if kauf.umsatzsteuer_id:
        doc.trade.agreement.buyer.tax_registrations.add(
            TaxRegistration(id=("VA", kauf.umsatzsteuer_id))
        )
    # Elektronische Adresse des Käufers (BT-49)
    doc.trade.agreement.buyer.electronic_address.uri_ID = ("EM", kauf.email)

    # Käuferreferenz (BT-10, Pflicht in XRechnung BR-DE-15) und
    # Bestellreferenz (BT-13)
    doc.trade.agreement.buyer_reference = kauf.kundennummer
    doc.trade.agreement.buyer_order.issuer_assigned_id = bestellnummer

    # Lieferdatum (BT-72): tatsächliches Leistungsende. Füllt zugleich das sonst
    # leere ApplicableHeaderTradeDelivery (Hygiene; PEPPOL-EN16931-R008).
    doc.trade.delivery.event.occurrence = rechnung.leistungszeitraum.bis

    # Settlement: Belegwährung BT-5, dynamisch aus der Bestellung (S-0064)
    doc.trade.settlement.currency_code = waehrung

    # Leistungszeitraum (BG-14)
    doc.trade.settlement.period.start = rechnung.leistungszeitraum.von
    doc.trade.settlement.period.end = rechnung.leistungszeitraum.bis

    # Zahlung und Bankverbindung (BG-16/17): die an der Rechnung gewählte, sonst Rückfall auf
    # die erste (S-0065). Der Rückfall greift nur bei inaktiver XRechnung; sonst verlangt die
    # Pflichtprüfung eine Wahl.
    bank = rechnung.bankverbindung or (
        verk.bankverbindungen[0] if verk.bankverbindungen else None
    )
    if bank is not None:
        zahlung = PaymentMeans(type_code="58")  # SEPA-Überweisung
        zahlung.payee_account.iban = bank.iban
        zahlung.payee_account.account_name = bank.kontoinhaber
        zahlung.payee_institution.bic = bank.bic
        doc.trade.settlement.payment_means.add(zahlung)

    # Positionen (BG-25), alle mit derselben Steuerkategorie; Zeilensumme aufaddieren
    netto = Decimal("0.00")
    for index, pos in enumerate(rechnung.positionen, start=1):
        zeile = LineItem()
        zeile.document.line_id = str(index)
        zeile.product.name = pos.bezeichnung
        zeile.agreement.net.amount = pos.einzelpreis
        zeile.agreement.net.basis_quantity = (Decimal("1"), EINHEIT_STUECK)
        zeile.delivery.billed_quantity = (pos.menge, EINHEIT_STUECK)
        zeile.settlement.trade_tax.type_code = "VAT"
        zeile.settlement.trade_tax.category_code = kategorie
        zeile.settlement.trade_tax.rate_applicable_percent = satz
        # Positions-Leistungszeitraum (BG-26, BT-134/BT-135): nur bei gesetztem Zeitraum
        # (S-0070); Positionen ohne Zeitraum bleiben ohne BG-26, der Kopf-BG-14 ist unberührt.
        if pos.leistungszeitraum is not None:
            zeile.settlement.period.start = pos.leistungszeitraum.von
            zeile.settlement.period.end = pos.leistungszeitraum.bis
        zeile.settlement.monetary_summation.total_amount = pos.gesamtpreis
        doc.trade.items.add(zeile)
        netto += pos.gesamtpreis

    # Steuerbetrag: 0 bei Reverse-Charge (AE), sonst netto × Satz, kaufmännisch auf
    # Cent gerundet (BR-CO-17, konsistent zu services.berechne_summen).
    if rechnung.reverse_charge:
        steuerbetrag = Decimal("0.00")
    else:
        steuerbetrag = (netto * satz / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)
    brutto = netto + steuerbetrag

    # Steueraufschlüsselung (BG-23): eine Gruppe. Bei AE der Pflicht-Befreiungsgrund
    # VATEX-EU-AE (BR-AE-10); bei S kein Befreiungsgrund.
    steuer = ApplicableTradeTax()
    steuer.calculated_amount = steuerbetrag
    steuer.basis_amount = netto
    steuer.type_code = "VAT"
    steuer.category_code = kategorie
    steuer.rate_applicable_percent = satz
    if rechnung.reverse_charge:
        steuer.exemption_reason_code = "VATEX-EU-AE"
        steuer.exemption_reason = "Reverse charge"
    doc.trade.settlement.trade_tax.add(steuer)

    # Summen (BG-22): netto + Steuer = brutto = Zahlbetrag (bei AE ist die Steuer 0)
    summe = doc.trade.settlement.monetary_summation
    summe.line_total = netto
    summe.charge_total = Decimal("0.00")
    summe.allowance_total = Decimal("0.00")
    summe.tax_basis_total = netto
    summe.tax_total = (steuerbetrag, waehrung)  # BT-110 in Belegwährung (S-0064)
    summe.grand_total = brutto
    summe.due_amount = brutto

    # Zahlungsbedingung (BT-20), bei gesetztem Skonto mit BR-DE-18-Zeile (S-0051)
    bedingung = PaymentTerms()
    bedingung.description = _bt20_text(rechnung)
    # Fälligkeitsdatum (BT-9) aus Rechnungsdatum plus Zahlungsfrist; ohne Frist kein BT-9.
    # Es tritt neben BT-20 und ersetzt es nicht (S-0081).
    if rechnung.zahlungsfrist > 0:
        bedingung.due = rechnung.rechnungsdatum + timedelta(days=rechnung.zahlungsfrist)
    doc.trade.settlement.terms.add(bedingung)

    return doc.serialize(schema="FACTUR-X_EN16931")
