"""Lokal vidensbase for godkendte Confluence-kilder.

Modulet gemmer kun sider, der matcher den eksplicit godkendte whitelist i
data/godkendte_confluence_omraader.json. SQLite bruges som standard, så appen
kan køre uden nye pakker. Postgres kan tilføjes senere via en lille adapter.
"""

from __future__ import annotations

import html
import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROD = Path(__file__).resolve().parent
DATA_MAPPE = ROD / "data"
DATABASE_FIL = DATA_MAPPE / "vidensbase.sqlite3"
GODKENDTE_OMRAADER_FIL = DATA_MAPPE / "godkendte_confluence_omraader.json"
PLANDATA_KILDER_FIL = DATA_MAPPE / "plandata_offentlige_kilder.json"
MAKS_CHUNK_TEGN = 1400
CHUNK_OVERLAP = 180
STOPORD = {
    "hvad", "hvor", "hvordan", "hvorfor", "skal", "kan", "kunne", "ville", "plejer",
    "svare", "svarer", "svar", "om", "der", "det", "den", "de", "en", "et", "og",
    "til", "for", "fra", "med", "ved", "som", "på", "af", "i", "vi", "os"
}


@dataclass(frozen=True)
class Godkendelse:
    omraade: str
    prioritet: int


def initialiser_database() -> None:
    DATA_MAPPE.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.executescript(
            """
            CREATE TABLE IF NOT EXISTS confluence_sider (
                side_id TEXT PRIMARY KEY,
                titel TEXT NOT NULL,
                url TEXT NOT NULL,
                kilde_type TEXT NOT NULL DEFAULT 'Confluence',
                omraade TEXT NOT NULL,
                prioritet INTEGER NOT NULL,
                forfaedre_json TEXT NOT NULL,
                version_tid TEXT,
                importeret_tid REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS confluence_chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                side_id TEXT NOT NULL,
                chunk_nr INTEGER NOT NULL,
                titel TEXT NOT NULL,
                url TEXT NOT NULL,
                kilde_type TEXT NOT NULL DEFAULT 'Confluence',
                omraade TEXT NOT NULL,
                prioritet INTEGER NOT NULL,
                tekst TEXT NOT NULL,
                FOREIGN KEY (side_id) REFERENCES confluence_sider(side_id)
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_side_id ON confluence_chunks(side_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_prioritet ON confluence_chunks(prioritet);

            CREATE TABLE IF NOT EXISTS tags (
                tag_navn TEXT PRIMARY KEY,
                beskrivelse TEXT NOT NULL DEFAULT '',
                oprettet_tid REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kilde_tags (
                side_id TEXT NOT NULL,
                tag_navn TEXT NOT NULL,
                PRIMARY KEY (side_id, tag_navn),
                FOREIGN KEY (side_id) REFERENCES confluence_sider(side_id),
                FOREIGN KEY (tag_navn) REFERENCES tags(tag_navn)
            );

            CREATE TABLE IF NOT EXISTS kilde_relationer (
                relation_id TEXT PRIMARY KEY,
                fra_side_id TEXT NOT NULL,
                til_side_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                oprettet_tid REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS qa_svar (
                qa_id TEXT PRIMARY KEY,
                spoergsmaal TEXT NOT NULL,
                svar TEXT NOT NULL,
                status TEXT NOT NULL,
                prioritet INTEGER NOT NULL,
                tags_json TEXT NOT NULL,
                vedhaeftede_filer_json TEXT NOT NULL DEFAULT '[]',
                oprettet_tid REAL NOT NULL,
                opdateret_tid REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_kilde_tags_tag ON kilde_tags(tag_navn);
            CREATE INDEX IF NOT EXISTS idx_relationer_fra ON kilde_relationer(fra_side_id);
            CREATE INDEX IF NOT EXISTS idx_relationer_til ON kilde_relationer(til_side_id);
            CREATE INDEX IF NOT EXISTS idx_qa_status ON qa_svar(status);
            """
        )
        _tilfoej_kolonne_hvis_mangler(forbindelse, "confluence_sider", "kilde_type", "TEXT NOT NULL DEFAULT 'Confluence'")
        _tilfoej_kolonne_hvis_mangler(forbindelse, "confluence_chunks", "kilde_type", "TEXT NOT NULL DEFAULT 'Confluence'")
        _tilfoej_kolonne_hvis_mangler(forbindelse, "qa_svar", "vedhaeftede_filer_json", "TEXT NOT NULL DEFAULT '[]'")


