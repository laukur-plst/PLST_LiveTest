"""Lokal webapplikation til Plandata Supports svarbase.

Serveren viser en statisk frontend og tilbyder et API, der sender
supporthenvendelser til AgentBase-flowet beskrevet i app_llm_kald.md.
API-nøglen læses kun lokalt fra adgangskoder.env ved kørsel.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import mimetypes
import os
import re
import secrets
import struct
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import vidensbase


ROD = Path(__file__).resolve().parent
STATISK_MAPPE = ROD / "statisk"
DATA_MAPPE = ROD / "data"
UPLOAD_MAPPE = DATA_MAPPE / "uploads"
KILDER_FIL = DATA_MAPPE / "videnskilder.json"
ADGANGSKODER_FIL = ROD / "adgangskoder.env"
IMPORT_TOKEN_FIL = DATA_MAPPE / "import_token.txt"
LLM_ENDPOINT = "https://api.flows.syv.ai/api/v1/apps/b6d24a0b-7473-4f1a-93ef-38793b529b96/run"
MULIGE_NOEGLE_NAVNE = ("API_KEY", "SYV_API_KEY", "AGENTBASE_API_KEY", "FLOW_API_KEY")
MAKS_UPLOAD_BYTES = 20 * 1024 * 1024
MAKS_FIL_BYTES = 12 * 1024 * 1024
MAKS_FILTEKST_TIL_LLM = 12000

SYSTEMPROMPT = """Du er Plandata Supportmentor.
Dit formål er at hjælpe medarbejdere i Plandata Support med at finde korrekte, konsistente og veldokumenterede svar til kommuner, rådgivere, systemleverandører og interne kolleger.

Du fungerer både som supportassistent, oplæringsværktøj for nye medarbejdere, videnssøgemaskine, kvalitetssikring af svar og guide til relevante vejledninger og skabeloner.

Du må aldrig opfinde svar. Hvis der ikke findes dokumentation eller kildegrundlag, skal du tydeligt skrive, at der mangler dokumentation, og foreslå hvilke oplysninger der skal fremskaffes.

Prioriter kilder i denne rækkefølge: Plandata.dk og officiel datamodel, godkendte svar fra Svarbank, relevant Confluence-vidensdeling, kodelister og datamodeller, REST API dokumentation, tidligere lignende supportsager, interne supportprocedurer, F2-procedurer og Jira-sager hvis relevant.

Supportens standardsvar er som udgangspunkt skabeloner til sager, der ikke er tilstrækkeligt oplyst eller ikke kræver egentlig supporthandling fra Plandata Support. De må ikke behandles som det fagligt rigtige svar til borgeren, kommunen eller rådgiveren, hvis sagen kræver konkret support, systemvejledning, datamodelafklaring eller fejlsøgning. Brug dem primært som formulering/skabelon til at bede om flere oplysninger, afslutte en sag uden handling eller forklare, at henvendelsen ikke kræver supporthandling.

Ved enhver henvendelse skal du identificere support-intent, finde relevante kilder, vurdere usikkerhed, udarbejde et svarudkast og give oplæringsforklaring når brugeren er ny medarbejder.

