"""Importer generelle planlægningsvejledninger til den lokale vidensbase.

Scriptet læser kun de angivne PDF-filer fra O-drevet og skriver udtrukket tekst
til den lokale SQLite-vidensbase. O-drevet ændres ikke.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3

import pdfplumber

import vidensbase


KILDER = [
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_om_strategisk_planlaegning_for_landsbyer_-nov2021.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\Byplanhaandbogen_.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\evaluering_af_planloven_m.v._2021.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\Håndbog om Miljø- og planlægning.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\Introduktion til SCRUM (scrum guide).pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\legislation-edition-3.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\lokalplanlaegning_for_bevaringsvaerdige_miljoeer_i_byer_og_paa_landet.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\Planloven i praksis.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_-_hvordan_finder_og_haandterer_man_deljordstykker_i_plandata.dk_.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_-_introduktion_til_deljordstykker_i_plandata.dk__0.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_for_omdannelseslandsbyer.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_om_bygherres_bidrag_-_endelig.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_om_landzoneadministration_-_erhvervsstyrelsen_november_2019.pdf"),
    Path(r"O:\Plan\23 Team Digitalisering Plan\Læsestof\vejledning_om_lokalplaner_af_mindre_betydning.pdf"),
]

TAGS = ["planloven", "vejledning", "ikke system vejledning"]
OMRAADE = "Generel planlægning og planlovsvejledning"
KILDE_TYPE = "Planfaglig vejledning"
PRIORITET = 7
NOTE = (
    "Generel planfaglig vejledning. Indholdet er ikke systemdokumentation og "
    "skal kontrolleres mod gældende lovgivning, Plandata.dk og nyere godkendte kilder."
)


def side_id_for(filsti: Path) -> str:
    return "dokument:" + hashlib.sha256(str(filsti).casefold().encode("utf-8")).hexdigest()[:24]


def er_importeret(filsti: Path) -> bool:
    vidensbase.initialiser_database()
    with sqlite3.connect(vidensbase.DATABASE_FIL) as forbindelse:
        række = forbindelse.execute(
            "SELECT 1 FROM confluence_sider WHERE side_id = ?",
            (side_id_for(filsti),),
        ).fetchone()
    return række is not None


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
        if er_importeret(filsti):
            print(f"SPRINGER OVER: {filsti.name} er allerede importeret")
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
