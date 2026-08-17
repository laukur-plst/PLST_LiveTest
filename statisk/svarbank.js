const statusfelt = document.querySelector("#svarbankStatus");
const qaIdFelt = document.querySelector("#qaId");
const spoergsmaalFelt = document.querySelector("#spoergsmaal");
const qaSvarFelt = document.querySelector("#qaSvar");
const qaStatusFelt = document.querySelector("#qaStatus");
const qaPrioritetFelt = document.querySelector("#qaPrioritet");
const qaTagsFelt = document.querySelector("#qaTags");
const qaFilUploadFelt = document.querySelector("#qaFilUpload");
const qaUploadListe = document.querySelector("#qaUploadListe");
const gemQaKnap = document.querySelector("#gemQa");
const nyQaKnap = document.querySelector("#nyQa");
const qaFilterFelt = document.querySelector("#qaFilter");
const qaListe = document.querySelector("#qaListe");

let alleSvar = [];
let vedhaeftedeFiler = [];

function sætStatus(tekst) {
  statusfelt.textContent = tekst;
}

function tagsFraTekst(tekst) {
  return tekst
    .split(/[,\n;]/)
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean);
}

function kortTekst(tekst, længde = 180) {
  if (tekst.length <= længde) {
    return tekst;
  }
  return tekst.slice(0, længde).trimEnd() + "...";
}

function rydFormular() {
  qaIdFelt.value = "";
  spoergsmaalFelt.value = "";
  qaSvarFelt.value = "";
  qaStatusFelt.value = "kladde";
  qaPrioritetFelt.value = "1";
  qaTagsFelt.value = "";
  vedhaeftedeFiler = [];
  qaFilUploadFelt.value = "";
  visVedhaeftedeFiler();
  spoergsmaalFelt.focus();
}

function redigerSvar(qa) {
  qaIdFelt.value = qa.qa_id;
  spoergsmaalFelt.value = qa.spoergsmaal;
  qaSvarFelt.value = qa.svar;
  qaStatusFelt.value = qa.status;
  qaPrioritetFelt.value = qa.prioritet;
  qaTagsFelt.value = (qa.tags || []).join(", ");
  vedhaeftedeFiler = qa.vedhaeftede_filer || [];
  qaFilUploadFelt.value = "";
  visVedhaeftedeFiler();
  sætStatus("Redigerer");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function visVedhaeftedeFiler() {
  qaUploadListe.innerHTML = "";
  for (const fil of vedhaeftedeFiler) {
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

    const fjern = document.createElement("button");
    fjern.type = "button";
    fjern.className = "sekundær miniKnap";
    fjern.textContent = "Fjern";
    fjern.addEventListener("click", () => {
      vedhaeftedeFiler = vedhaeftedeFiler.filter((punkt) => punkt !== fil);
      visVedhaeftedeFiler();
    });

    element.append(titel, status, fjern);
    qaUploadListe.appendChild(element);
  }
}

function visSvar() {
  const søgning = qaFilterFelt.value.trim().toLowerCase();
  qaListe.innerHTML = "";

  for (const qa of alleSvar) {
    const samlet = `${qa.spoergsmaal} ${qa.svar} ${qa.status} ${(qa.tags || []).join(" ")}`.toLowerCase();
    if (søgning && !samlet.includes(søgning)) {
      continue;
    }

    const kort = document.createElement("article");
    kort.className = "qaKort";
    kort.dataset.status = qa.status;

    const top = document.createElement("div");
    top.className = "qaTop";

    const titel = document.createElement("h3");
    titel.textContent = qa.spoergsmaal;

    const mærke = document.createElement("span");
    mærke.className = "mærke";
    mærke.textContent = `${qa.status} · prioritet ${qa.prioritet}`;

    top.append(titel, mærke);

    const svar = document.createElement("p");
    svar.textContent = kortTekst(qa.svar);

    const tags = document.createElement("div");
    tags.className = "tagliste";
    for (const tag of qa.tags || []) {
      const chip = document.createElement("span");
      chip.className = "tagchip";
      chip.textContent = tag;
      tags.appendChild(chip);
    }

    if ((qa.vedhaeftede_filer || []).length) {
      const bilag = document.createElement("p");
      bilag.className = "bilagtekst";
      bilag.textContent = `${qa.vedhaeftede_filer.length} bilag`;
      tags.appendChild(bilag);
    }

    const handlinger = document.createElement("div");
    handlinger.className = "handlinger kompakt";
    const rediger = document.createElement("button");
    rediger.type = "button";
    rediger.className = "sekundær";
    rediger.textContent = "Redigér";
    rediger.addEventListener("click", () => redigerSvar(qa));
    handlinger.appendChild(rediger);

    kort.append(top, svar, tags, handlinger);
    qaListe.appendChild(kort);
  }
}

async function hentSvar() {
  const svar = await fetch("/api/svarbank");
  const data = await svar.json();
  if (!data.ok) {
    throw new Error("Svarbank kunne ikke hentes.");
  }
  alleSvar = data.svar || [];
  visSvar();
  sætStatus(`${alleSvar.length} svar`);
}

async function gemSvar() {
  gemQaKnap.disabled = true;
  sætStatus("Gemmer");
  try {
    const svar = await fetch("/api/svarbank/gem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        qa_id: qaIdFelt.value || undefined,
        spoergsmaal: spoergsmaalFelt.value,
        svar: qaSvarFelt.value,
        status: qaStatusFelt.value,
        prioritet: Number(qaPrioritetFelt.value || 1),
        tags: tagsFraTekst(qaTagsFelt.value),
        vedhaeftede_filer: vedhaeftedeFiler,
      }),
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Svaret kunne ikke gemmes.");
    }
    await hentSvar();
    qaIdFelt.value = data.qa_id;
    sætStatus(data.status === "godkendt" ? `Indekseret: ${data.chunks} tekststykker` : "Gemt");
  } catch (fejl) {
    sætStatus("Fejl");
    alert(fejl.message);
  } finally {
    gemQaKnap.disabled = false;
  }
}

async function uploadQaFiler() {
  if (!qaFilUploadFelt.files.length) {
    return;
  }

  const formData = new FormData();
  for (const fil of qaFilUploadFelt.files) {
    formData.append("filer", fil);
  }

  qaFilUploadFelt.disabled = true;
  sætStatus("Uploader bilag");
  try {
    const svar = await fetch("/api/filer/upload", {
      method: "POST",
      body: formData,
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Upload fejlede");
    }
    vedhaeftedeFiler = vedhaeftedeFiler.concat(data.filer || []);
    visVedhaeftedeFiler();
    sætStatus("Bilag klar");
  } catch (fejl) {
    sætStatus("Fejl");
    alert(fejl.message);
  } finally {
    qaFilUploadFelt.disabled = false;
    qaFilUploadFelt.value = "";
  }
}

gemQaKnap.addEventListener("click", gemSvar);
nyQaKnap.addEventListener("click", rydFormular);
qaFilterFelt.addEventListener("input", visSvar);
qaFilUploadFelt.addEventListener("change", uploadQaFiler);

hentSvar().catch((fejl) => sætStatus(fejl.message));