Returnér altid: Identificeret support-intent, Valgte kilder, Begrundelse, Svarudkast, Eventuelle usikkerheder og Forslag til opfølgende spørgsmål. Hvis et standardsvar vælges, skal du tydeligt forklare, om det kun bruges som skabelon, eller om der også findes egentligt kildegrundlag for svaret.
"""

INTENT_REGLER: list[tuple[str, tuple[str, ...]]] = [
    ("Udskiftning af plandokument", ("udskift", "erstat", "forkert pdf", "forkert plandokument", "ny pdf")),
    ("Ændring af plandokument", ("ændr", "rette plandokument", "opdater plandokument")),
    ("Høringsmeddelelse", ("høring", "høringsmeddelelse", "høringsperiode", "orienteringspligt", "parter")),
    ("Delvis aflysning", ("delvis aflys", "delvist aflys")),
    ("Aflysning af lokalplan", ("aflysning", "aflyse lokalplan", "aflys lokalplan")),
    ("Geometrifejl", ("geometri", "polygon", "kort", "spatial", "geometrifejl")),
    ("GIS-filvalidering", ("geojson", "gml", "shape", "shapefile", "gis", "epsg", "attribut", "datamodel", "buffer(0)", "buffer 0")),
    ("Uploadfejl", ("upload", "kan ikke indberette", "fejl ved upload")),
    ("Valideringsfejl", ("validering", "valideringsfejl", "fejlbesked")),
    ("Delområder", ("delområde", "delområder")),
    ("Byggefelter", ("byggefelt", "byggefelter")),
    ("Kommuneplanrammer", ("kommuneplanramme", "rammeområde", "rammer")),
    ("Brugerrettigheder", ("rettighed", "bruger", "login", "adgang")),
    ("REST API", ("rest api", "swagger", "dto", "json", "integration", "endpoint")),
    ("Kodelister", ("kodeliste", "kodeværdi", "kode")),
    ("Datamodel", ("datamodel", "felt", "relation")),
    ("Planstatus", ("forslag", "vedtaget", "kladde")),
]

SVARMODUS_REGLER: dict[str, dict[str, str]] = {
    "supportfagligt_svar": {
        "navn": "Supportfagligt svar",
        "instruktion": "Lav et eksternt anvendeligt svarudkast med konkret supportvejledning. Brug standardsvarsskabeloner med forsigtighed og kun som formulering, ikke som fagligt facit.",
    },
    "bed_om_flere_oplysninger": {
        "navn": "Bed om flere oplysninger",
        "instruktion": "Lav et kort svarudkast, der beder om de konkrete oplysninger, der mangler for at supporten kan behandle sagen. Her må standardsvarsskabeloner gerne bruges som primært formuleringsgrundlag.",
    },
    "intern_vurdering": {
        "navn": "Intern vurdering",
        "instruktion": "Lav en intern vurdering til supportmedarbejderen. Skeln tydeligt mellem dokumenteret viden, antagelser, usikkerheder og næste interne handling.",
    },
    "teknisk_fejlsoegning": {
        "navn": "Teknisk fejlsøgning",
        "instruktion": "Lav en teknisk fejlsøgningsanalyse. Prioriter konkrete fejlbeskeder, GIS-/filanalyse, datamodel, API-dokumentation, kodelister og kendte fejl over standardsvarsskabeloner.",
    },
    "planfaglig_baggrund": {
        "navn": "Planfaglig baggrund",
        "instruktion": "Lav en planfaglig baggrundsvurdering. Marker tydeligt, hvis kilderne er generel vejledning eller historiske dokumenter og ikke aktuel systemvejledning.",
    },
}


@dataclass(frozen=True)
class Kilde:
    titel: str
    type: str
    prioritet: int
    status: str
    beskrivelse: str
    noegleord: tuple[str, ...]


def laes_adgangskoder() -> dict[str, str]:
    """Læs nøgle-værdi-par fra adgangskoder.env uden at eksponere værdierne."""
    vaerdier: dict[str, str] = {}
    if not ADGANGSKODER_FIL.exists():
        return vaerdier

    for linje in ADGANGSKODER_FIL.read_text(encoding="utf-8-sig").splitlines():
        renset = linje.strip()
        if not renset or renset.startswith("#") or "=" not in renset:
            continue
        navn, vaerdi = renset.split("=", 1)
        vaerdier[navn.strip()] = vaerdi.strip().strip('"').strip("'")
    return vaerdier


def find_import_token() -> str:
    """Find eller opret lokal import-token til Confluence-import."""
    DATA_MAPPE.mkdir(parents=True, exist_ok=True)
    if IMPORT_TOKEN_FIL.exists():
        token = IMPORT_TOKEN_FIL.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    IMPORT_TOKEN_FIL.write_text(token, encoding="utf-8")
    return token


def find_api_noegle() -> str | None:
    for navn in MULIGE_NOEGLE_NAVNE:
        if os.environ.get(navn):
            return os.environ[navn]

    adgangskoder = laes_adgangskoder()
    for navn in MULIGE_NOEGLE_NAVNE:
        if adgangskoder.get(navn):
            return adgangskoder[navn]

    for vaerdi in adgangskoder.values():
        if vaerdi:
            return vaerdi
    return None


def laes_kilder() -> list[Kilde]:
    data = json.loads(KILDER_FIL.read_text(encoding="utf-8"))
    return [
        Kilde(
            titel=str(punkt["titel"]),
            type=str(punkt["type"]),
            prioritet=int(punkt["prioritet"]),
            status=str(punkt["status"]),
            beskrivelse=str(punkt["beskrivelse"]),
            noegleord=tuple(str(ord).lower() for ord in punkt.get("noegleord", [])),
        )
        for punkt in data
    ]


def normaliser(tekst: str) -> str:
    return re.sub(r"\s+", " ", tekst.casefold()).strip()


def identificer_intent(henvendelse: str) -> str:
    tekst = normaliser(henvendelse)
    for intent, noegleord in INTENT_REGLER:
        if any(ord in tekst for ord in noegleord):
            return intent
    return "Ikke sikkert identificeret - kræver manuel vurdering"


def normaliser_svarmodus(svarmodus: Any) -> str:
    valgt = str(svarmodus or "").strip()
    if valgt in SVARMODUS_REGLER:
        return valgt
    return "supportfagligt_svar"


def vaelg_kilder(henvendelse: str, ekstra_kontekst: str, svarmodus: str = "supportfagligt_svar") -> list[Kilde]:
    tekst = normaliser(f"{henvendelse} {ekstra_kontekst}")
    kilder = laes_kilder()
    scorede: list[tuple[int, Kilde]] = []

    for kilde in kilder:
        match_score = sum(1 for ord in kilde.noegleord if ord and ord in tekst)
        prioritet_bonus = max(0, 10 - kilde.prioritet)
        standardsvarsskabelon = "skabelon" in normaliser(f"{kilde.type} {kilde.titel}")
        if match_score or kilde.prioritet <= 2:
            score = match_score * 20 + prioritet_bonus
            if standardsvarsskabelon and svarmodus == "bed_om_flere_oplysninger":
                score += 16
            elif standardsvarsskabelon:
                score -= 14
            scorede.append((score, kilde))

    scorede.sort(key=lambda punkt: (-punkt[0], punkt[1].prioritet, punkt[1].titel))
    return [kilde for _, kilde in scorede[:6]]


def byg_kildegrundlag(kilder: list[Kilde]) -> str:
    linjer: list[str] = []
    for kilde in kilder:
        linjer.append(
            f"- {kilde.titel} ({kilde.type}, prioritet {kilde.prioritet})\n"
            f"  Status: {kilde.status}\n"
            f"  Relevans: {kilde.beskrivelse}"
        )
    return "\n".join(linjer)


def byg_indekseret_kildegrundlag(henvendelse: str, ekstra_kontekst: str) -> tuple[str, list[dict[str, Any]]]:
    resultater = vidensbase.soeg_viden(f"{henvendelse} {ekstra_kontekst}", maksimum=8)
    if not resultater:
        return "Der blev ikke fundet konkrete, importerede Confluence-uddrag i den lokale vidensbase.", []

    linjer: list[str] = []
    for nr, resultat in enumerate(resultater, start=1):
        tekst = resultat["tekst"].strip()
        if len(tekst) > 1200:
            tekst = tekst[:1200].rsplit(" ", 1)[0] + " ..."
        linjer.append(
            f"[{nr}] {resultat['titel']} ({resultat['omraade']}, prioritet {resultat['prioritet']})\n"
            f"URL: {resultat['url']}\n"
            f"Uddrag:\n{tekst}"
        )
    return "\n\n".join(linjer), resultater


def rens_filnavn(filnavn: str) -> str:
    """Lav et filnavn, der kan gemmes lokalt uden sti eller specialtegn."""
    navn = Path(filnavn).name.strip() or "upload"
    navn = re.sub(r"[^A-Za-z0-9æøåÆØÅ._ -]+", "_", navn)
    navn = re.sub(r"\s+", " ", navn).strip(" .")
    return navn[:140] or "upload"


def find_header_parameter(header: str, navn: str) -> str:
    match = re.search(rf'{re.escape(navn)}="([^"]*)"', header)
    if match:
        return match.group(1)
    match = re.search(rf"{re.escape(navn)}=([^;]+)", header)
    return match.group(1).strip() if match else ""


def parse_multipart_filer(raadata: bytes, content_type: str) -> list[dict[str, Any]]:
    """Udtræk filer fra en multipart/form-data-anmodning uden eksterne pakker."""
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
    if not match:
        raise ValueError("Upload mangler multipart-boundary.")

    boundary = (match.group(1) or match.group(2)).encode("utf-8")
    filer: list[dict[str, Any]] = []
    for deldata in raadata.split(b"--" + boundary):
        deldata = deldata.strip(b"\r\n")
        if not deldata or deldata == b"--":
            continue
        if deldata.endswith(b"--"):
            deldata = deldata[:-2].rstrip(b"\r\n")

        headerdata, separator, indhold = deldata.partition(b"\r\n\r\n")
        if not separator:
            continue

        headers: dict[str, str] = {}
        for linje in headerdata.decode("latin-1", errors="replace").splitlines():
            if ":" not in linje:
                continue
            header_navn, vaerdi = linje.split(":", 1)
            headers[header_navn.casefold().strip()] = vaerdi.strip()

        disposition = headers.get("content-disposition", "")
        filnavn = find_header_parameter(disposition, "filename")
        if filnavn:
            filer.append(
                {
                    "feltnavn": find_header_parameter(disposition, "name"),
                    "filnavn": filnavn,
                    "content_type": headers.get("content-type", "application/octet-stream"),
                    "indhold": indhold,
                }
            )
    return filer


def dekod_tekst(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def udtraek_docx_tekst(filsti: Path) -> str:
    with zipfile.ZipFile(filsti) as arkiv:
        dokument_xml = arkiv.read("word/document.xml")
    rod = ET.fromstring(dokument_xml)
    tekststykker = [
        element.text
        for element in rod.iter()
        if element.tag.endswith("}t") and element.text
    ]
    return "\n".join(tekststykker).strip()


def udtraek_pdf_tekst(filsti: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return "", "PDF-tekst kan ikke udtrækkes, fordi der ikke findes en lokal PDF-læser i runtime."

    try:
        reader = PdfReader(str(filsti))
        sider = [(side.extract_text() or "").strip() for side in reader.pages]
    except Exception as fejl:
        return "", f"PDF-tekst kunne ikke udtrækkes: {fejl}"
    return "\n\n".join(side for side in sider if side), ""


def lokalnavn(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def opdater_bbox(bbox: list[float] | None, koordinat: tuple[float, float]) -> list[float]:
    x, y = koordinat
    if bbox is None:
        return [x, y, x, y]
    bbox[0] = min(bbox[0], x)
    bbox[1] = min(bbox[1], y)
    bbox[2] = max(bbox[2], x)
    bbox[3] = max(bbox[3], y)
    return bbox


def formater_bbox(bbox: list[float] | None) -> str:
    if not bbox:
        return "ikke fundet"
    return f"{bbox[0]:.6f}, {bbox[1]:.6f}, {bbox[2]:.6f}, {bbox[3]:.6f}"


def kort_liste(punkter: list[str], maksimum: int = 18) -> str:
    unikke = sorted({punkt for punkt in punkter if punkt})
    if not unikke:
        return "ingen"
    if len(unikke) <= maksimum:
        return ", ".join(unikke)
    return ", ".join(unikke[:maksimum]) + f" ... (+{len(unikke) - maksimum})"


def koordinatpar(værdi: Any) -> tuple[float, float] | None:
    if not isinstance(værdi, list | tuple) or len(værdi) < 2:
        return None
    try:
        x = float(værdi[0])
        y = float(værdi[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return x, y


def ring_areal(ring: list[tuple[float, float]]) -> float:
    if len(ring) < 4:
        return 0.0
    areal = 0.0
    for indeks in range(len(ring) - 1):
        x1, y1 = ring[indeks]
        x2, y2 = ring[indeks + 1]
        areal += x1 * y2 - x2 * y1
    return abs(areal) / 2


def orientering(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segmenter_krydser(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    o1 = orientering(a, b, c)
    o2 = orientering(a, b, d)
    o3 = orientering(c, d, a)
    o4 = orientering(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def valider_ring(ring: list[tuple[float, float]], label: str) -> list[str]:
    fejl: list[str] = []
    if len(ring) < 4:
        return [f"{label}: polygonring har under 4 punkter."]
    if ring[0] != ring[-1]:
        fejl.append(f"{label}: polygonring er ikke lukket.")
    if ring_areal(ring) == 0:
        fejl.append(f"{label}: polygonring har areal 0.")
    for indeks in range(len(ring) - 1):
        if ring[indeks] == ring[indeks + 1]:
            fejl.append(f"{label}: gentaget nabopunkt ved punkt {indeks + 1}.")
            break
    segmenter = list(zip(ring[:-1], ring[1:]))
    for i, (a, b) in enumerate(segmenter):
        for j, (c, d) in enumerate(segmenter):
            if j <= i + 1:
                continue
            if i == 0 and j == len(segmenter) - 1:
                continue
            if segmenter_krydser(a, b, c, d):
                fejl.append(f"{label}: mulig selvskæring mellem segment {i + 1} og {j + 1}.")
                return fejl
    return fejl


def geojson_geometrier(geometri: dict[str, Any]) -> list[dict[str, Any]]:
    geometri_type = str(geometri.get("type", ""))
    if geometri_type == "GeometryCollection":
        geometrier: list[dict[str, Any]] = []
        for undergeometri in geometri.get("geometries", []):
            if isinstance(undergeometri, dict):
                geometrier.extend(geojson_geometrier(undergeometri))
        return geometrier
    return [geometri]


def geojson_koordinater(værdi: Any) -> list[tuple[float, float]]:
    koordinat = koordinatpar(værdi)
    if koordinat:
        return [koordinat]
    if isinstance(værdi, list):
        fundne: list[tuple[float, float]] = []
        for punkt in værdi:
            fundne.extend(geojson_koordinater(punkt))
        return fundne
    return []


def valider_geojson_geometri(geometri: dict[str, Any], label: str) -> tuple[list[str], list[tuple[float, float]]]:
    geometri_type = str(geometri.get("type", ""))
    koordinater = geometri.get("coordinates")
    fejl: list[str] = []
    punkter = geojson_koordinater(koordinater)

    if geometri_type == "Point" and not koordinatpar(koordinater):
        fejl.append(f"{label}: Point mangler gyldigt koordinatpar.")
    elif geometri_type == "LineString" and len(punkter) < 2:
        fejl.append(f"{label}: LineString har under 2 punkter.")
    elif geometri_type == "Polygon" and isinstance(koordinater, list):
        for ring_nr, ringdata in enumerate(koordinater, start=1):
            ring = [punkt for punkt in geojson_koordinater(ringdata)]
            fejl.extend(valider_ring(ring, f"{label}, ring {ring_nr}"))
    elif geometri_type == "MultiPolygon" and isinstance(koordinater, list):
        for polygon_nr, polygondata in enumerate(koordinater, start=1):
            if not isinstance(polygondata, list):
                continue
            for ring_nr, ringdata in enumerate(polygondata, start=1):
                ring = [punkt for punkt in geojson_koordinater(ringdata)]
                fejl.extend(valider_ring(ring, f"{label}, polygon {polygon_nr}, ring {ring_nr}"))
    elif not geometri_type:
        fejl.append(f"{label}: geometri mangler type.")

    return fejl, punkter


def analyser_geojson(data: dict[str, Any], filnavn: str) -> str:
    objekttype = str(data.get("type", ""))
    features: list[dict[str, Any]]
    if objekttype == "FeatureCollection":
        features = [feature for feature in data.get("features", []) if isinstance(feature, dict)]
    elif objekttype == "Feature":
        features = [data]
    elif "coordinates" in data:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        return ""

    bbox: list[float] | None = None
    felter: list[str] = []
    tomme_felter: dict[str, int] = {}
    geometrityper: list[str] = []
    fejl: list[str] = []
    tomme_geometrier = 0
    punktantal = 0

    for feature_nr, feature in enumerate(features, start=1):
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        for navn, værdi in properties.items():
            felter.append(str(navn))
            if værdi in (None, ""):
                tomme_felter[str(navn)] = tomme_felter.get(str(navn), 0) + 1

        geometri = feature.get("geometry")
        if not isinstance(geometri, dict):
            tomme_geometrier += 1
            fejl.append(f"Feature {feature_nr}: mangler geometri.")
            continue

        for delgeometri in geojson_geometrier(geometri):
            geometrityper.append(str(delgeometri.get("type", "Ukendt")))
            del_fejl, punkter = valider_geojson_geometri(delgeometri, f"Feature {feature_nr}")
            fejl.extend(del_fejl)
            punktantal += len(punkter)
            for punkt in punkter:
                bbox = opdater_bbox(bbox, punkt)

    crs = data.get("crs")
    crs_tekst = "ikke angivet"
    if isinstance(crs, dict):
        properties = crs.get("properties")
        if isinstance(properties, dict):
            crs_tekst = str(properties.get("name", "ikke angivet"))

    linjer = [
        "GIS-analyse af uploadet fil",
        f"Fil: {filnavn}",
        "Format: GeoJSON",
        f"Objekttype: {objekttype or 'ukendt'}",
        f"Features: {len(features)}",
        f"Geometrityper: {kort_liste(geometrityper)}",
        f"Koordinatpunkter: {punktantal}",
        f"BBox: {formater_bbox(bbox)}",
        f"CRS: {crs_tekst}",
        f"Attributfelter: {kort_liste(felter)}",
    ]
    if tomme_felter:
        linjer.append(
            "Tomme attributværdier: "
            + ", ".join(f"{navn}={antal}" for navn, antal in sorted(tomme_felter.items())[:18])
        )
    if tomme_geometrier:
        linjer.append(f"Tomme geometrier: {tomme_geometrier}")
    if fejl:
        linjer.append("Mulige geometri-/strukturfejl:")
        linjer.extend(f"- {punkt}" for punkt in fejl[:30])
        if len(fejl) > 30:
            linjer.append(f"- ... yderligere {len(fejl) - 30} fejl skjult")
        linjer.append("Typisk afhjælpning kan være at reparere geometrien i GIS, fx make valid eller buffer(0), og derefter kontrollere attributfelter mod Plandata.dk's datamodel.")
    else:
        linjer.append("Ingen åbenlyse geometri-/strukturfejl fundet i den indbyggede basisvalidering.")
        linjer.append("Sammenhold stadig attributfelter, datatyper, planstatus og kodelisteværdier med Plandata.dk's datamodel.")
    return "\n".join(linjer)


def analyser_gml(tekst: str, filnavn: str) -> str:
    if "<gml:" not in tekst and "opengis.net/gml" not in tekst:
        return ""
    try:
        rod = ET.fromstring(tekst.encode("utf-8"))
    except ET.ParseError as fejl:
        return "\n".join(
            [
                "GIS-analyse af uploadet fil",
                f"Fil: {filnavn}",
                "Format: GML/XML",
                f"XML'en kunne ikke parses: {fejl}",
            ]
        )

    geometri_tags = {
        "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon",
        "Surface", "MultiSurface", "Curve", "MultiCurve", "pos", "posList", "coordinates",
        "exterior", "interior", "LinearRing",
    }
    geometrier: list[str] = []
    attributter: list[str] = []
    bbox: list[float] | None = None
    punktantal = 0
    feature_count = 0

    for element in rod.iter():
        navn = lokalnavn(element.tag)
        if navn in {"featureMember", "member"}:
            feature_count += 1
        if navn in geometri_tags:
            if navn not in {"pos", "posList", "coordinates", "exterior", "interior", "LinearRing"}:
                geometrier.append(navn)
            if navn in {"pos", "posList", "coordinates"} and element.text:
                tal = [float(match.group(0)) for match in re.finditer(r"-?\d+(?:[.,]\d+)?", element.text.replace(",", "."))]
                for indeks in range(0, len(tal) - 1, 2):
                    bbox = opdater_bbox(bbox, (tal[indeks], tal[indeks + 1]))
                    punktantal += 1
        elif len(element) == 0 and element.text and element.text.strip():
            attributter.append(navn)

    linjer = [
        "GIS-analyse af uploadet fil",
        f"Fil: {filnavn}",
        "Format: GML/XML",
        f"Feature-medlemmer: {feature_count or 'ikke optalt'}",
        f"Geometrityper: {kort_liste(geometrier)}",
        f"Koordinatpunkter fundet: {punktantal}",
        f"BBox: {formater_bbox(bbox)}",
        f"Attribut-/elementfelter: {kort_liste(attributter)}",
    ]
    if not geometrier:
        linjer.append("Der blev ikke fundet kendte GML-geometrielementer. Kontroller namespace og eksportformat.")
    linjer.append("Kontroller især namespace, koordinatsystem, obligatoriske attributter, kodelisteværdier og om geometrierne matcher Plandata.dk's datamodel.")
    return "\n".join(linjer)


def parse_dbf_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 33:
        return {"records": 0, "felter": []}
    records = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    felter: list[str] = []
    offset = 32
    while offset + 32 <= min(header_len, len(data)):
        if data[offset] == 0x0D:
            break
        navn = data[offset : offset + 11].split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()
        felttype = chr(data[offset + 11])
        længde = data[offset + 16]
        if navn:
            felter.append(f"{navn} ({felttype}, {længde})")
        offset += 32
    return {"records": records, "felter": felter}


def parse_shp_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 100:
        return {"fejl": ["SHP-filen er for kort til en gyldig header."]}
    shape_type = struct.unpack("<i", data[32:36])[0]
    bbox = list(struct.unpack("<4d", data[36:68]))
    offset = 100
    records = 0
    fejl: list[str] = []
    shape_types: list[str] = []
    punktantal = 0

    while offset + 8 <= len(data):
        content_words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        content_bytes = content_words * 2
        record_start = offset + 8
        record_end = record_start + content_bytes
        if record_end > len(data) or content_bytes < 4:
            fejl.append(f"Record {records + 1}: record-længde ser ugyldig ud.")
            break
        records += 1
        record_type = struct.unpack("<i", data[record_start : record_start + 4])[0]
        shape_types.append(str(record_type))
        if record_type in {3, 5, 13, 15, 23, 25} and record_start + 44 <= record_end:
            num_parts = struct.unpack("<i", data[record_start + 36 : record_start + 40])[0]
            num_points = struct.unpack("<i", data[record_start + 40 : record_start + 44])[0]
            punktantal += max(num_points, 0)
            parts_start = record_start + 44
            points_start = parts_start + max(num_parts, 0) * 4
            if points_start + max(num_points, 0) * 16 <= record_end and record_type in {5, 15, 25}:
                parts = list(struct.unpack("<" + "i" * num_parts, data[parts_start:points_start])) if num_parts > 0 else []
                punkter = [
                    struct.unpack("<2d", data[points_start + indeks * 16 : points_start + indeks * 16 + 16])
                    for indeks in range(max(num_points, 0))
                ]
                for part_nr, start in enumerate(parts, start=1):
                    slut = parts[part_nr] if part_nr < len(parts) else len(punkter)
                    fejl.extend(valider_ring(punkter[start:slut], f"Record {records}, ring {part_nr}"))
        offset = record_end

    return {
        "shape_type": shape_type,
        "bbox": bbox,
        "records": records,
        "shape_types": shape_types,
        "punktantal": punktantal,
        "fejl": fejl,
    }


def analyser_shapefile_zip(filsti: Path, filnavn: str) -> str:
    try:
        with zipfile.ZipFile(filsti) as arkiv:
            navne = arkiv.namelist()
            shp_navn = next((navn for navn in navne if navn.casefold().endswith(".shp")), "")
            dbf_navn = next((navn for navn in navne if navn.casefold().endswith(".dbf")), "")
            shx_navn = next((navn for navn in navne if navn.casefold().endswith(".shx")), "")
            prj_navn = next((navn for navn in navne if navn.casefold().endswith(".prj")), "")
            shp = parse_shp_metadata(arkiv.read(shp_navn)) if shp_navn else {"fejl": ["ZIP mangler .shp-fil."]}
            dbf = parse_dbf_metadata(arkiv.read(dbf_navn)) if dbf_navn else {"records": 0, "felter": []}
            prj = arkiv.read(prj_navn).decode("latin-1", errors="replace")[:500] if prj_navn else "ikke fundet"
    except zipfile.BadZipFile:
        return ""

    linjer = [
        "GIS-analyse af uploadet fil",
        f"Fil: {filnavn}",
        "Format: Zipped shapefile",
        f"Indeholder .shp: {'ja' if shp_navn else 'nej'}",
        f"Indeholder .shx: {'ja' if shx_navn else 'nej'}",
        f"Indeholder .dbf: {'ja' if dbf_navn else 'nej'}",
        f"Indeholder .prj: {'ja' if prj_navn else 'nej'}",
        f"SHP records: {shp.get('records', 0)}",
        f"DBF records: {dbf.get('records', 0)}",
        f"Shape type: {shp.get('shape_type', 'ukendt')}",
        f"BBox: {formater_bbox(shp.get('bbox'))}",
        f"Koordinatpunkter: {shp.get('punktantal', 0)}",
        f"Attributfelter: {kort_liste(dbf.get('felter', []))}",
        f"PRJ: {prj}",
    ]
    if shp.get("records") and dbf.get("records") and shp.get("records") != dbf.get("records"):
        linjer.append("Mulig strukturfejl: antal SHP-records matcher ikke antal DBF-records.")
    fejl = list(shp.get("fejl", []))
    if fejl:
        linjer.append("Mulige geometri-/strukturfejl:")
        linjer.extend(f"- {punkt}" for punkt in fejl[:30])
        linjer.append("Typisk afhjælpning kan være at reparere polygoner i GIS, fx make valid eller buffer(0), og eksportere shapefilen igen inkl. .shp, .shx, .dbf og .prj.")
    else:
        linjer.append("Ingen åbenlyse geometri-/strukturfejl fundet i den indbyggede basisvalidering.")
    linjer.append("Sammenhold altid attributfelter og kodelisteværdier med Plandata.dk's datamodel før genupload.")
    return "\n".join(linjer)


def analyser_gis_fil(filsti: Path, content_type: str) -> str:
    filtype = filsti.suffix.casefold()
    if filtype in {".geojson", ".json"}:
        try:
            data = json.loads(dekod_tekst(filsti.read_bytes()))
        except json.JSONDecodeError:
            return ""
        if isinstance(data, dict):
            return analyser_geojson(data, filsti.name)
    if filtype in {".gml", ".xml"}:
        return analyser_gml(dekod_tekst(filsti.read_bytes()), filsti.name)
    if filtype == ".zip":
        return analyser_shapefile_zip(filsti, filsti.name)
    if filtype == ".shp":
        shp = parse_shp_metadata(filsti.read_bytes())
        linjer = [
            "GIS-analyse af uploadet fil",
            f"Fil: {filsti.name}",
            "Format: SHP uden tilhørende filer",
            f"SHP records: {shp.get('records', 0)}",
            f"Shape type: {shp.get('shape_type', 'ukendt')}",
            f"BBox: {formater_bbox(shp.get('bbox'))}",
            "Bemærk: .shp alene er ikke nok til attributanalyse. Upload normalt shapefile som ZIP med .shp, .shx, .dbf og .prj.",
        ]
        fejl = list(shp.get("fejl", []))
        if fejl:
            linjer.append("Mulige geometri-/strukturfejl:")
            linjer.extend(f"- {punkt}" for punkt in fejl[:30])
        return "\n".join(linjer)
    return ""


def udtraek_uploadtekst(filsti: Path, content_type: str) -> dict[str, Any]:
    filtype = filsti.suffix.casefold()
    try:
        gis_analyse = analyser_gis_fil(filsti, content_type)
        if gis_analyse:
            return {"tekst": gis_analyse[:MAKS_FILTEKST_TIL_LLM], "status": "GIS-analyse udført", "kraever_ocr": False}
        if filtype in {".txt", ".md", ".csv", ".json", ".xml", ".log"}:
            tekst = dekod_tekst(filsti.read_bytes())
        elif filtype in {".html", ".htm"} or "html" in content_type:
            tekst = vidensbase.html_til_tekst(dekod_tekst(filsti.read_bytes()))
        elif filtype == ".docx":
            tekst = udtraek_docx_tekst(filsti)
        elif filtype == ".pdf":
            tekst, fejl = udtraek_pdf_tekst(filsti)
            if fejl:
                return {"tekst": "", "status": fejl, "kraever_ocr": True}
            if len(tekst.strip()) < 40:
                return {
                    "tekst": "",
                    "status": "PDF'en har ikke udtrækkelig tekst og skal OCR-læses.",
                    "kraever_ocr": True,
                }
        elif filtype in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
            return {
                "tekst": "",
                "status": "Billedfilen kræver OCR eller vision-model, før indholdet kan bruges.",
                "kraever_ocr": True,
            }
        elif filtype == ".msg":
            return {
                "tekst": "",
                "status": "MSG-filer kræver Outlook/MSG-parser og bør importeres som mailkilde eller håndteres særskilt.",
                "kraever_ocr": False,
            }
        else:
            tekst = dekod_tekst(filsti.read_bytes())

        tekst = re.sub(r"\s+\n", "\n", tekst)
        tekst = re.sub(r"\n{4,}", "\n\n\n", tekst).strip()
        if len(tekst) < 20:
            return {
                "tekst": "",
                "status": "Filen havde for lidt udtrækkelig tekst til at indgå i svaret.",
                "kraever_ocr": filtype == ".pdf",
            }
        return {"tekst": tekst[:MAKS_FILTEKST_TIL_LLM], "status": "Tekst udtrukket", "kraever_ocr": False}
    except Exception as fejl:
        return {"tekst": "", "status": f"Filen kunne ikke læses: {fejl}", "kraever_ocr": filtype == ".pdf"}


def haandter_filupload(raadata: bytes, content_type: str) -> dict[str, Any]:
    if len(raadata) > MAKS_UPLOAD_BYTES:
        return {"ok": False, "fejl": "Uploadet er for stort. Maksimum er 20 MB samlet."}

    try:
        filer = parse_multipart_filer(raadata, content_type)
    except ValueError as fejl:
        return {"ok": False, "fejl": str(fejl)}

    if not filer:
        return {"ok": False, "fejl": "Der blev ikke fundet filer i uploadet."}

    UPLOAD_MAPPE.mkdir(parents=True, exist_ok=True)
    resultater: list[dict[str, Any]] = []
    for fil in filer:
        indhold = bytes(fil["indhold"])
        originalt_filnavn = str(fil["filnavn"])
        fil_id = uuid.uuid4().hex
        if len(indhold) > MAKS_FIL_BYTES:
            resultater.append(
                {
                    "fil_id": fil_id,
                    "filnavn": originalt_filnavn,
                    "status": "Filen er for stor. Maksimum er 12 MB pr. fil.",
                    "tekst": "",
                    "tekst_laengde": 0,
                    "kraever_ocr": False,
                }
            )
            continue

        gemt_sti = UPLOAD_MAPPE / f"{fil_id}_{rens_filnavn(originalt_filnavn)}"
        gemt_sti.write_bytes(indhold)
        udtraek = udtraek_uploadtekst(gemt_sti, str(fil.get("content_type", "")))
        tekst = str(udtraek.get("tekst", ""))
        resultater.append(
            {
                "fil_id": fil_id,
                "filnavn": originalt_filnavn,
                "status": str(udtraek.get("status", "")),
                "tekst": tekst,
                "tekst_laengde": len(tekst),
                "kraever_ocr": bool(udtraek.get("kraever_ocr", False)),
            }
        )

    return {"ok": True, "filer": resultater}


def normaliser_uploadede_filer(uploadede_filer: Any) -> list[dict[str, Any]]:
    if not isinstance(uploadede_filer, list):
        return []
    normaliserede: list[dict[str, Any]] = []
    for fil in uploadede_filer:
        if not isinstance(fil, dict):
            continue
        normaliserede.append(
            {
                "filnavn": str(fil.get("filnavn", "Ukendt fil")).strip()[:180],
                "status": str(fil.get("status", "")).strip()[:300],
                "tekst": str(fil.get("tekst", "")).strip()[:MAKS_FILTEKST_TIL_LLM],
                "kraever_ocr": bool(fil.get("kraever_ocr", False)),
            }
        )
    return normaliserede


def byg_fil_kontekst(uploadede_filer: list[dict[str, Any]]) -> str:
    if not uploadede_filer:
        return "(ingen uploadede filer)"

    blokke: list[str] = []
    for nr, fil in enumerate(uploadede_filer, start=1):
        filnavn = fil["filnavn"]
        status = fil["status"] or "Ingen status"
        tekst = fil["tekst"]
        if tekst:
            blokke.append(f"[Fil {nr}] {filnavn}\nStatus: {status}\nUdtrukket tekst:\n{tekst}")
        else:
            note = "Indholdet kan ikke bruges som tekstgrundlag endnu."
            if fil["kraever_ocr"]:
                note = "Indholdet kræver OCR/vision-læsning, før det kan bruges som tekstgrundlag."
            blokke.append(f"[Fil {nr}] {filnavn}\nStatus: {status}\nNote: {note}")
    return "\n\n".join(blokke)


def byg_llm_input(
    henvendelse: str,
    ekstra_kontekst: str,
    ny_medarbejder: bool,
    svarmodus: str,
    kilder: list[Kilde],
    uploadede_filer: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    fil_kontekst = byg_fil_kontekst(uploadede_filer or [])
    konkrete_kilder, _ = byg_indekseret_kildegrundlag(henvendelse, f"{ekstra_kontekst}\n{fil_kontekst}")
    modus = SVARMODUS_REGLER[normaliser_svarmodus(svarmodus)]
    instruktion = f"""{SYSTEMPROMPT}