def _tilfoej_kolonne_hvis_mangler(forbindelse: sqlite3.Connection, tabel: str, kolonne: str, definition: str) -> None:
    kolonner = {række[1] for række in forbindelse.execute(f"PRAGMA table_info({tabel})")}
    if kolonne not in kolonner:
        forbindelse.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolonne} {definition}")


def laes_godkendte_omraader() -> dict[str, Any]:
    return json.loads(GODKENDTE_OMRAADER_FIL.read_text(encoding="utf-8"))


def normaliser(tekst: str) -> str:
    return re.sub(r"\s+", " ", tekst.casefold()).strip()


def find_godkendelse(titel: str, forfaedre: list[str]) -> Godkendelse | None:
    konfiguration = laes_godkendte_omraader()
    samlet_sti = " / ".join(forfaedre + [titel])
    titel_norm = normaliser(titel)
    sti_norm = normaliser(samlet_sti)

    for udelukket in konfiguration.get("udeluk_som_standard", []):
        if normaliser(udelukket) in sti_norm:
            return None

    for omraade in konfiguration.get("omraader", []):
        if not omraade.get("godkendt"):
            continue
        for match in omraade.get("titel_match", []):
            if normaliser(match) == titel_norm:
                return Godkendelse(str(omraade["navn"]), int(omraade["prioritet"]))
        for match in omraade.get("sti_match", []):
            if normaliser(match) in sti_norm:
                return Godkendelse(str(omraade["navn"]), int(omraade["prioritet"]))
    return None


def html_til_tekst(indhold_html: str) -> str:
    tekst = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", indhold_html)
    tekst = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|table|blockquote)>", "\n", tekst)
    tekst = re.sub(r"(?i)<br\s*/?>", "\n", tekst)
    tekst = re.sub(r"(?s)<[^>]+>", " ", tekst)
    tekst = html.unescape(tekst)
    tekst = re.sub(r"[ \t\r\f\v]+", " ", tekst)
    tekst = re.sub(r"\n\s+", "\n", tekst)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


def udtraek_hovedindhold(indhold_html: str) -> str:
    match = re.search(r'(?is)<div\s+role=["\']main["\'][^>]*>(.*?)(?:<footer|</body>)', indhold_html)
    if match:
        return html_til_tekst(match.group(1))
    match = re.search(r'(?is)<main[^>]*>(.*?)</main>', indhold_html)
    if match:
        return html_til_tekst(match.group(1))
    return html_til_tekst(indhold_html)


def lav_chunks(tekst: str) -> list[str]:
    afsnit = [afsnit.strip() for afsnit in re.split(r"\n{2,}", tekst) if afsnit.strip()]
    chunks: list[str] = []
    aktuel = ""

    for afsnit in afsnit:
        if len(aktuel) + len(afsnit) + 2 <= MAKS_CHUNK_TEGN:
            aktuel = f"{aktuel}\n\n{afsnit}".strip()
            continue
        if aktuel:
            chunks.append(aktuel)
        if len(afsnit) <= MAKS_CHUNK_TEGN:
            aktuel = afsnit
        else:
            for start in range(0, len(afsnit), MAKS_CHUNK_TEGN - CHUNK_OVERLAP):
                chunks.append(afsnit[start : start + MAKS_CHUNK_TEGN].strip())
            aktuel = ""

    if aktuel:
        chunks.append(aktuel)
    return chunks


def normaliser_tags(tags: Any) -> list[str]:
    """Normaliser tags fra liste eller kommasepareret tekst."""
    if isinstance(tags, str):
        rå_tags = re.split(r"[,;\n]", tags)
    elif isinstance(tags, list):
        rå_tags = [str(tag) for tag in tags]
    else:
        rå_tags = []

    normaliserede: list[str] = []
    for tag in rå_tags:
        renset = re.sub(r"\s+", " ", tag.strip().casefold())
        if renset and renset not in normaliserede:
            normaliserede.append(renset[:60])
    return normaliserede


