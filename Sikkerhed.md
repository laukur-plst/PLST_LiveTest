# Sikkerhedssetup for AI-kodeassistent — model og Codex-oversættelse

**Version 1.0 · 2026-06-19 · Forfatter: Peter Kure (PLST) · Til: Frederik**

Sådan har jeg begrænset Claude Codes adgang på min Statens IT-maskine — og hvordan
principperne oversættes til Codex, så du kan bygge din egen indhegning. Det er ikke en
1:1-opskrift (vi bruger forskellige værktøjer), men idéen bag er værktøjsuafhængig.

---

## Grundidé: hård vs. blød

Den vigtigste skelnen i hele setuppet:

- **Hård regel** = kodet ind i værktøjet, kan ikke omgås — heller ikke hvis du ved et
  uheld godkender det.
- **Blød regel** = en instruktion modellen *vælger* at følge, fordi den læser den.

Begge har en plads. Pointen er at *vide* hvilken du har, så du ikke tror noget er låst,
når det reelt kun er aftalt.

**Trusselsmodel:** uagtsomhed, ikke ondskab. Jeg beskytter mod at assistenten kommer til
at læse en nøgle, skrive på netværksdrevet eller røre persondata — ikke mod en ondsindet
model der prøver at bryde ud. Det afgør hvor jeg bruger hårde låse (på det der gør reel
skade) og hvor jeg nøjes med bløde regler (hvor daglig friktion ville koste mere end risikoen).

---

## Tre lag

| Lag | Fil | Hvem læser det | Håndhævelse |
|---|---|---|---|
| 1 · Politik | `AGENTS.md` | Modellen + mennesker | **Blød** (model adlyder) |
| 2 · Manifest | `adgangskontrol.md` | Mennesker (dokumentation) | Ingen — beskriver bare |
| 3 · Teknisk | `.claude/settings.json` | Selve værktøjet (harness) | **Hård** (kan ikke omgås) |

Samme regel kan leve i flere lag. "Læs aldrig `.env`" står både som politik i `AGENTS.md`
(så modellen *ved* det) **og** som en hård `deny` i `settings.json` (så den ikke *kan*,
hvis den glemmer det).

Lag 2 (manifestet) findes for ærlighedens skyld: hver regel er mærket hård / delvist / blød,
så ingen tror der er en lås hvor der kun er en hensigt.

---

## Lag 3 — den hårde kerne (min faktiske settings.json)

`allow` giver fuld adgang til projektmappen. `deny` spærrer hårdt for nøgler, persondata,
netværksdrev og hele hjemmemappen undtagen projektet. **En `deny` slår altid en `allow`.**
`**` betyder "alt herunder"; `~/` er hjemmemappen (portabelt); drevbogstaver er absolutte.

```jsonc
{
  "permissions": {
    "allow": [
      "Read(C:\\Users\\B294260\\Python\\**)",
      "Write(C:\\Users\\B294260\\Python\\**)",
      "Edit(C:\\Users\\B294260\\Python\\**)"
    ],
    "deny": [
      "Read(**/.env)",
      "Read(C:\\Users\\B294260\\Python\\_foelsommeoplysninger\\**)",
      "Write(C:\\Users\\B294260\\Python\\_foelsommeoplysninger\\**)",
      "Edit(C:\\Users\\B294260\\Python\\_foelsommeoplysninger\\**)",
      "Read(O:\\**)",  "Write(O:\\**)",  "Edit(O:\\**)",
      "Read(H:\\**)",  "Write(H:\\**)",  "Edit(H:\\**)",
      "Read(F:\\**)",  "Write(F:\\**)",  "Edit(F:\\**)",
      "Read(~/Desktop/**)",   "Write(~/Desktop/**)",   "Edit(~/Desktop/**)",
      "Read(~/Documents/**)", "Write(~/Documents/**)", "Edit(~/Documents/**)",
      "Read(~/OneDrive/**)",  "Write(~/OneDrive/**)",  "Edit(~/OneDrive/**)"
      // ...samme tre-linjers mønster for hver øvrige mappe i hjemmemappen:
      //    Downloads, AppData, Pictures, Music, Videos, GIS-mapper,
      //    "Plan- og Landdistriktsstyrelsen", .vscode, .copilot m.fl.
    ]
  }
}
```

### Hvorfor bygget sådan

- **`deny` vinder over `allow`** → en `deny` er en reel, uomgåelig lås. Men det betyder
  også at man *ikke* kan skrive "spær hele `C:` og tillad så kun min mappe": den brede
  `deny C:\**` ville æde din `allow`.
- **Det du vil låse hårdt** (nøgler, persondata, drev, navngivne hjemmemapper) →
  eksplicitte `deny`-regler.
- **"Alt andet på C:"** kan ikke denies samtidig med din allow → fanges i stedet af
  værktøjets indbyggede godkendelses-prompt (blødere, men dækker resten).