Du skal svare på dansk og følge outputformatet præcist.
Svarmodus er: {modus["navn"]}. {modus["instruktion"]}
Brug kun det kildegrundlag, der er sendt med. Hvis kildegrundlaget kun består af kildehenvisninger uden konkret dokumentation, må du ikke foregive at have læst dokumentationen.
Når der er konkrete importerede Confluence-uddrag, skal du bruge dem som dokumenteret grundlag og henvise til sidetitlerne.
Uploadede filer er bilag til den konkrete henvendelse. Brug kun filindhold, hvor der faktisk er udtrukket tekst. Hvis en fil er markeret som OCR-krævende, skal du nævne, at den ikke er læst endnu.
Hvis en uploadet fil indeholder en GIS-analyse, skal du bruge den som teknisk fejlfindingsgrundlag. Vurder både geometri, koordinatsystem, attributfelter, obligatoriske datamodelfelter, kodelisteværdier og typiske reparationsspor som make valid eller buffer(0). Du må ikke konkludere, at en geometri er endeligt gyldig, når analysen kun er basisvalidering uden fuld GIS-motor.
Marker tydeligt manglende dokumentation og foreslå konkrete oplysninger, der bør fremskaffes.
{"Medtag en kort oplæringsforklaring til en ny medarbejder." if ny_medarbejder else "Hold oplæringsdelen kort og kun hvor den er nødvendig."}
"""

    indhold = f"""Henvendelse:
{henvendelse.strip()}