def normaliser_vedhaeftede_filer(filer: Any) -> list[dict[str, Any]]:
    """Normaliser bilag til Q&A uden at gemme browser-/formularstøj."""
    if not isinstance(filer, list):
        return []
    normaliserede: list[dict[str, Any]] = []
    for fil in filer:
        if not isinstance(fil, dict):
            continue
        tekst = str(fil.get("tekst", "") or "").strip()
        filnavn = str(fil.get("filnavn", "Ukendt fil")).strip()[:180]
        if not filnavn:
            filnavn = "Ukendt fil"
        normaliserede.append(
            {
                "filnavn": filnavn,
                "status": str(fil.get("status", "") or "").strip()[:300],
                "tekst": tekst[:12000],
                "tekst_laengde": int(fil.get("tekst_laengde") or len(tekst)),
                "kraever_ocr": bool(fil.get("kraever_ocr", False)),
            }
        )
    return normaliserede


def gem_tags(forbindelse: sqlite3.Connection, tags: list[str]) -> None:
    tidspunkt = time.time()
    forbindelse.executemany(
        """
        INSERT INTO tags (tag_navn, beskrivelse, oprettet_tid)
        VALUES (?, '', ?)
        ON CONFLICT(tag_navn) DO NOTHING
        """,
        [(tag, tidspunkt) for tag in tags],
    )


def gem_kilde_tags(forbindelse: sqlite3.Connection, side_id: str, tags: list[str]) -> None:
    gem_tags(forbindelse, tags)
    forbindelse.execute("DELETE FROM kilde_tags WHERE side_id = ?", (side_id,))
    forbindelse.executemany(
        "INSERT OR IGNORE INTO kilde_tags (side_id, tag_navn) VALUES (?, ?)",
        [(side_id, tag) for tag in tags],
    )


def hent_tags_map(forbindelse: sqlite3.Connection) -> dict[str, list[str]]:
    rækker = forbindelse.execute(
        """
        SELECT side_id, tag_navn
        FROM kilde_tags
        ORDER BY tag_navn
        """
    ).fetchall()
    tags: dict[str, list[str]] = {}
    for række in rækker:
        tags.setdefault(str(række["side_id"]), []).append(str(række["tag_navn"]))
    return tags


def qa_side_id(qa_id: str) -> str:
    return f"qa:{qa_id}"


