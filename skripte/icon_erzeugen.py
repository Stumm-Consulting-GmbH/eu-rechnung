"""Erzeugt das Programm-Icon der Anwendung (S-0086).

Dieses Skript **ist** die Quelle des Icons: Es zeichnet das Symbol und schreibt
`eu_rechnung/ressourcen/icon.ico`. Damit ist jede Änderung an Motiv, Farbe oder Größen
nachvollziehbar und wiederholbar, statt in einer eingecheckten Binärdatei unbekannter
Herkunft zu verschwinden. Die `.ico` selbst ist versioniert, denn die Anwendung braucht
sie zur Laufzeit; erzeugt wird sie nur, wenn sich das Motiv ändert.

Motiv nach Vorgabe des Product Owners: ein dunkelblaues Eurozeichen auf
champagnerfarbenem Grund, quadratisch mit abgerundeten Ecken.

Gezeichnet wird mit Pillow, das über ReportLab ohnehin im Bestand liegt
(`Requires-Dist: pillow>=9.0.0`); das Eurozeichen kommt aus der von ReportLab
mitgelieferten, frei lizenzierten Vera-Schrift. Es kommt also keine Abhängigkeit hinzu
und es braucht keinen Vektor-Editor.

Aufruf (im Projekt-Wurzelverzeichnis):

    .\\.venv\\Scripts\\python.exe skripte\\icon_erzeugen.py

Neben der `.ico` entsteht unter `Daten/icon-muster/` eine Musterreihe zur Sichtprüfung
der kleinen Größen (Akzeptanzkriterium: bei 16 px als Eurozeichen erkennbar). `Daten/`
ist git-ignoriert, die Muster sind Prüf-Artefakte und kein Repo-Inhalt.
"""

from __future__ import annotations

import os
from pathlib import Path

import reportlab
from PIL import Image, ImageDraw, ImageFont

# Farben der Vorgabe: Grund Champagner, Zeichen EU-Blau (das Blau der Europaflagge,
# passend zu einem Werkzeug für EU-Norm-Rechnungen).
GRUND = "#F7E7CE"
ZEICHEN = "#003399"

# Die von Windows genutzten Auflösungen. 256 px ist die größte, die das ICO-Format
# in dieser Form trägt.
GROESSEN = (16, 24, 32, 48, 64, 128, 256)

# Jede Größe wird einzeln gezeichnet und dabei überabgetastet (acht-fach gerendert,
# dann verkleinert). Das ergibt saubere Kanten, ohne auf eine einzige Vorlage
# angewiesen zu sein.
UEBERABTASTUNG = 8

# Kleine Größen erhalten bewusst andere Proportionen: ein größeres Zeichen und einen
# schwächer gerundeten Rand, weil bei 16 px sonst zu wenig Fläche für den Glyphen
# bleibt. Das ist gängige Icon-Praxis und keine Abweichung von der Vorgabe.
KLEIN_BIS = 32
ECKENRADIUS_ANTEIL = 0.18
ECKENRADIUS_ANTEIL_KLEIN = 0.15
ZEICHEN_ANTEIL = 0.56
ZEICHEN_ANTEIL_KLEIN = 0.70

# Fette Schnittvariante: Ein Icon-Glyph braucht Strichstärke, sonst verschwindet er
# in den kleinen Größen.
SCHRIFT_DATEI = "VeraBd.ttf"

_WURZEL = Path(__file__).resolve().parent.parent
_ZIEL_ICO = _WURZEL / "eu_rechnung" / "ressourcen" / "icon.ico"
_ZIEL_MUSTER = _WURZEL / "Daten" / "icon-muster"


def schrift_pfad() -> Path:
    """Pfad der Vera-Schrift im ReportLab-Paket.

    Dieselbe Quelle, aus der auch der PDF-Sichtteil seine eingebettete Schrift nimmt
    (`export/pdf_sicht.py`); die Schrift ist frei lizenziert und trägt das Eurozeichen.
    """
    pfad = Path(os.path.dirname(reportlab.__file__)) / "fonts" / SCHRIFT_DATEI
    if not pfad.is_file():
        raise FileNotFoundError(f"Schrift nicht gefunden: {pfad}")
    return pfad


