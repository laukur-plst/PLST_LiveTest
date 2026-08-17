const statusfelt = document.querySelector("#kildeStatus");
const statuskort = document.querySelector("#statuskort");
const kildeTabel = document.querySelector("#kildeTabel");
const filterFelt = document.querySelector("#filter");
const opdaterPlandataKnap = document.querySelector("#opdaterPlandata");
const genindlæsKnap = document.querySelector("#genindlæs");
const fraKildeFelt = document.querySelector("#fraKilde");
const tilKildeFelt = document.querySelector("#tilKilde");
const relationTypeFelt = document.querySelector("#relationType");
const relationNoteFelt = document.querySelector("#relationNote");
const gemRelationKnap = document.querySelector("#gemRelation");
const relationListe = document.querySelector("#relationListe");

let kilder = [];
let relationer = [];

function sætStatus(tekst) {
  statusfelt.textContent = tekst;
}

function tagsFraTekst(tekst) {
  return tekst
    .split(/[,\n;]/)
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean);
}

function visStatus(status) {
  const områdeTekst = (status.omraader || [])
    .map((område) => `
      <div class="statlinje">
        <span>${område.kilde_type} · ${område.omraade}</span>
        <strong>${område.sider}</strong>
      </div>
    `)
    .join("");

  statuskort.innerHTML = `
    <div class="statlinje"><span>Sider</span><strong>${status.sider}</strong></div>
    <div class="statlinje"><span>Tekststykker</span><strong>${status.chunks}</strong></div>
    <div class="statlinje"><span>Tags</span><strong>${status.tags || 0}</strong></div>
    <div class="statlinje"><span>Svarbank</span><strong>${status.qa_svar || 0}</strong></div>
    <div class="statlinje"><span>Relationer</span><strong>${status.relationer || 0}</strong></div>
    ${områdeTekst}
  `;
}

function udfyldKildeSelects() {
  const options = kilder
    .map((kilde) => `<option value="${kilde.side_id}">${kilde.prioritet} · ${kilde.kilde_type} · ${kilde.titel}</option>`)
    .join("");
  fraKildeFelt.innerHTML = options;
  tilKildeFelt.innerHTML = options;
}

async function gemKildeMetadata(kilde, række) {
  const prioritet = række.querySelector(".prioritetInput").value;
  const tags = tagsFraTekst(række.querySelector(".tagsInput").value);
  sætStatus("Gemmer");
  const svar = await fetch("/api/kilder/metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ side_id: kilde.side_id, prioritet, tags }),
  });
  const data = await svar.json();
  if (!data.ok) {
    throw new Error(data.fejl || "Metadata kunne ikke gemmes.");
  }
  await hentStatus();
  sætStatus("Gemt");
}

function visKilder() {
  const søgning = filterFelt.value.trim().toLowerCase();
  kildeTabel.innerHTML = "";

  for (const kilde of kilder) {
    const samlet = `${kilde.kilde_type} ${kilde.omraade} ${kilde.titel} ${(kilde.tags || []).join(" ")}`.toLowerCase();
    if (søgning && !samlet.includes(søgning)) {
      continue;
    }

    const række = document.createElement("tr");
    række.innerHTML = `
      <td><input class="prioritetInput lilleInput" type="number" min="0" max="9"></td>
      <td></td>
      <td></td>
      <td><a target="_blank" rel="noreferrer"></a></td>
      <td><input class="tagsInput" type="text" placeholder="tags"></td>
      <td><button class="sekundær gemMetadata" type="button">Gem</button></td>
    `;
    række.querySelector(".prioritetInput").value = kilde.prioritet;
    række.children[1].textContent = kilde.kilde_type;
    række.children[2].textContent = kilde.omraade;
    række.querySelector(".tagsInput").value = (kilde.tags || []).join(", ");
    const link = række.querySelector("a");
    link.href = kilde.url && !kilde.url.startsWith("svarbank:") ? kilde.url : "/svarbank.html";
    link.textContent = kilde.titel;
    række.querySelector(".gemMetadata").addEventListener("click", () => {
      gemKildeMetadata(kilde, række).catch((fejl) => {
        sætStatus("Fejl");
        alert(fejl.message);
      });
    });
    kildeTabel.appendChild(række);
  }
}

function visRelationer() {
  relationListe.innerHTML = "";
  for (const relation of relationer.slice(0, 12)) {
    const element = document.createElement("article");
    element.className = "relationkort";
    element.innerHTML = `
      <strong></strong>
      <span></span>
    `;
    element.querySelector("strong").textContent = `${relation.fra_titel || relation.fra_side_id} ${relation.relation_type} ${relation.til_titel || relation.til_side_id}`;
    element.querySelector("span").textContent = relation.note || "Ingen note";
    relationListe.appendChild(element);
  }
}

async function hentStatus() {
  const statusSvar = await fetch("/api/vidensbase/status");
  const siderSvar = await fetch("/api/vidensbase/sider");
  const relationSvar = await fetch("/api/kilder/relationer");
  const statusData = await statusSvar.json();
  const siderData = await siderSvar.json();
  const relationData = await relationSvar.json();
  if (!statusData.ok || !siderData.ok || !relationData.ok) {
    throw new Error("Kildestatus kunne ikke hentes.");
  }
  kilder = siderData.sider;
  relationer = relationData.relationer || [];
  visStatus(statusData.status);
  udfyldKildeSelects();
  visKilder();
  visRelationer();
}

async function opdaterPlandata() {
  opdaterPlandataKnap.disabled = true;
  sætStatus("Opdaterer");
  try {
    const svar = await fetch("/api/kilder/opdater-plandata", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Opdateringen fejlede.");
    }
    visStatus(data.status);
    await hentStatus();
    sætStatus(`Plandata.dk: ${data.importeret}/${data.kilder}`);
  } catch (fejl) {
    sætStatus("Fejl");
    alert(fejl.message);
  } finally {
    opdaterPlandataKnap.disabled = false;
  }
}

async function gemRelation() {
  gemRelationKnap.disabled = true;
  sætStatus("Gemmer relation");
  try {
    const svar = await fetch("/api/kilder/relation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fra_side_id: fraKildeFelt.value,
        til_side_id: tilKildeFelt.value,
        relation_type: relationTypeFelt.value,
        note: relationNoteFelt.value,
      }),
    });
    const data = await svar.json();
    if (!data.ok) {
      throw new Error(data.fejl || "Relationen kunne ikke gemmes.");
    }
    relationNoteFelt.value = "";
    await hentStatus();
    sætStatus("Relation gemt");
  } catch (fejl) {
    sætStatus("Fejl");
    alert(fejl.message);
  } finally {
    gemRelationKnap.disabled = false;
  }
}

filterFelt.addEventListener("input", visKilder);
genindlæsKnap.addEventListener("click", () => hentStatus().catch((fejl) => sætStatus(fejl.message)));
opdaterPlandataKnap.addEventListener("click", opdaterPlandata);
gemRelationKnap.addEventListener("click", gemRelation);

hentStatus().catch((fejl) => sætStatus(fejl.message));