def indekser_qa(forbindelse: sqlite3.Connection, qa: dict[str, Any]) -> int:
    qa_id = str(qa["qa_id"])
    side_id = qa_side_id(qa_id)
    status_tekst = str(qa["status"])
    forbindelse.execute("DELETE FROM confluence_chunks WHERE side_id = ?", (side_id,))

    if status_tekst != "godkendt":
        forbindelse.execute("DELETE FROM confluence_sider WHERE side_id = ?", (side_id,))
        forbindelse.execute("DELETE FROM kilde_tags WHERE side_id = ?", (side_id,))
        return 0

    tags = normaliser_tags(json.loads(str(qa["tags_json"] or "[]")))
    vedhaeftede_filer = normaliser_vedhaeftede_filer(json.loads(str(qa.get("vedhaeftede_filer_json") or "[]")))
    titel = str(qa["spoergsmaal"]).strip()[:180]
    prioritet = int(qa["prioritet"])
    filblokke: list[str] = []
    for nr, fil in enumerate(vedhaeftede_filer, start=1):
        if fil["tekst"]:
            filblokke.append(
                f"Bilag {nr}: {fil['filnavn']}\n"
                f"Status: {fil['status'] or 'Ingen status'}\n"
                f"Udtrukket tekst:\n{fil['tekst']}"
            )
        else:
            filblokke.append(
                f"Bilag {nr}: {fil['filnavn']}\n"
                f"Status: {fil['status'] or 'Ingen status'}"
            )
    tekst = (
        f"Spørgsmål:\n{qa['spoergsmaal']}\n\n"
        f"Godkendt svar:\n{qa['svar']}\n\n"
        f"Tags: {', '.join(tags) if tags else 'ingen'}\n\n"
        f"Vedhæftede filer:\n{chr(10).join(filblokke) if filblokke else 'ingen'}"
    )
    chunks = lav_chunks(tekst)
    forbindelse.execute(
        """
        INSERT INTO confluence_sider
            (side_id, titel, url, kilde_type, omraade, prioritet, forfaedre_json, version_tid, importeret_tid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(side_id) DO UPDATE SET
            titel=excluded.titel,
            url=excluded.url,
            kilde_type=excluded.kilde_type,
            omraade=excluded.omraade,
            prioritet=excluded.prioritet,
            forfaedre_json=excluded.forfaedre_json,
            version_tid=excluded.version_tid,
            importeret_tid=excluded.importeret_tid
        """,
        (
            side_id,
            titel,
            f"svarbank:{qa_id}",
            "Svarbank",
            "Godkendte spørgsmål og svar",
            prioritet,
            json.dumps(["Svarbank"], ensure_ascii=False),
            str(qa["opdateret_tid"]),
            time.time(),
        ),
    )
    forbindelse.executemany(
        """
        INSERT INTO confluence_chunks
            (side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (side_id, nr, titel, f"svarbank:{qa_id}", "Svarbank", "Godkendte spørgsmål og svar", prioritet, chunk)
            for nr, chunk in enumerate(chunks, start=1)
        ],
    )
    gem_kilde_tags(forbindelse, side_id, tags)
    return len(chunks)


def gem_qa_svar(data: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()
    qa_id = str(data.get("qa_id") or uuid.uuid4().hex)
    spoergsmaal = str(data.get("spoergsmaal", "")).strip()
    svar = str(data.get("svar", "")).strip()
    status_tekst = str(data.get("status", "kladde")).strip().casefold()
    if status_tekst not in {"kladde", "godkendt", "forældet"}:
        status_tekst = "kladde"
    prioritet = int(data.get("prioritet", 1) or 1)
    prioritet = max(0, min(9, prioritet))
    tags = normaliser_tags(data.get("tags", []))
    vedhaeftede_filer = normaliser_vedhaeftede_filer(data.get("vedhaeftede_filer", []))

    if len(spoergsmaal) < 5 or len(svar) < 5:
        return {"ok": False, "fejl": "Spørgsmål og svar skal begge udfyldes."}

    tidspunkt = time.time()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        eksisterende = forbindelse.execute("SELECT oprettet_tid FROM qa_svar WHERE qa_id = ?", (qa_id,)).fetchone()
        oprettet_tid = float(eksisterende["oprettet_tid"]) if eksisterende else tidspunkt
        forbindelse.execute(
            """
            INSERT INTO qa_svar
                (qa_id, spoergsmaal, svar, status, prioritet, tags_json, vedhaeftede_filer_json, oprettet_tid, opdateret_tid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qa_id) DO UPDATE SET
                spoergsmaal=excluded.spoergsmaal,
                svar=excluded.svar,
                status=excluded.status,
                prioritet=excluded.prioritet,
                tags_json=excluded.tags_json,
                vedhaeftede_filer_json=excluded.vedhaeftede_filer_json,
                opdateret_tid=excluded.opdateret_tid
            """,
            (
                qa_id,
                spoergsmaal,
                svar,
                status_tekst,
                prioritet,
                json.dumps(tags, ensure_ascii=False),
                json.dumps(vedhaeftede_filer, ensure_ascii=False),
                oprettet_tid,
                tidspunkt,
            ),
        )
        qa = forbindelse.execute("SELECT * FROM qa_svar WHERE qa_id = ?", (qa_id,)).fetchone()
        chunks = indekser_qa(forbindelse, dict(qa))

    return {
        "ok": True,
        "qa_id": qa_id,
        "status": status_tekst,
        "tags": tags,
        "vedhaeftede_filer": len(vedhaeftede_filer),
        "chunks": chunks,
    }


def hent_qa_svar() -> list[dict[str, Any]]:
    initialiser_database()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        rækker = forbindelse.execute(
            """
            SELECT qa_id, spoergsmaal, svar, status, prioritet, tags_json, vedhaeftede_filer_json, oprettet_tid, opdateret_tid
            FROM qa_svar
            ORDER BY opdateret_tid DESC
            """
        ).fetchall()
    svar: list[dict[str, Any]] = []
    for række in rækker:
        punkt = dict(række)
        punkt["tags"] = json.loads(str(punkt.pop("tags_json") or "[]"))
        punkt["vedhaeftede_filer"] = json.loads(str(punkt.pop("vedhaeftede_filer_json") or "[]"))
        svar.append(punkt)
    return svar


def hent_tags() -> list[str]:
    initialiser_database()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        rækker = forbindelse.execute("SELECT tag_navn FROM tags ORDER BY tag_navn").fetchall()
    return [str(række[0]) for række in rækker]


def opdater_kilde_metadata(data: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()
    side_id = str(data.get("side_id", "")).strip()
    tags = normaliser_tags(data.get("tags", []))
    prioritet = data.get("prioritet")
    if not side_id:
        return {"ok": False, "fejl": "Kilden mangler side_id."}

    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        kilde = forbindelse.execute("SELECT side_id FROM confluence_sider WHERE side_id = ?", (side_id,)).fetchone()
        if not kilde:
            return {"ok": False, "fejl": "Kilden findes ikke i vidensbasen."}
        if prioritet is not None and str(prioritet).strip() != "":
            ny_prioritet = max(0, min(9, int(prioritet)))
            forbindelse.execute("UPDATE confluence_sider SET prioritet = ? WHERE side_id = ?", (ny_prioritet, side_id))
            forbindelse.execute("UPDATE confluence_chunks SET prioritet = ? WHERE side_id = ?", (ny_prioritet, side_id))
        gem_kilde_tags(forbindelse, side_id, tags)
    return {"ok": True, "side_id": side_id, "tags": tags}


def gem_kilde_relation(data: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()
    fra_side_id = str(data.get("fra_side_id", "")).strip()
    til_side_id = str(data.get("til_side_id", "")).strip()
    relation_type = str(data.get("relation_type", "supplerer")).strip().casefold()
    note = str(data.get("note", "")).strip()[:500]
    if relation_type not in {"supplerer", "erstatter", "erstattes af", "modsiger", "eksempel på", "kræver"}:
        relation_type = "supplerer"
    if not fra_side_id or not til_side_id or fra_side_id == til_side_id:
        return {"ok": False, "fejl": "Vælg to forskellige kilder til relationen."}

    relation_id = uuid.uuid4().hex
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.execute(
            """
            INSERT INTO kilde_relationer
                (relation_id, fra_side_id, til_side_id, relation_type, note, oprettet_tid)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (relation_id, fra_side_id, til_side_id, relation_type, note, time.time()),
        )
    return {"ok": True, "relation_id": relation_id}