def zeichne(kante: int) -> Image.Image:
    """Zeichnet das Icon in der Kantenlänge `kante` (quadratisch, mit Transparenz).

    Außerhalb der abgerundeten Fläche bleibt der Hintergrund durchsichtig, damit das
    Symbol auf hellem und dunklem Untergrund gleich sauber sitzt.
    """
    klein = kante <= KLEIN_BIS
    gross = kante * UEBERABTASTUNG
    radius_anteil = ECKENRADIUS_ANTEIL_KLEIN if klein else ECKENRADIUS_ANTEIL
    zeichen_anteil = ZEICHEN_ANTEIL_KLEIN if klein else ZEICHEN_ANTEIL

    bild = Image.new("RGBA", (gross, gross), (0, 0, 0, 0))
    stift = ImageDraw.Draw(bild)
    stift.rounded_rectangle(
        (0, 0, gross - 1, gross - 1), radius=round(gross * radius_anteil), fill=GRUND
    )

    # Schriftgröße so wählen, dass die tatsächliche Glyphen-Höhe dem gewünschten
    # Anteil entspricht. Gemessen wird am Glyphen selbst, nicht an den
    # Schrift-Metriken: Ober- und Unterlängen der Schrift sagen über die Höhe eines
    # einzelnen Zeichens nichts.
    ziel_hoehe = gross * zeichen_anteil
    probe = ImageFont.truetype(str(schrift_pfad()), 100)
    links, oben, rechts, unten = probe.getbbox("€")
    schriftgroesse = max(1, round(100 * ziel_hoehe / (unten - oben)))
    schrift = ImageFont.truetype(str(schrift_pfad()), schriftgroesse)

    # Optisch mittig setzen: über die Begrenzung des Glyphen, nicht über den
    # Textursprung, sonst sitzt das Zeichen sichtbar zu tief.
    links, oben, rechts, unten = schrift.getbbox("€")
    x = (gross - (rechts - links)) / 2 - links
    y = (gross - (unten - oben)) / 2 - oben
    stift.text((x, y), "€", font=schrift, fill=ZEICHEN)

    return bild.resize((kante, kante), Image.Resampling.LANCZOS)


def schreibe_musterreihe(rahmen: dict[int, Image.Image]) -> Path:
    """Legt alle Größen 1:1 nebeneinander, auf hellem und dunklem Streifen.

    Dient der Sichtprüfung, ob das Eurozeichen auch bei 16 px erkennbar ist. Eine
    Behauptung dazu wäre wertlos, ein Bild ist prüfbar.
    """
    abstand = 12
    breite = sum(k + abstand for k in rahmen) + abstand
    hoehe = max(rahmen) + 2 * abstand
    blatt = Image.new("RGBA", (breite, 2 * hoehe), (255, 255, 255, 255))
    ImageDraw.Draw(blatt).rectangle((0, hoehe, breite, 2 * hoehe), fill="#1E1E1E")

    for streifen in (0, 1):
        x = abstand
        for kante in sorted(rahmen):
            y = streifen * hoehe + (hoehe - kante) // 2
            blatt.alpha_composite(rahmen[kante], (x, y))
            x += kante + abstand

    _ZIEL_MUSTER.mkdir(parents=True, exist_ok=True)
    for kante, bild in rahmen.items():
        bild.save(_ZIEL_MUSTER / f"icon-{kante}.png")
    ziel = _ZIEL_MUSTER / "musterreihe.png"
    blatt.save(ziel)
    return ziel


def main() -> None:
    rahmen = {kante: zeichne(kante) for kante in GROESSEN}
    gross = rahmen[max(GROESSEN)]
    _ZIEL_ICO.parent.mkdir(parents=True, exist_ok=True)
    gross.save(
        _ZIEL_ICO,
        format="ICO",
        sizes=[(k, k) for k in GROESSEN],
        append_images=[rahmen[k] for k in GROESSEN if k != max(GROESSEN)],
    )
    muster = schreibe_musterreihe(rahmen)
    print(f"{_ZIEL_ICO.relative_to(_WURZEL)}: {_ZIEL_ICO.stat().st_size} Bytes")
    print(f"Größen: {', '.join(str(k) for k in GROESSEN)}")
    print(f"Muster: {muster.relative_to(_WURZEL)}")


if __name__ == "__main__":
    main()