Ekstra kontekst fra supportmedarbejderen:
{ekstra_kontekst.strip() or "(ingen ekstra kontekst)"}

Svarmodus:
{modus["navn"]} - {modus["instruktion"]}

Uploadede filer og udtrukket tekst:
{fil_kontekst}

Forhåndsidentificeret intent:
{identificer_intent(henvendelse)}

Valgte kildehenvisninger:
{byg_kildegrundlag(kilder)}

Konkrete importerede Confluence-uddrag:
{konkrete_kilder}
"""
    return instruktion, indhold


def kald_llm(instruktion: str, indhold: str) -> str:
    api_noegle = find_api_noegle()
    if not api_noegle:
        raise RuntimeError("Der mangler API-nøgle i miljøvariabler eller adgangskoder.env.")

    payload = json.dumps(
        {
            "inputs": {
                "indhold_tekst": indhold,
                "instruktion_tekst": instruktion,
            }
        }
    ).encode("utf-8")
    anmodning = urllib.request.Request(
        LLM_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_noegle}",
            "Content-Type": "application/json",
        },
    )

    try:
        direkte_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direkte_opener.open(anmodning, timeout=90) as svar:
            data = json.loads(svar.read().decode("utf-8"))
    except urllib.error.HTTPError as fejl:
        besked = fejl.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM-kaldet fejlede med HTTP {fejl.code}: {besked}") from fejl
    except urllib.error.URLError as fejl:
        raise RuntimeError(f"LLM-kaldet kunne ikke gennemføres: {fejl.reason}") from fejl

    if isinstance(data, dict):
        if isinstance(data.get("svar"), str):
            return data["svar"]
        results = data.get("results")
        if isinstance(results, dict) and isinstance(results.get("svar"), str):
            return results["svar"]
        outputs = data.get("outputs")
        if isinstance(outputs, dict) and isinstance(outputs.get("svar"), str):
            return outputs["svar"]

    raise RuntimeError("LLM-svaret havde et uventet format.")


def byg_lokalt_svar(
    henvendelse: str,
    ekstra_kontekst: str,
    svarmodus: str,
    kilder: list[Kilde],
    fejlbesked: str,
    uploadede_filer: list[dict[str, Any]] | None = None,
) -> str:
    intent = identificer_intent(henvendelse)
    modus = SVARMODUS_REGLER[normaliser_svarmodus(svarmodus)]
    kilde_liste = "\n".join(f"- {kilde.titel} ({kilde.type}) - {kilde.status}" for kilde in kilder)
    fil_note = byg_fil_kontekst(uploadede_filer or [])
    return f"""Identificeret support-intent
{intent}

