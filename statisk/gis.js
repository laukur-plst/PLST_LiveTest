const gisFilUpload = document.querySelector("#gisFilUpload");
const gisFejltekst = document.querySelector("#gisFejltekst");
const gisUploadListe = document.querySelector("#gisUploadListe");
const gisOpsummering = document.querySelector("#gisOpsummering");
const gisRapport = document.querySelector("#gisRapport");
const analyserGisKnap = document.querySelector("#analyserGis");
const sendTilSvarbaseKnap = document.querySelector("#sendTilSvarbase");
const kopierGisKnap = document.querySelector("#kopierGis");
const rydGisKnap = document.querySelector("#rydGis");
const gisStatus = document.querySelector("#gisStatus");

let senesteGisFiler = [];
let senesteRapport = "";

function sætGisStatus(tekst) {
  gisStatus.textContent = tekst;
}

function escapeHtml(tekst) {
  return String(tekst)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function visUploadListe(filer) {
  gisUploadListe.innerHTML = "";
  for (const fil of filer) {
    const element = document.createElement("article");
    element.className = "uploadkort";
    if (fil.kraever_ocr || fil.status !== "GIS-analyse udført") {
      element.classList.add("ocr");
    }

    const titel = document.createElement("strong");
    titel.textContent = fil.filnavn;

    const status = document.createElement("span");
    const tekstLængde = fil.tekst_laengde ? ` · ${fil.tekst_laengde} tegn` : "";
    status.textContent = `${fil.status || "Ingen status"}${tekstLængde}`;

    element.append(titel, status);
    gisUploadListe.appendChild(element);
  }
}

function findLinje(tekst, prefix) {
  return String(tekst || "")
    .split(/\r?\n/)
    .find((linje) => linje.toLowerCase().startsWith(prefix.toLowerCase()));
}

function lavOpsummering(filer) {
  const fund = [];
  const samletTekst = filer.map((fil) => fil.tekst || "").join("\n").toLowerCase();
  const analyseFiler = filer.filter((fil) => fil.status === "GIS-analyse udført");

  fund.push(`${analyseFiler.length}/${filer.length} filer fik GIS-analyse`);
  if (samletTekst.includes("mulige geometri-/strukturfejl")) {
    fund.push("Mulige geometri- eller strukturfejl fundet");
  }
  if (samletTekst.includes("crs: ikke angivet") || samletTekst.includes("prj: ikke fundet")) {
    fund.push("Koordinatsystem/PRJ bør kontrolleres");
  }
  if (samletTekst.includes("attributfelter: ingen")) {
    fund.push("Attributfelter mangler eller blev ikke læst");
  }
  if (samletTekst.includes("zip mangler") || samletTekst.includes("shp alene")) {
    fund.push("Shapefile-pakken ser ufuldstændig ud");
  }
  if (samletTekst.includes("buffer(0)") || samletTekst.includes("make valid")) {
    fund.push("Geometrireparation kan være relevant");
  }
  if (fund.length === 1 && analyseFiler.length > 0) {
    fund.push("Ingen åbenlyse fejl i basisvalideringen");
  }

  gisOpsummering.innerHTML = fund.map((punkt) => `<span>${escapeHtml(punkt)}</span>`).join("");
}

function lavRapport(filer) {
  const fejltekst = gisFejltekst.value.trim();
  const linjer = [
    "GIS-fejlsøgning",
    "",
    `Dato: ${new Date().toLocaleString("da-DK")}`,
  ];

  if (fejltekst) {
    linjer.push("", "Fejltekst eller kontekst", fejltekst);
  }

  for (const fil of filer) {
    linjer.push("", "----------------------------------------");
    linjer.push(`Fil: ${fil.filnavn}`);
    linjer.push(`Status: ${fil.status || "Ingen status"}`);
    if (fil.tekst) {
      linjer.push("", fil.tekst.trim());
      const bbox = findLinje(fil.tekst, "BBox:");
      const crs = findLinje(fil.tekst, "CRS:");
      const prj = findLinje(fil.tekst, "PRJ:");
      if (bbox || crs || prj) {
        linjer.push("", "Nøglepunkter");
        if (bbox) linjer.push(`- ${bbox}`);
        if (crs) linjer.push(`- ${crs}`);
        if (prj) linjer.push(`- ${prj}`);
      }
    } else {
      linjer.push("", "Der blev ikke udtrukket en GIS-rapport fra filen.");
    }
  }

  linjer.push(
    "",
    "Forbehold",
    "Dette er en basisanalyse uden fuld GIS-motor. Kontroller altid resultatet i GIS og mod Plandata.dk's aktuelle datamodel, obligatoriske felter og kodelister."
  );
  return linjer.join("\n");
}

async function analyserGis() {
  if (!gisFilUpload.files.length) {
    gisRapport.textContent = "Vælg mindst én GIS-fil først.";
    sætGisStatus("Mangler fil");
    return;
  }

  const formData = new FormData();
  for (const fil of gisFilUpload.files) {
    formData.append("filer", fil);
  }

  analyserGisKnap.disabled = true;
  sætGisStatus("Analyserer");
  gisRapport.textContent = "Analyserer filer...";
  gisOpsummering.innerHTML = "";

  try {
    const svar = await fetch("/api/filer/upload", {
      method: "POST",
      body: formData,
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "GIS-analysen fejlede");
    }

    senesteGisFiler = data.filer || [];
    senesteRapport = lavRapport(senesteGisFiler);
    visUploadListe(senesteGisFiler);
    lavOpsummering(senesteGisFiler);
    gisRapport.textContent = senesteRapport;
    sætGisStatus("Analyse klar");
  } catch (fejl) {
    gisRapport.textContent = `Fejl: ${fejl.message}`;
    sætGisStatus("Fejl");
  } finally {
    analyserGisKnap.disabled = false;
    gisFilUpload.value = "";
  }
}

async function kopierRapport() {
  if (!senesteRapport) {
    return;
  }
  await navigator.clipboard.writeText(senesteRapport);
  sætGisStatus("Kopieret");
}

function sendTilSvarbase() {
  if (!senesteRapport) {
    gisRapport.textContent = "Lav en GIS-analyse først.";
    sætGisStatus("Mangler rapport");
    return;
  }

  sessionStorage.setItem(
    "gisAnalyseTilSvarbase",
    JSON.stringify({
      rapport: senesteRapport,
      filnavne: senesteGisFiler.map((fil) => fil.filnavn),
      fejltekst: gisFejltekst.value.trim(),
      tid: new Date().toISOString(),
    })
  );
  window.location.href = "/";
}

function rydGis() {
  senesteGisFiler = [];
  senesteRapport = "";
  gisFilUpload.value = "";
  gisFejltekst.value = "";
  gisUploadListe.innerHTML = "";
  gisOpsummering.innerHTML = "";
  gisRapport.textContent = "Upload en GIS-fil for at danne en teknisk rapport.";
  sætGisStatus("Klar");
}

analyserGisKnap.addEventListener("click", analyserGis);
sendTilSvarbaseKnap.addEventListener("click", sendTilSvarbase);
kopierGisKnap.addEventListener("click", kopierRapport);
rydGisKnap.addEventListener("click", rydGis);
