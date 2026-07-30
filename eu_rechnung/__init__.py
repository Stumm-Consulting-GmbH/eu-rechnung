"""EU-Rechnung — Werkzeug für EN-16931-konforme E-Rechnungen (XRechnung, ZUGFeRD)."""

# Die Programmversion steht hier und nur hier: `pyproject.toml` liest sie über
# `dynamic = ["version"]` von hier, der Über-Dialog importiert sie direkt. Bewusst nicht
# über `importlib.metadata`, weil Paket-Metadaten in der späteren `.exe` nicht verlässlich
# vorliegen.
__version__ = "0.1.0"

# Produkt- und Herausgeberangaben, bewusst nicht im Sprachkatalog: Eigennamen werden nicht
# übersetzt. Sie stehen hier statt in der Oberfläche, weil Fenstertitel und Über-Dialog sie
# beide brauchen und der Dialog sonst zirkulär auf das Hauptfenster zeigen müsste.
PRODUKTNAME = "SCG EU E-Rechnung Generator"
HERAUSGEBER = "Stumm-Consulting GmbH, Liestal (Schweiz)"
# Jahr des Copyright-Vermerks, bewusst fest statt aus der Systemuhr: Ein Copyright-Jahr ist
# eine Aussage über die Veröffentlichung, kein Tagesdatum.
COPYRIGHT_JAHR = "2026"