Valgte kilder
{kilde_liste}

Begrundelse
Svarmodus er {modus["navn"]}. {modus["instruktion"]}

Der er valgt kilder efter systempromptens prioritering, hvor Plandata.dk, officiel datamodel, godkendte Svarbank-svar og egentlig vidensdeling vægtes før standardsvarsskabeloner. Det konkrete kildeindhold er endnu ikke importeret i svarbasen.

Svarudkast
Tak for henvendelsen. Vi skal først have bekræftet det relevante kildegrundlag, før vi kan give et endeligt svar. Umiddelbart peger henvendelsen på: {intent}.

Når den relevante vejledning, datamodel eller godkendte videnskilde er fundet, bør svaret formuleres konkret med henvisning til den dokumenterede procedure og de handlinger, kommunen eller systemleverandøren skal udføre. Standardsvar bør kun bruges som skabelon, hvis sagen mangler oplysninger eller ikke kræver supporthandling.

Eventuelle usikkerheder
- Der mangler konkret dokumentation i svarbasen for de valgte kilder.
- LLM-kaldet blev ikke gennemført: {fejlbesked}
- Hvis sagen kræver juridisk eller planfaglig vurdering, skal den kvalitetssikres manuelt.

Forslag til opfølgende spørgsmål
- Kræver sagen egentlig supporthandling, eller er den egnet til en standardsvarsskabelon, fordi den mangler oplysninger eller kan afsluttes uden handling?
- Hvilken plantype og planstatus handler sagen om?
- Er der en fejlbesked, sagsreference eller et konkret plandokument, der bør indgå?
- Skal sagen håndteres som intern procedure, F2-sag eller teknisk fejl?