- **Sletning og `pip install` er bevidst holdt bløde** — kunne gøres hårde, men prisen i
  daglig friktion er for høj mod en lav risiko. Et valg, ikke en forglemmelse.

---

## Regel-klassificering

| Regel | Type | Metode |
|---|---|---|
| Læs aldrig `.env` | 🔒 Hård | `deny Read(**/.env)` |
| Følsom-persondata-mappe spærret | 🔒 Hård | `deny R/W/E(..._foelsommeoplysninger\**)` |
| Netværksdrev O: (læs/skriv via værktøj) | 🔒 Hård | `deny R/W/E(O:\**)` |
| H:/F: + hjemmemappe undtagen projekt | 🔒 Hård | `deny` pr. drev/mappe |
| Kun adgang til projektmappen | ⚠ Delvist | `allow` + prompt for resten |
| Spørg før redigering af filer | 📋 Blød | Interaktionsregel — kan ikke kodes |
| Slet aldrig uden anmodning | 📋 Blød | Bevidst ikke gjort hård |
| Advar før irreversible handlinger | 📋 Blød | Adfærdsregel |
| Ingen `pip install` uden anmodning | 📋 Blød | Bevidst ikke gjort hård |

---

## Oversat til Codex — sådan bygger du din egen indhegning

> **Forbehold:** Jeg kender Claude Codes `settings.json` præcist (det er min faktiske fil).
> Codex' config-skema udvikler sig derimod løbende — **nøglerne herunder er retningsgivende
> og skal verificeres mod Codex' aktuelle dokumentation** før du forlader dig på dem.

### Lag 1 — politik: `AGENTS.md`

Codex læser `AGENTS.md` (i projektroden og/eller `~/.codex/`). Læg dine klartekst-regler her — ren 1:1-oversættelse af lag 1. Stadig blødt.

### Lag 3 — teknisk: `~/.codex/config.toml`

Codex' hårde lag er en kombination af en **sandkasse-tilstand** og en **godkendelses-politik**.
Bygget omvendt af min allow/deny: i stedet for at remse forbudte stier op, sætter du én
sandkasse der per default kun tillader skrivning i arbejdsmappen og slår netadgang fra.

```toml
# ~/.codex/config.toml  — retningsgivende, verificér nøglerne
approval_policy = "on-request"     # spørg før risikable handlinger
sandbox_mode    = "workspace-write" # kun arbejdsmappen er skrivbar

[sandbox_workspace_write]
network_access = false                      # ingen netadgang (svarer til min standard)
writable_roots = ["C:\\sti\\til\\dit\\projekt"]  # din "allow"-mappe
```

| Hos mig (Claude Code) | Codex-pendant | Note |
|---|---|---|
| `allow(...Python\**)` | `writable_roots` + `workspace-write` | Den ene mappe der må skrives i |
| `deny` på alt udenfor | Implicit i sandkassen | Codex spærrer alt uden for sandkassen — du remser ikke forbud op |
| Ingen netadgang | `network_access = false` | Slået fra som standard i workspace-write |
| Godkendelses-prompt for resten | `approval_policy` | `on-request` ≈ min prompt; `never` = ingen prompt (mere risikabelt) |

**Vigtig forskel:** Codex har ikke et lige så finkornet "deny denne ene undermappe inde i en
ellers tilladt mappe"-system som mine `.env`- og persondata-spærrer. Vil du sikre følsomme
undermapper, er den robuste vej at **holde dem helt uden for arbejdsmappen**, så de aldrig er
i sandkassen til at begynde med.

---

## Den vigtigste advarsel: native Windows-fælden

Codex' *rigtige* sandkasse bruger styresystemets egne isolations-mekanismer (Seatbelt på
macOS, Landlock/seccomp på Linux). **Native Windows har ikke en tilsvarende** — så på en
Statens IT Windows-maskine hviler beskyttelsen i højere grad på *godkendelses-politikken*
(du bliver spurgt) end på en hård spærre der fysisk forhindrer adgang.

Det er præcis samme mur jeg selv ramte: en ren "spær alt undtagen min mappe"-model er ikke
mulig på native Windows (`deny` slår `allow`, så du kan ikke whitelist'e én mappe ud af en
ellers spærret disk). Den ægte løsning begge steder:

- **WSL2** (Linux-sandkasse under Windows) — hvis dit arbejde rører noget følsomt, og du vil
  have den hårde lås.
- **Ellers:** hold følsomme data fysisk uden for arbejdsmappen, kør
  `sandbox_mode = "workspace-write"` med `network_access = false`, og vær bevidst om at
  `approval_policy` er din egentlige beskyttelse på native Windows — vælg den **ikke** `never`.

---

## Ændringslog
- v1.0 (2026-06-19) – oprettet som markdown-pendant til `sikkerhedssetup_til_frederik.html`;
  udvikler-orienteret så Frederik kan bygge sin egen indhegning i Codex.
