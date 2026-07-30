"""Gemeinsame Bausteine der PyInstaller-Konfigurationen (4T-0183).

Es gibt zwei Build-Ziele: die ausgelieferte Anwendung (`eu-rechnung.spec`) und das
Prüf-Binary des Bundle-Selbsttests (`bundle-selbsttest.spec`). Der Selbsttest soll
belegen, dass die **gefrorene** Anwendung ihre gebündelten Assets findet. Diese Aussage
trägt nur, wenn beide Ziele dieselben Datendateien sammeln, deshalb steht die Sammlung
hier an einer Stelle statt zweimal nebeneinander. Eine Kopie würde irgendwann auseinander
laufen, und der Selbsttest prüfte dann eine Konfiguration, die es nicht mehr gibt.
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


def sammle_datas() -> list[tuple[str, str]]:
    """Alle Datendateien, die ins Bundle gehören.

    Die eigenen Ressourcen (ICC-Profil, Programm-Icon, Sprachdateien) und die
    Package-Data der Bibliotheken, die PyInstaller nicht von allein findet: drafthorse
    bringt die CII-Schemata mit, factur-x seine XSD- und XSL-Dateien. `reportlab` wird
    gesammelt, weil der PDF-Sichtteil seine eingebettete Schrift aus dem Paket selbst
    holt (`export/pdf_sicht.py`). Für `jsonschema` und `jsonschema_specifications` liegen
    Hooks bei, die das erledigen.

    **Ohne die Order-X-Schemata von factur-x.** Order-X ist der Standard für
    Bestelldokumente; factur-x lädt diese Schemata ausschließlich bei
    `flavor="order-x"`, und die Anwendung erzeugt Rechnungen mit
    `flavor="factur-x"` (`export/zugferd.py`). Der Ausschluss spart 57 Dateien und
    löst zugleich ein handfestes Problem: Acht dieser Dateinamen sind so lang, dass der
    Pfad im Build-Verzeichnis die Windows-Grenze von 260 Zeichen überschreitet, woran
    der Bau des Setup-Programms scheiterte (Inno Setup nutzt die Langpfad-Unterstützung
    des Systems nicht). Belegt wird der Ausschluss durch den Bundle-Selbsttest, dessen
    XSD-Prüfung Teil der ZUGFeRD-Erzeugung ist.
    """
    facturx = [
        (quelle, ziel)
        for quelle, ziel in collect_data_files("facturx")
        if "orderx" not in quelle.replace("\\", "/").lower()
    ]
    return (
        collect_data_files("eu_rechnung")
        + collect_data_files("drafthorse")
        + facturx
        + collect_data_files("reportlab")
    )


def lies_angaben(wurzel: Path) -> dict[str, str]:
    """Produktangaben aus `eu_rechnung/__init__.py`, ohne das Paket zu importieren.

    Version, Produktname und Herausgeber stehen ausschließlich dort; eine zweite
    Pflegestelle liefe irgendwann auseinander. Das Modul importiert nichts, deshalb ist
    das Auswerten gefahrlos und zieht nicht die halbe Anwendung in den Build-Prozess.
    """
    angaben: dict[str, str] = {}
    exec((wurzel / "eu_rechnung" / "__init__.py").read_text(encoding="utf-8"), angaben)
    return angaben


def schreibe_versionsinfo(wurzel: Path, dateiname: str) -> Path:
    """Erzeugt die Windows-Versionsinfo der .exe aus den Produktangaben.

    Sprache 0407 (Deutsch) mit Codepage 04B0 (Unicode).
    """
    angaben = lies_angaben(wurzel)
    version = angaben["__version__"]
    teile = [int(t) for t in version.split(".")]
    while len(teile) < 4:
        teile.append(0)
    copyright_ = f"© {angaben['COPYRIGHT_JAHR']} {angaben['HERAUSGEBER']}"
    ziel = wurzel / "build" / f"version_info_{dateiname}.txt"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple(teile)}, prodvers={tuple(teile)},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', {angaben["HERAUSGEBER"]!r}),
      StringStruct('FileDescription', {angaben["PRODUKTNAME"]!r}),
      StringStruct('FileVersion', {version!r}),
      StringStruct('InternalName', {dateiname!r}),
      StringStruct('LegalCopyright', {copyright_!r}),
      StringStruct('OriginalFilename', {dateiname + ".exe"!r}),
      StringStruct('ProductName', {angaben["PRODUKTNAME"]!r}),
      StringStruct('ProductVersion', {version!r}),
    ])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return ziel
