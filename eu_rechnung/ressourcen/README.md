# Ressourcen

Gebündelte Laufzeit-Assets der Anwendung, die mit in die spätere `.exe`
ausgeliefert werden.

## sprachen/

Die Sprachdateien des Katalogs (`../texte.py`), je eine flache JSON-Datei pro
Sprache: `de.json`, `en.json`, `it.json`, `fr.json`, `es.json`. Sie tragen alle
festen Texte des Programms, für die Oberfläche wie für den PDF-Sichtteil, dazu die
Zahlen- und Datumsformate je Sprache (`format.*`).

Bewusst ohne Werkzeugkette (kein Qt-`tr()`, kein `lupdate`/`lrelease`, kein
Binärformat), damit ein Text ohne Übersetzungswerkzeug pflegbar bleibt. Begründung:
Entscheidung E-011.

### Einen Text ändern

Den Wert in allen fünf Dateien anpassen. Der Schlüssel bleibt unverändert, sonst
laufen die Fundstellen im Code ins Leere.

### Einen neuen Text anlegen

1. **Erst prüfen, ob es ihn schon gibt.** Texte, die mehrere Module teilen, liegen in
   der Gruppe `allgemein.*` (etwa `allgemein.fehlt_land`). Ein zweiter Schlüssel mit
   demselben Wortlaut ist eine Dublette, die beim Übersetzen auseinanderläuft.
2. **Schlüssel nach dem Muster `<gruppe>.<zweck>`** vergeben; die Gruppe ist das Modul
   oder der Bereich (`firma.`, `rechnung.`, `sichtteil.`, `allgemein.`). Für Meldungen
   sind `<gruppe>.fehlt_<feld>` und `<gruppe>.fehler_<feld>` etabliert.
3. **In alle fünf Dateien eintragen.** `tests/test_texte.py` bricht, sobald ein
   Schlüssel in einer Sprache fehlt oder eine Datei einen unbekannten führt.
4. **Werte als Platzhalter**, nie in den Text hineinformatiert: `"Position {nr}: …"`
   statt eines vorformatierten Strings. Sonst bliebe die Satzstellung an die deutsche
   Grammatik gebunden. Die Platzhalter-Namen müssen in allen fünf Sprachen identisch
   sein.

### Was das DoD-Kriterium D5 praktisch verlangt

„Sprachdateien (DE/EN/IT/FR/ES) überarbeitet" ist erfüllt, wenn jeder Text, den die
Story neu einführt oder ändert, in allen fünf Sprachen steht und fachlich stimmt. Die
Vollständigkeit prüft `tests/test_texte.py` automatisch, die Formulierung nicht: Für
Fachbegriffe der Rechnungsstellung (Steuerschuldnerschaft, Skonto, Zahlbetrag) gilt der
geläufige Normbegriff der jeweiligen Sprache, nicht die wörtliche Übersetzung. Die
Texte entstehen ohne muttersprachliche Prüfung; eine spätere Korrekturschleife bleibt
möglich, weil sie hier pflegbar liegen (Risiko notiert in 3E-0031).

Wo Befunde der Fachlogik betroffen sind, prüft `tests/test_befunde.py` zusätzlich, dass
jeder im Code verwendete Schlüssel im Katalog steht und seine Platzhalter passen.

## sRGB2014.icc

sRGB-ICC-Profil, das im Sichtteil als PDF/A-OutputIntent gesetzt wird
([../export/pdf_sicht.py](../export/pdf_sicht.py)). PDF/A verlangt einen
OutputIntent mit eingebettetem Zielprofil; factur-x setzt ihn nicht
(Entscheidung E-007). Das Profil wird gebündelt, damit die Anwendung
unabhängig vom Windows-Systemprofil arbeitet.

- **Herkunft:** International Color Consortium (ICC),
  <https://registry.color.org/rgb-registry/profiles/sRGB2014.icc> (bezogen 2026-06-19).
- **Version:** ICC v2, sRGB mit D65-D50-chromatischer Adaption.
- **Lizenz:** Das Profil „may be copied, distributed, embedded, made, used,
  and sold without restriction." Auflage: Veränderte Fassungen müssen die
  ursprüngliche Identifikation und Copyright-Information entfernen und dürfen
  nicht als Original ausgegeben werden. Quelle:
  [ICC FAQ](https://www.color.org/faqs.xalter).
- **Unverändert:** Die Datei wird unverändert übernommen und ausgeliefert.