def hent_kilde_relationer() -> list[dict[str, Any]]:
    initialiser_database()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        rækker = forbindelse.execute(
            """
            SELECT
                r.relation_id,
                r.fra_side_id,
                fra.titel AS fra_titel,
                r.til_side_id,
                til.titel AS til_titel,
                r.relation_type,
                r.note,
                r.oprettet_tid
            FROM kilde_relationer r
            LEFT JOIN confluence_sider fra ON fra.side_id = r.fra_side_id
            LEFT JOIN confluence_sider til ON til.side_id = r.til_side_id
            ORDER BY r.oprettet_tid DESC
            """
        ).fetchall()
    return [dict(række) for række in rækker]


def importer_confluence_side(side: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()

    titel = str(side.get("titel", "")).strip()
    side_id = str(side.get("side_id", "")).strip()
    url = str(side.get("url", "")).strip()
    forfaedre = [str(punkt) for punkt in side.get("forfaedre", []) if str(punkt).strip()]
    version_tid = str(side.get("version_tid", "") or "")
    indhold_html = str(side.get("indhold_html", "") or "")
    tekst = str(side.get("tekst", "") or "").strip() or html_til_tekst(indhold_html)

    if not side_id or not titel or not url:
        return {"ok": False, "fejl": "Siden mangler side_id, titel eller url."}
    godkendelse = find_godkendelse(titel, forfaedre)
    if not godkendelse:
        return {"ok": False, "fejl": f"Siden er ikke på whitelist: {titel}"}
    if len(tekst) < 40:
        return {"ok": False, "fejl": f"Siden har for lidt tekst til import: {titel}"}

    chunks = lav_chunks(tekst)
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.execute(
            """
            INSERT INTO confluence_sider
                (side_id, titel, url, kilde_type, omraade, prioritet, forfaedre_json, version_tid, importeret_tid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(side_id) DO UPDATE SET
                titel=excluded.titel,
                url=excluded.url,
                kilde_type=excluded.kilde_type,
                omraade=excluded.omraade,
                prioritet=excluded.prioritet,
                forfaedre_json=excluded.forfaedre_json,
                version_tid=excluded.version_tid,
                importeret_tid=excluded.importeret_tid
            """,
            (
                side_id,
                titel,
                url,
                "Confluence",
                godkendelse.omraade,
                godkendelse.prioritet,
                json.dumps(forfaedre, ensure_ascii=False),
                version_tid,
                time.time(),
            ),
        )
        forbindelse.execute("DELETE FROM confluence_chunks WHERE side_id = ?", (side_id,))
        forbindelse.executemany(
            """
            INSERT INTO confluence_chunks
                (side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (side_id, nr, titel, url, "Confluence", godkendelse.omraade, godkendelse.prioritet, chunk)
                for nr, chunk in enumerate(chunks, start=1)
            ],
        )

    return {
        "ok": True,
        "side_id": side_id,
        "titel": titel,
        "omraade": godkendelse.omraade,
        "chunks": len(chunks),
    }


def hent_url(url: str) -> str:
    anmodning = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Plandata Supportmentor lokal kildeopdatering",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(anmodning, timeout=45) as svar:
        return svar.read().decode("utf-8", errors="replace")


def importer_plandata_side(kilde: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()
    url = str(kilde["url"]).strip()
    titel = str(kilde["titel"]).strip()
    omraade = str(kilde.get("omraade", "Plandata.dk")).strip()
    prioritet = int(kilde.get("prioritet", 0))
    side_id = "plandata:" + re.sub(r"[^a-z0-9]+", "-", url.casefold()).strip("-")

    try:
        indhold_html = hent_url(url)
    except (urllib.error.URLError, TimeoutError) as fejl:
        return {"ok": False, "titel": titel, "fejl": f"Kunne ikke hente siden: {fejl}"}

    tekst = udtraek_hovedindhold(indhold_html)
    if len(tekst) < 80:
        return {"ok": False, "titel": titel, "fejl": "Siden havde for lidt tekst til import."}

    chunks = lav_chunks(tekst)
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.execute(
            """
            INSERT INTO confluence_sider
                (side_id, titel, url, kilde_type, omraade, prioritet, forfaedre_json, version_tid, importeret_tid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(side_id) DO UPDATE SET
                titel=excluded.titel,
                url=excluded.url,
                kilde_type=excluded.kilde_type,
                omraade=excluded.omraade,
                prioritet=excluded.prioritet,
                forfaedre_json=excluded.forfaedre_json,
                version_tid=excluded.version_tid,
                importeret_tid=excluded.importeret_tid
            """,
            (
                side_id,
                titel,
                url,
                "Plandata.dk",
                omraade,
                prioritet,
                json.dumps(kilde.get("forfaedre", []), ensure_ascii=False),
                "",
                time.time(),
            ),
        )
        forbindelse.execute("DELETE FROM confluence_chunks WHERE side_id = ?", (side_id,))
        forbindelse.executemany(
            """
            INSERT INTO confluence_chunks
                (side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (side_id, nr, titel, url, "Plandata.dk", omraade, prioritet, chunk)
                for nr, chunk in enumerate(chunks, start=1)
            ],
        )

    return {"ok": True, "side_id": side_id, "titel": titel, "omraade": omraade, "chunks": len(chunks)}


def importer_mail_kilde(mail: dict[str, Any]) -> dict[str, Any]:
    initialiser_database()

    filsti = str(mail.get("filsti", "")).strip()
    emne = str(mail.get("emne", "")).strip() or Path(filsti).stem
    modtaget_tid = str(mail.get("modtaget_tid", "") or "")
    sendt_tid = str(mail.get("sendt_tid", "") or "")
    tekst = str(mail.get("tekst", "") or "").strip()

    if not filsti or not emne:
        return {"ok": False, "fejl": "Mailen mangler filsti eller emne."}
    if len(tekst) < 40:
        return {"ok": False, "titel": emne, "fejl": "Mailen havde for lidt tekst til import."}

    side_id = "mail:" + hashlib.sha256(filsti.casefold().encode("utf-8")).hexdigest()[:24]
    kilde_tekst = f"Emne: {emne}\nSendt: {sendt_tid}\nModtaget: {modtaget_tid}\n\n{tekst}".strip()
    chunks = lav_chunks(kilde_tekst)

    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.execute(
            """
            INSERT INTO confluence_sider
                (side_id, titel, url, kilde_type, omraade, prioritet, forfaedre_json, version_tid, importeret_tid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(side_id) DO UPDATE SET
                titel=excluded.titel,
                url=excluded.url,
                kilde_type=excluded.kilde_type,
                omraade=excluded.omraade,
                prioritet=excluded.prioritet,
                forfaedre_json=excluded.forfaedre_json,
                version_tid=excluded.version_tid,
                importeret_tid=excluded.importeret_tid
            """,
            (
                side_id,
                emne,
                filsti,
                "Mail",
                "Tidligere supportsager",
                3,
                json.dumps(["Vedhæftede mails"], ensure_ascii=False),
                sendt_tid or modtaget_tid,
                time.time(),
            ),
        )
        forbindelse.execute("DELETE FROM confluence_chunks WHERE side_id = ?", (side_id,))
        forbindelse.executemany(
            """
            INSERT INTO confluence_chunks
                (side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (side_id, nr, emne, filsti, "Mail", "Tidligere supportsager", 3, chunk)
                for nr, chunk in enumerate(chunks, start=1)
            ],
        )

    return {"ok": True, "side_id": side_id, "titel": emne, "omraade": "Tidligere supportsager", "chunks": len(chunks)}


def importer_dokument_kilde(dokument: dict[str, Any]) -> dict[str, Any]:
    """Importer et lokalt dokumentudtræk som kilde i vidensbasen."""
    initialiser_database()

    filsti = str(dokument.get("filsti", "")).strip()
    titel = str(dokument.get("titel", "")).strip() or Path(filsti).stem
    tekst = str(dokument.get("tekst", "") or "").strip()
    kilde_type = str(dokument.get("kilde_type", "Dokument")).strip() or "Dokument"
    omraade = str(dokument.get("omraade", "Dokumenter")).strip() or "Dokumenter"
    prioritet = max(0, min(9, int(dokument.get("prioritet", 5) or 5)))
    tags = normaliser_tags(dokument.get("tags", []))
    note = str(dokument.get("note", "") or "").strip()

    if not filsti or not titel:
        return {"ok": False, "fejl": "Dokumentet mangler filsti eller titel."}
    if len(tekst) < 40:
        return {"ok": False, "titel": titel, "fejl": "Dokumentet havde for lidt tekst til import."}

    side_id = "dokument:" + hashlib.sha256(filsti.casefold().encode("utf-8")).hexdigest()[:24]
    kilde_tekst = (
        f"Titel: {titel}\n"
        f"Kilde: {filsti}\n"
        f"Tags: {', '.join(tags) if tags else 'ingen'}\n"
        f"Note: {note or 'ingen'}\n\n"
        f"{tekst}"
    ).strip()
    chunks = lav_chunks(kilde_tekst)

    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.execute(
            """
            INSERT INTO confluence_sider
                (side_id, titel, url, kilde_type, omraade, prioritet, forfaedre_json, version_tid, importeret_tid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(side_id) DO UPDATE SET
                titel=excluded.titel,
                url=excluded.url,
                kilde_type=excluded.kilde_type,
                omraade=excluded.omraade,
                prioritet=excluded.prioritet,
                forfaedre_json=excluded.forfaedre_json,
                version_tid=excluded.version_tid,
                importeret_tid=excluded.importeret_tid
            """,
            (
                side_id,
                titel,
                filsti,
                kilde_type,
                omraade,
                prioritet,
                json.dumps(["Dokumentimport"], ensure_ascii=False),
                "",
                time.time(),
            ),
        )
        forbindelse.execute("DELETE FROM confluence_chunks WHERE side_id = ?", (side_id,))
        forbindelse.executemany(
            """
            INSERT INTO confluence_chunks
                (side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (side_id, nr, titel, filsti, kilde_type, omraade, prioritet, chunk)
                for nr, chunk in enumerate(chunks, start=1)
            ],
        )
        gem_kilde_tags(forbindelse, side_id, tags)

    return {"ok": True, "side_id": side_id, "titel": titel, "omraade": omraade, "tags": tags, "chunks": len(chunks)}


def opdater_plandata_kilder() -> dict[str, Any]:
    kilder = json.loads(PLANDATA_KILDER_FIL.read_text(encoding="utf-8"))
    resultater = [importer_plandata_side(kilde) for kilde in kilder]
    return {
        "ok": True,
        "kilder": len(kilder),
        "importeret": sum(1 for resultat in resultater if resultat.get("ok")),
        "fejlet": sum(1 for resultat in resultater if not resultat.get("ok")),
        "resultater": resultater,
        "status": status(),
    }


def score_chunk(query: str, titel: str, tekst: str, prioritet: int) -> int:
    query_ord = [
        ord
        for ord in re.findall(r"[\wæøåÆØÅ.-]{3,}", normaliser(query))
        if ord not in STOPORD
    ]
    tekst_norm = normaliser(f"{titel} {tekst}")
    score = max(0, 8 - prioritet)
    for ord in query_ord:
        if ord in tekst_norm:
            score += 24 if any(tegn.isdigit() for tegn in ord) else 8
    return score


def soeg_viden(query: str, maksimum: int = 8) -> list[dict[str, Any]]:
    initialiser_database()
    if not query.strip():
        return []

    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        tags_map = hent_tags_map(forbindelse)
        rækker = forbindelse.execute(
            """
            SELECT side_id, chunk_nr, titel, url, kilde_type, omraade, prioritet, tekst
            FROM confluence_chunks
            ORDER BY prioritet ASC, chunk_id ASC
            """
        ).fetchall()

    scorede: list[tuple[int, sqlite3.Row]] = []
    for række in rækker:
        tags = tags_map.get(str(række["side_id"]), [])
        score = score_chunk(query, f"{række['titel']} {' '.join(tags)}", række["tekst"], int(række["prioritet"]))
        grundscore = max(0, 8 - int(række["prioritet"]))
        if række["kilde_type"] == "Plandata.dk" and score > grundscore:
            score += 25
        if række["kilde_type"] == "Svarbank" and score > grundscore:
            score += 22
        if række["kilde_type"] == "Mail" and score > grundscore:
            score += 12
        query_norm = normaliser(query)
        if any(tag and tag in query_norm for tag in tags):
            score += 18
        if score > 8:
            scorede.append((score, række))
    scorede.sort(key=lambda punkt: (-punkt[0], punkt[1]["prioritet"], punkt[1]["titel"]))
    diversificeret: list[tuple[int, sqlite3.Row]] = []
    antal_pr_side: dict[str, int] = {}
    for score, række in scorede:
        side_id = str(række["side_id"])
        if antal_pr_side.get(side_id, 0) >= 2:
            continue
        diversificeret.append((score, række))
        antal_pr_side[side_id] = antal_pr_side.get(side_id, 0) + 1
        if len(diversificeret) >= maksimum:
            break

    return [
        {
            "side_id": række["side_id"],
            "chunk_nr": række["chunk_nr"],
            "titel": række["titel"],
            "url": række["url"],
            "kilde_type": række["kilde_type"],
            "omraade": række["omraade"],
            "prioritet": række["prioritet"],
            "tekst": række["tekst"],
            "score": score,
            "tags": tags_map.get(str(række["side_id"]), []),
        }
        for score, række in diversificeret
    ]


def status() -> dict[str, Any]:
    initialiser_database()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        antal_sider = forbindelse.execute("SELECT COUNT(*) AS antal FROM confluence_sider").fetchone()["antal"]
        antal_chunks = forbindelse.execute("SELECT COUNT(*) AS antal FROM confluence_chunks").fetchone()["antal"]
        antal_tags = forbindelse.execute("SELECT COUNT(*) AS antal FROM tags").fetchone()["antal"]
        antal_qa = forbindelse.execute("SELECT COUNT(*) AS antal FROM qa_svar").fetchone()["antal"]
        antal_relationer = forbindelse.execute("SELECT COUNT(*) AS antal FROM kilde_relationer").fetchone()["antal"]
        områder = forbindelse.execute(
            """
            SELECT kilde_type, omraade, COUNT(*) AS sider
            FROM confluence_sider
            GROUP BY kilde_type, omraade
            ORDER BY MIN(prioritet), kilde_type, omraade
            """
        ).fetchall()
    return {
        "database": str(DATABASE_FIL),
        "sider": antal_sider,
        "chunks": antal_chunks,
        "tags": antal_tags,
        "qa_svar": antal_qa,
        "relationer": antal_relationer,
        "omraader": [dict(række) for række in områder],
    }


def importerede_sider() -> list[dict[str, Any]]:
    initialiser_database()
    with sqlite3.connect(DATABASE_FIL) as forbindelse:
        forbindelse.row_factory = sqlite3.Row
        tags_map = hent_tags_map(forbindelse)
        rækker = forbindelse.execute(
            """
            SELECT side_id, titel, url, kilde_type, omraade, prioritet
            FROM confluence_sider
            ORDER BY prioritet, kilde_type, titel
            """
        ).fetchall()
    sider: list[dict[str, Any]] = []
    for række in rækker:
        punkt = dict(række)
        punkt["tags"] = tags_map.get(str(punkt["side_id"]), [])
        sider.append(punkt)
    return sider