Internt notat
Ekstra kontekst modtaget: {ekstra_kontekst.strip() or "ingen"}

Uploadede filer:
{fil_note}"""


SVAR_SEKTIONER = {
    "identificeret support-intent": "Identificeret support-intent",
    "valgte kilder": "Valgte kilder",
    "begrundelse": "Begrundelse",
    "svarudkast": "Svarudkast",
    "eventuelle usikkerheder": "Eventuelle usikkerheder",
    "forslag til opfølgende spørgsmål": "Forslag til opfølgende spørgsmål",
    "internt notat": "Internt notat",
}


def normaliser_svaroverskrift(linje: str) -> str:
    renset = linje.strip()
    renset = re.sub(r"^#{1,6}\s*", "", renset)
    renset = renset.strip("*_ ")
    renset = renset.rstrip(":").strip()
    return normaliser(renset)


def lav_kildeadvarsler(
    konkrete_kilder: list[dict[str, Any]],
    uploadede_filer: list[dict[str, Any]],
    svarmodus: str,
) -> list[str]:
    advarsler: list[str] = []
    if not konkrete_kilder:
        advarsler.append("Der er ikke fundet konkrete importerede kildeuddrag. Svaret skal kvalitetssikres ekstra, før det bruges eksternt.")

    typer = [normaliser(str(kilde.get("kilde_type", ""))) for kilde in konkrete_kilder]
    omraader = [normaliser(str(kilde.get("omraade", ""))) for kilde in konkrete_kilder]
    titler = [normaliser(str(kilde.get("titel", ""))) for kilde in konkrete_kilder]
    samlet = " ".join(typer + omraader + titler)

    har_standardsvar = "standardsvar" in samlet or "skabelon" in samlet
    har_historisk = "historisk" in samlet
    har_mail = any(kilde_type == "mail" for kilde_type in typer)
    har_planfaglig = "planfaglig vejledning" in samlet or "ikke system vejledning" in samlet
    har_stærk_kilde = any(
        kilde_type in {"plandata.dk", "svarbank"} or "datamodel/api" in omraade
        for kilde_type, omraade in zip(typer, omraader)
    )
    har_ocr_afventer = any(bool(fil.get("kraever_ocr")) for fil in uploadede_filer)

    if har_standardsvar and svarmodus != "bed_om_flere_oplysninger":
        advarsler.append("Standardsvar indgår i kildegrundlaget. De skal normalt forstås som skabeloner til manglende oplysninger eller sager uden supporthandling, ikke som fagligt facit.")
    elif har_standardsvar:
        advarsler.append("Standardsvar indgår som skabelongrundlag, hvilket passer til svarmodus 'Bed om flere oplysninger'.")

    if har_historisk:
        advarsler.append("Historiske PlanDK-/PlansystemDK-dokumenter indgår. De må kun bruges som baggrund og skal kontrolleres mod aktuelle Plandata.dk-kilder og gældende datamodel.")

    if har_mail:
        advarsler.append("Tidligere mails indgår. De kan vise praksis og formuleringer, men bør ikke stå alene som dokumentation.")

    if har_planfaglig:
        advarsler.append("Generel planfaglig vejledning indgår. Den er ikke nødvendigvis systemvejledning for Plandata.dk.")

    if konkrete_kilder and not har_stærk_kilde:
        advarsler.append("Der er ikke fundet Plandata.dk-, Svarbank- eller datamodel/API-kilder blandt de konkrete uddrag. Overvej at fremsøge stærkere kilder.")

    if har_ocr_afventer:
        advarsler.append("Mindst ét bilag kræver OCR/vision-læsning og er derfor ikke brugt som fuldt tekstgrundlag.")

    return advarsler


def opdel_svartekst(
    svar: str,
    intent: str,
    llm_status: str,
    svarmodus: str,
    konkrete_kilder: list[dict[str, Any]],
    uploadede_filer: list[dict[str, Any]],
) -> dict[str, str]:
    """Del samlet LLM-svar i kopierbart svarudkast og internt resultatnotat."""
    sektioner: list[tuple[str, list[str]]] = []
    aktuel_titel = "Internt notat"
    aktuelle_linjer: list[str] = []

    for linje in svar.replace("\r\n", "\n").split("\n"):
        overskrift = SVAR_SEKTIONER.get(normaliser_svaroverskrift(linje))
        if overskrift:
            if aktuelle_linjer or sektioner:
                sektioner.append((aktuel_titel, aktuelle_linjer))
            aktuel_titel = overskrift
            aktuelle_linjer = []
            continue
        aktuelle_linjer.append(linje)
    sektioner.append((aktuel_titel, aktuelle_linjer))

    svarudkast = ""
    modus = SVARMODUS_REGLER[normaliser_svarmodus(svarmodus)]
    kildeadvarsler = lav_kildeadvarsler(konkrete_kilder, uploadede_filer, normaliser_svarmodus(svarmodus))
    interne_dele: list[str] = [
        "Teknisk metadata",
        f"- Intent: {intent}",
        f"- Svarmodus: {modus['navn']}",
        f"- LLM-status: {llm_status}",
        f"- Konkrete kilder fundet: {len(konkrete_kilder)}",
        f"- Uploadede filer: {len(uploadede_filer)}",
    ]
    if kildeadvarsler:
        interne_dele.append("")
        interne_dele.append("Kildeadvarsler")
        interne_dele.extend(f"- {advarsel}" for advarsel in kildeadvarsler)
    else:
        interne_dele.append("")
        interne_dele.append("Kildeadvarsler")
        interne_dele.append("- Ingen særlige kildeadvarsler ud fra den nuværende kontrol.")

    for titel, linjer in sektioner:
        indhold = "\n".join(linjer).strip()
        if not indhold:
            continue
        if titel == "Svarudkast" and not svarudkast:
            svarudkast = indhold
        else:
            interne_dele.append("")
            interne_dele.append(titel)
            interne_dele.append(indhold)

    if not svarudkast:
        svarudkast = svar.strip()
        interne_dele.append("")
        interne_dele.append("Opdeling")
        interne_dele.append("Svarudkast-sektionen kunne ikke findes sikkert, så hele svaret vises i svarfeltet.")

    return {
        "svarudkast": svarudkast,
        "resultatnotat": "\n".join(interne_dele).strip(),
        "kildeadvarsler": "\n".join(kildeadvarsler),
    }


def besvar_henvendelse(data: dict[str, Any]) -> dict[str, Any]:
    henvendelse = str(data.get("henvendelse", "")).strip()
    ekstra_kontekst = str(data.get("ekstra_kontekst", "")).strip()
    ny_medarbejder = bool(data.get("ny_medarbejder", False))
    svarmodus = normaliser_svarmodus(data.get("svarmodus"))
    uploadede_filer = normaliser_uploadede_filer(data.get("uploadede_filer", []))
    samlet_kontekst = f"{ekstra_kontekst}\n{byg_fil_kontekst(uploadede_filer)}"

    if not henvendelse:
        return {
            "ok": False,
            "fejl": "Skriv en henvendelse, før der kan laves et svarudkast.",
        }

    kilder = vaelg_kilder(henvendelse, samlet_kontekst, svarmodus)
    _, konkrete_kilder = byg_indekseret_kildegrundlag(henvendelse, samlet_kontekst)
    instruktion, indhold = byg_llm_input(henvendelse, ekstra_kontekst, ny_medarbejder, svarmodus, kilder, uploadede_filer)

    try:
        svar = kald_llm(instruktion, indhold)
        llm_status = "LLM-kald gennemført"
    except RuntimeError as fejl:
        svar = byg_lokalt_svar(henvendelse, ekstra_kontekst, svarmodus, kilder, str(fejl), uploadede_filer)
        llm_status = "Lokalt fallback-svar"

    intent = identificer_intent(henvendelse)
    opdeling = opdel_svartekst(svar, intent, llm_status, svarmodus, konkrete_kilder, uploadede_filer)
    modus = SVARMODUS_REGLER[svarmodus]

    return {
        "ok": True,
        "intent": intent,
        "svarmodus": svarmodus,
        "svarmodus_navn": modus["navn"],
        "llm_status": llm_status,
        "svar": svar,
        "svarudkast": opdeling["svarudkast"],
        "resultatnotat": opdeling["resultatnotat"],
        "kildeadvarsler": opdeling["kildeadvarsler"],
        "kilder": [kilde.__dict__ | {"noegleord": list(kilde.noegleord)} for kilde in kilder],
        "konkrete_kilder": [
            {
                "titel": kilde["titel"],
                "url": kilde["url"],
                "kilde_type": kilde["kilde_type"],
                "omraade": kilde["omraade"],
                "prioritet": kilde["prioritet"],
                "chunk_nr": kilde["chunk_nr"],
                "score": kilde["score"],
                "tags": kilde.get("tags", []),
            }
            for kilde in konkrete_kilder
        ],
    }


class SvarbaseHandler(BaseHTTPRequestHandler):
    server_version = "PlandataSvarbase/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        indhold = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(indhold)))
        self.end_headers()
        self.wfile.write(indhold)

    def do_GET(self) -> None:
        url_sti = urlsplit(self.path).path
        if url_sti == "/api/kilder":
            kilder = [kilde.__dict__ | {"noegleord": list(kilde.noegleord)} for kilde in laes_kilder()]
            self.send_json({"ok": True, "kilder": kilder})
            return
        if url_sti == "/api/vidensbase/status":
            self.send_json({"ok": True, "status": vidensbase.status()})
            return
        if url_sti == "/api/vidensbase/sider":
            self.send_json({"ok": True, "sider": vidensbase.importerede_sider()})
            return
        if url_sti == "/api/svarbank":
            self.send_json({"ok": True, "svar": vidensbase.hent_qa_svar()})
            return
        if url_sti == "/api/tags":
            self.send_json({"ok": True, "tags": vidensbase.hent_tags()})
            return
        if url_sti == "/api/kilder/relationer":
            self.send_json({"ok": True, "relationer": vidensbase.hent_kilde_relationer()})
            return

        sti = url_sti.strip("/")
        fil = STATISK_MAPPE / (sti or "index.html")
        if not fil.resolve().is_relative_to(STATISK_MAPPE.resolve()) or not fil.exists() or not fil.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Filen blev ikke fundet")
            return

        indhold = fil.read_bytes()
        mime_type = mimetypes.guess_type(fil.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(indhold)))
        self.end_headers()
        self.wfile.write(indhold)

    def do_POST(self) -> None:
        url_sti = urlsplit(self.path).path
        laengde = int(self.headers.get("Content-Length", "0"))
        raadata = self.rfile.read(laengde)

        if url_sti == "/api/filer/upload":
            resultat = haandter_filupload(raadata, self.headers.get("Content-Type", ""))
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        try:
            tekst = raadata.decode("utf-8")
        except UnicodeDecodeError:
            tekst = raadata.decode("utf-16", errors="replace")

        try:
            data = json.loads(tekst)
        except json.JSONDecodeError:
            self.send_json({"ok": False, "fejl": "Ugyldigt JSON-format."}, HTTPStatus.BAD_REQUEST)
            return

        if url_sti == "/api/svar":
            svar = besvar_henvendelse(data)
            status = HTTPStatus.OK if svar.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(svar, status)
            return

        if url_sti == "/api/svarbank/gem":
            resultat = vidensbase.gem_qa_svar(data)
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        if url_sti == "/api/kilder/metadata":
            resultat = vidensbase.opdater_kilde_metadata(data)
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        if url_sti == "/api/kilder/relation":
            resultat = vidensbase.gem_kilde_relation(data)
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        if url_sti == "/api/import/confluence-side":
            token = self.headers.get("X-Import-Token", "")
            if not secrets.compare_digest(token, find_import_token()):
                self.send_json({"ok": False, "fejl": "Import-token mangler eller er forkert."}, HTTPStatus.FORBIDDEN)
                return
            resultat = vidensbase.importer_confluence_side(data)
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        if url_sti == "/api/kilder/opdater-plandata":
            resultat = vidensbase.opdater_plandata_kilder()
            self.send_json(resultat)
            return

        if url_sti == "/api/import/mail-kilde":
            token = self.headers.get("X-Import-Token", "")
            if not secrets.compare_digest(token, find_import_token()):
                self.send_json({"ok": False, "fejl": "Import-token mangler eller er forkert."}, HTTPStatus.FORBIDDEN)
                return
            resultat = vidensbase.importer_mail_kilde(data)
            status = HTTPStatus.OK if resultat.get("ok") else HTTPStatus.BAD_REQUEST
            self.send_json(resultat, status)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint blev ikke fundet")


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Plandata Supportmentors lokale svarbase.")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse serveren skal lytte på.")
    parser.add_argument("--port", default=8765, type=int, help="Port serveren skal lytte på.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SvarbaseHandler)
    print(f"Plandata Supportmentor kører på http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeren er stoppet.")


if __name__ == "__main__":
    main()
