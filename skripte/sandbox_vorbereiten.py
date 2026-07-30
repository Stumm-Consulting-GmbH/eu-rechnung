"""Bereitet den Nachweis-Durchlauf in der Windows Sandbox vor (4T-0184, S-0052).

Die Sandbox ist beim Schließen restlos vergessen. Damit der Durchlauf nicht an
Kopierarbeit und verlorenen Belegen hängt, erzeugt dieses Skript

1. einen **Austauschordner** auf dem Host, den die Sandbox beschreibbar eingebunden
   bekommt. Alles, was darin landet, überlebt das Schließen; ein Herauskopieren vor dem
   Ende ist damit nicht nötig.
2. eine **Beispiel-Firma-Datei** aus dem Erstlauf-Seed, damit in der Sandbox nicht erst
   Stammdaten von Hand erfasst werden müssen. Kunde, Artikel und Bestellung sind
   enthalten, eine Rechnung bewusst **nicht**: Das Anlegen und Erzeugen über die Maske
   ist genau der Teil, den der Nachweis prüfen soll (S-0052 AK2).
3. eine **Sandbox-Konfiguration** (`.wsb`), die den Build-Ordner schreibgeschützt und
   den Austauschordner beschreibbar einbindet und beim Start den Ordner der Anwendung
   öffnet.

Die `.wsb`-Datei enthält absolute Pfade dieses Rechners und wird deshalb erzeugt, statt
im Repository zu liegen; sie landet unter `Daten/` und ist git-ignoriert.

Aufruf:

    .\\.venv\\Scripts\\python.exe skripte\\sandbox_vorbereiten.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from eu_rechnung.persistence import speichere
from eu_rechnung.services import erzeuge_seed

_WURZEL = Path(__file__).resolve().parent.parent
_DIST = _WURZEL / "dist"
_SANDBOX = _WURZEL / "Daten" / "sandbox"
_AUSTAUSCH = _SANDBOX / "austausch"
_WSB = _SANDBOX / "pruefung.wsb"

# Eingebundene Ordner erscheinen in der Sandbox auf dem Desktop des Standardkontos.
_SANDBOX_DESKTOP = r"C:\Users\WDAGUtilityAccount\Desktop"


def _mapping() -> str:
    """Die beiden eingebundenen Ordner: Build schreibgeschützt, Austausch beschreibbar."""
    return f"""  <MappedFolders>
    <MappedFolder>
      <HostFolder>{_DIST}</HostFolder>
      <SandboxFolder>{_SANDBOX_DESKTOP}\\dist</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{_AUSTAUSCH}</HostFolder>
      <SandboxFolder>{_SANDBOX_DESKTOP}\\austausch</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
"""


def main() -> int:
    if not (_DIST / "SCG-EU-E-Rechnung-Generator").is_dir():
        print("Der Build fehlt. Erst `pyinstaller --noconfirm eu-rechnung.spec` laufen lassen.")
        return 1

    _AUSTAUSCH.mkdir(parents=True, exist_ok=True)
    firma_datei = _AUSTAUSCH / "Beispiel-Firma.scgr"
    speichere(erzeuge_seed(), firma_datei)

    # `<vGPU>Disable</vGPU>` ist auf diesem Rechner **notwendig**, nicht optional: Mit
    # aktiver virtueller Grafikbeschleunigung (Windows-Standard) bricht die Sandbox
    # reproduzierbar nach etwa 25 Sekunden ab („Verbindung mit der
    # Windows-Sandbox-Umgebung wurde getrennt"), ohne sie läuft die Sitzung stabil.
    # Gemessen am 2026-07-30 durch Bisektion: Blank-Start ohne jede Konfiguration
    # scheiterte ebenso, womit die Konfiguration als Ursache ausgeschlossen war.
    # Die Anwendung braucht keine Grafikbeschleunigung; für den Nachweis ist das
    # folgenlos.
    #
    # Die beiden schlankeren Varianten bleiben als Diagnosemittel bestehen: Sollte die
    # Sandbox künftig wieder abbrechen, grenzt man mit ihnen ein, statt zu raten.
    varianten = {
        # Voll: ohne vGPU, mit Anmeldebefehl (öffnet den Programmordner), ohne Netzwerk.
        _WSB: (
            f"<Configuration>\n  <vGPU>Disable</vGPU>\n{_mapping()}"
            f"  <LogonCommand>\n"
            f"    <Command>explorer.exe {_SANDBOX_DESKTOP}\\dist\\SCG-EU-E-Rechnung-Generator"
            f"</Command>\n  </LogonCommand>\n"
            "  <ClipboardRedirection>true</ClipboardRedirection>\n"
            "  <Networking>Disable</Networking>\n</Configuration>\n"
        ),
        # Minimal: nur das Mapping, sonst alles auf Standard.
        _SANDBOX / "pruefung-minimal.wsb": f"<Configuration>\n{_mapping()}</Configuration>\n",
        # Ohne Grafikbeschleunigung: hilft auf Systemen, deren Treiber die virtuelle GPU
        # der Sandbox nicht mitmacht (typisches Bild: Fenster erscheint, dann bricht die
        # Verbindung ab).
        _SANDBOX / "pruefung-ohne-vgpu.wsb": (
            f"<Configuration>\n  <vGPU>Disable</vGPU>\n{_mapping()}</Configuration>\n"
        ),
    }
    for pfad, inhalt in varianten.items():
        pfad.write_text(inhalt, encoding="utf-8")

    print("Vorbereitet:")
    print(f"  Austauschordner       : {_AUSTAUSCH}")
    print(f"  Beispiel-Firma        : {firma_datei.name} ({firma_datei.stat().st_size} Bytes)")
    print("  Konfigurationen (in dieser Reihenfolge probieren, falls die Sandbox abbricht):")
    for pfad in varianten:
        print(f"    {pfad.name}")
    print("\nStart der Sandbox: die gewünschte .wsb-Datei doppelklicken.")
    print("In der vollen Variante ist das Netzwerk abgeschaltet: Die Anwendung braucht")
    print("keins, und ohne Netz ist der Nachweis „läuft eigenständig“ nicht durch")
    print("Nachladen zu verwässern.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
