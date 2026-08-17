"""Importer historiske PlanDK-/PlansystemDK-PDF'er til den lokale vidensbase.

Scriptet læser kun PDF-filer fra O-drevet og skriver udtrukket tekst til den
lokale SQLite-vidensbase. O-drevet ændres ikke.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

import vidensbase


KILDER = [
    Path(r"O:\Plan\23 Team Digitalisering Plan\9. Arkiv\090622_PlanDK3.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\datamodel-lokalplandelomraade plandk2+.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Generelle anvendelseskategorier.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Konket anvendelse.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Objektklasser.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Objekttype.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Administrative skel.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Kommuneplan.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Kommuneplanramme.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Kommuneplanstrategi.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Kommuneplantillæg.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Lokalplan.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Lokalplandelområde.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2 Zonekort.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\plandk2_-_2004.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\plandk2_0 (1).pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2_fysisk_datamodel.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK3_fysisk_datamodel_kommuneplan.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK3_fysisk_datamodel_spildevand og varmeforsyning.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Specifik anvendelse.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\Webtxt_Datamodellen PlanDK2.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2_fysisk datamodel\plandk2.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2_fysisk datamodel\Webtxt_PlanDK2, Fysisk datamodel.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\8. Systemer\System dokumentation PlanDK2 og PlanDK3\PlanDK2, XML_GML\Webtxt_PlanDK2, XML _GML.pdf"),
]

TAGS = ["historisk", "plansystemdk"]
OMRAADE = "Historisk PlansystemDK datamodel"
KILDE_TYPE = "Historisk dokument"
PRIORITET = 6
NOTE = (
    "Historisk kilde. Indholdet kan være delvist uaktuelt og skal kontrolleres "
    "mod Plandata.dk, gældende datamodel og nyere godkendte kilder."
)


def udtraek_pdf_tekst(filsti: Path) -> str:
    tekststykker: list[str] = []
    with pdfplumber.open(str(filsti)) as pdf:
        for sidenr, side in enumerate(pdf.pages, start=1):
            tekst = (side.extract_text() or "").strip()
            if tekst:
                tekststykker.append(f"Side {sidenr}\n{tekst}")
    return "\n\n".join(tekststykker).strip()


def main() -> None:
    importerede = 0
    fejlede = 0
    for filsti in KILDER:
        if filsti.name.startswith("~$"):
            continue
        if not filsti.exists():
            fejlede += 1
            print(f"MANGLER: {filsti}")
            continue
        try:
            tekst = udtraek_pdf_tekst(filsti)
            resultat = vidensbase.importer_dokument_kilde(
                {
                    "filsti": str(filsti),
                    "titel": filsti.stem,
                    "tekst": tekst,
                    "kilde_type": KILDE_TYPE,
                    "omraade": OMRAADE,
                    "prioritet": PRIORITET,
                    "tags": TAGS,
                    "note": NOTE,
                }
            )
        except Exception as fejl:
            fejlede += 1
            print(f"FEJL: {filsti} -> {fejl}")
            continue
        if resultat.get("ok"):
            importerede += 1
            print(f"OK: {filsti.name} ({resultat['chunks']} tekststykker)")
        else:
            fejlede += 1
            print(f"FEJL: {filsti.name} -> {resultat.get('fejl')}")

    print(f"Færdig: {importerede} importeret, {fejlede} fejlet")


if __name__ == "__main__":
    main()
