const henvendelseFelt = document.querySelector("#henvendelse");
const ekstraKontekstFelt = document.querySelector("#ekstraKontekst");
const nyMedarbejderFelt = document.querySelector("#nyMedarbejder");
const svarmodusFelt = document.querySelector("#svarmodus");
const filUploadFelt = document.querySelector("#filUpload");
const uploadListe = document.querySelector("#uploadListe");
const sendKnap = document.querySelector("#sendKnap");
const rydKnap = document.querySelector("#rydKnap");
const kopierKnap = document.querySelector("#kopierKnap");
const svarfelt = document.querySelector("#svarfelt");
const resultatfelt = document.querySelector("#resultatfelt");
const intentFelt = document.querySelector("#intent");
const statusFelt = document.querySelector("#llmStatus");
const kildeliste = document.querySelector("#kildeliste");
const kildesøgning = document.querySelector("#kildesøgning");

let alleKilder = [];
let uploadedeFiler = [];
let senesteSvar = "Svarudkastet vises her.";
let senesteResultat = "Metadata og interne overvejelser vises her.";

function sætStatus(tekst) {
  statusFelt.textContent = tekst;
}

function escapeHtml(tekst) {
  return String(tekst)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(tekst) {
  let html = escapeHtml(tekst);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return html;
}

function renderMarkdown(markdown) {
  const linjer = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let listeType = "";
  let iKodeblok = false;
  let kodeblok = [];

  function lukListe() {
    if (listeType) {
      html.push(`</${listeType}>`);
      listeType = "";
    }
  }

  for (const linje of linjer) {
    if (linje.trim().startsWith("```")) {
      if (iKodeblok) {
        html.push(`<pre><code>${escapeHtml(kodeblok.join("\n"))}</code></pre>`);
        kodeblok = [];
        iKodeblok = false;
      } else {
        lukListe();
        iKodeblok = true;
      }
      continue;
    }
    if (iKodeblok) {
      kodeblok.push(linje);
      continue;
    }

    const trimmet = linje.trim();
    if (!trimmet) {
      lukListe();
      continue;
    }

    const overskrift = trimmet.match(/^(#{1,3})\s+(.+)$/);
    if (overskrift) {
      lukListe();
      const niveau = overskrift[1].length + 2;
      html.push(`<h${niveau}>${renderInlineMarkdown(overskrift[2])}</h${niveau}>`);
      continue;
    }

    const punkt = trimmet.match(/^[-*]\s+(.+)$/);
    if (punkt) {
      if (listeType !== "ul") {
        lukListe();
        listeType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${renderInlineMarkdown(punkt[1])}</li>`);
      continue;
    }

    const nummereret = trimmet.match(/^\d+\.\s+(.+)$/);
    if (nummereret) {
      if (listeType !== "ol") {
        lukListe();
        listeType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${renderInlineMarkdown(nummereret[1])}</li>`);
      continue;
    }

    lukListe();
    html.push(`<p>${renderInlineMarkdown(trimmet)}</p>`);
  }

  lukListe();
  if (iKodeblok) {
    html.push(`<pre><code>${escapeHtml(kodeblok.join("\n"))}</code></pre>`);
  }
  return html.join("\n");
}

function visSvar(markdown) {
  senesteSvar = markdown || "";
  svarfelt.innerHTML = renderMarkdown(senesteSvar);
}

function visResultat(markdown) {
  senesteResultat = markdown || "";
  resultatfelt.innerHTML = renderMarkdown(senesteResultat);
}

function visKilder(kilder) {
  kildeliste.innerHTML = "";
  for (const kilde of kilder) {
    const element = document.createElement("article");
    element.className = "kilde";
    element.dataset.prioritet = String(kilde.prioritet);
    element.innerHTML = `
      <span class="mærke">Prioritet ${kilde.prioritet} · ${kilde.type}</span>
      <h3></h3>
      <p></p>
    `;
    element.querySelector("h3").textContent = kilde.titel;
    element.querySelector("p").textContent = kilde.beskrivelse;
    kildeliste.appendChild(element);
  }
}

function visKonkreteKilder(kilder) {
  kildeliste.innerHTML = "";
  for (const kilde of kilder) {
    const element = document.createElement("article");
    element.className = "kilde";
    element.dataset.prioritet = String(kilde.prioritet);

    const mærke = document.createElement("span");
    mærke.className = "mærke";
    mærke.textContent = `Prioritet ${kilde.prioritet} · ${kilde.omraade}`;

    const titel = document.createElement("h3");
    titel.textContent = kilde.titel;

    const beskrivelse = document.createElement("p");
    beskrivelse.textContent = `Uddrag ${kilde.chunk_nr} · score ${kilde.score}`;

    element.append(mærke, titel, beskrivelse);
    if (kilde.url) {
      element.title = kilde.url;
    }
    kildeliste.appendChild(element);
  }
}

function visUploadedeFiler() {
  uploadListe.innerHTML = "";
  for (const fil of uploadedeFiler) {
    const element = document.createElement("article");
    element.className = "uploadkort";
    if (fil.kraever_ocr) {
      element.classList.add("ocr");
    }

    const titel = document.createElement("strong");
    titel.textContent = fil.filnavn;

    const status = document.createElement("span");
    const tekstLængde = fil.tekst_laengde ? ` · ${fil.tekst_laengde} tegn` : "";
    status.textContent = `${fil.status || "Ingen status"}${tekstLængde}`;

    element.append(titel, status);
    uploadListe.appendChild(element);
  }
}

function filtrerKilder() {
  const søgning = kildesøgning.value.trim().toLowerCase();
  if (!søgning) {
    visKilder(alleKilder);
    return;
  }
  visKilder(
    alleKilder.filter((kilde) =>
      `${kilde.titel} ${kilde.type} ${kilde.beskrivelse} ${(kilde.noegleord || []).join(" ")}`
        .toLowerCase()
        .includes(søgning)
    )
  );
}

async function hentKilder() {
  const svar = await fetch("/api/kilder");
  const data = await svar.json();
  if (data.ok) {
    alleKilder = data.kilder;
    visKilder(alleKilder);
  }
}

async function uploadFiler() {
  if (!filUploadFelt.files.length) {
    return;
  }

  const formData = new FormData();
  for (const fil of filUploadFelt.files) {
    formData.append("filer", fil);
  }

  filUploadFelt.disabled = true;
  sætStatus("Uploader filer");
  try {
    const svar = await fetch("/api/filer/upload", {
      method: "POST",
      body: formData,
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Upload fejlede");
    }
    uploadedeFiler = uploadedeFiler.concat(data.filer || []);
    visUploadedeFiler();
    sætStatus("Filer klar");
  } catch (fejl) {
    uploadListe.textContent = `Uploadfejl: ${fejl.message}`;
    sætStatus("Fejl");
  } finally {
    filUploadFelt.disabled = false;
    filUploadFelt.value = "";
  }
}

async function lavSvar() {
  const henvendelse = henvendelseFelt.value.trim();
  if (!henvendelse) {
    visSvar("Skriv en henvendelse først.");
    visResultat("Der er endnu ikke lavet en analyse.");
    return;
  }

  sendKnap.disabled = true;
  sætStatus("Arbejder");
  visSvar("Udarbejder svarudkast...");
  visResultat("Finder kilder, intent og interne noter...");

  try {
    const svar = await fetch("/api/svar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        henvendelse,
        ekstra_kontekst: ekstraKontekstFelt.value,
        ny_medarbejder: nyMedarbejderFelt.checked,
        svarmodus: svarmodusFelt.value,
        uploadede_filer: uploadedeFiler,
      }),
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Ukendt fejl");
    }
    intentFelt.textContent = data.intent;
    visSvar(data.svarudkast || data.svar);
    visResultat(data.resultatnotat || data.svar);
    sætStatus(data.llm_status);
    if (Array.isArray(data.konkrete_kilder) && data.konkrete_kilder.length > 0) {
      visKonkreteKilder(data.konkrete_kilder);
    } else if (Array.isArray(data.kilder)) {
      visKilder(data.kilder);
    }
  } catch (fejl) {
    visSvar(`Der opstod en fejl:\n${fejl.message}`);
    visResultat("Se fejlbeskeden i svarfeltet.");
    sætStatus("Fejl");
  } finally {
    sendKnap.disabled = false;
  }
}

function rydFelter() {
  henvendelseFelt.value = "";
  ekstraKontekstFelt.value = "";
  nyMedarbejderFelt.checked = false;
  svarmodusFelt.value = "supportfagligt_svar";
  uploadedeFiler = [];
  filUploadFelt.value = "";
  uploadListe.innerHTML = "";
  intentFelt.textContent = "Afventer henvendelse";
  visSvar("Svarudkastet vises her.");
  visResultat("Metadata og interne overvejelser vises her.");
  sætStatus("Klar");
  visKilder(alleKilder);
}

async function kopierSvar() {
  await navigator.clipboard.writeText(senesteSvar);
  sætStatus("Kopieret");
}

sendKnap.addEventListener("click", lavSvar);
rydKnap.addEventListener("click", rydFelter);
kopierKnap.addEventListener("click", kopierSvar);
kildesøgning.addEventListener("input", filtrerKilder);
filUploadFelt.addEventListener("change", uploadFiler);

function hentGisAnalyseFraModul() {
  const gemt = sessionStorage.getItem("gisAnalyseTilSvarbase");
  if (!gemt) {
    return;
  }
  sessionStorage.removeItem("gisAnalyseTilSvarbase");
  try {
    const data = JSON.parse(gemt);
    if (!data || !data.rapport) {
      return;
    }
    svarmodusFelt.value = "teknisk_fejlsoegning";
    if (!henvendelseFelt.value.trim()) {
      henvendelseFelt.value = "Der ønskes hjælp til fejlsøgning af GIS-upload i Plandata.dk.";
    }
    const eksisterende = ekstraKontekstFelt.value.trim();
    ekstraKontekstFelt.value = `${eksisterende ? `${eksisterende}\n\n` : ""}GIS-rapport fra GIS-modulet:\n${data.rapport}`;
    sætStatus("GIS-rapport indsat");
  } catch {
    sætStatus("GIS-import fejlede");
  }
}

hentGisAnalyseFraModul();

hentKilder().catch(() => {
  kildeliste.textContent = "Kilder kunne ikke indlæses.";
});
