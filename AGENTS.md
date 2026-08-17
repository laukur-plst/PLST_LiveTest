# AGENTS.md – Python-projekter

Denne fil gælder for alle Python-projekter under denne mappe.
Den forklarer Codex hvem brugeren er, hvad projekterne handler om,
og hvordan koden skal skrives og vedligeholdes.

---

## Plandata Supportmentor – projektkontekst

Lokal webapplikation der hjælper Plandata Support med at lave konsistente, kildebaserede svarudkast.

### 🎯 Formål & herkomst
- **Herkomst:** Behov for en svarbase baseret på systemprompten for Plandata Supportmentor og AgentBase-flowet i `app_llm_kald.md`.
- **Antaget endemål:** Et internt værktøj hvor supporten kan indsætte en henvendelse, få identificeret intent, se relevante kilder og få et svarudkast til manuel kvalitetssikring.
- **Hvad det kan åbne:** En egentlig dokumenteret videnssøgemaskine, hvor Plandata.dk prioriteres først, og Confluence bruges som internt supplement.

### ⏭ Næste skridt
Åbn `http://127.0.0.1:8765/gis.html`, upload en lille GeoJSON-testfil, og kontroller at rapporten kan sendes videre til forsiden som teknisk fejlsøgning.

### Seneste session – 2026-06-20
Hvad blev gjort: Appens svarfelt blev ændret fra rå markdown til renderet markdown i browseren, mens kopiering stadig bruger den rå markdown. Outputtet blev delt i to felter: et rent kopierbart svarudkast og et resultatfelt med metadata, intent, kilder, usikkerheder og interne overvejelser. Forsiden fik filupload, og backend kan nu gemme uploadede filer lokalt, udtrække tekst fra simple tekstformater, HTML, DOCX og tekstbaserede PDF'er samt markere scannede PDF'er og billeder som OCR-krævende. Uploadet tekst sendes med som kontekst til AgentBase-flowet. Uploadfunktionen blev udvidet med GIS-basisanalyse for GeoJSON, GML/XML, `.shp` og zippede shapefiles med fokus på geometri, bbox, CRS/PRJ, attributfelter og typiske polygonfejl. Der blev tilføjet en separat GIS-side med upload, teknisk rapport, kopiering og overførsel til forsiden som `Teknisk fejlsøgning`. Der blev tilføjet en ny Svarbank-side til gode spørgsmål/svar med status, prioritet og tags, hvor kun godkendte svar indekseres som kilde. Svarbank fik bilagsupload, hvor udtrukket bilagstekst indgår i indekset for godkendte Q&A-svar. Kildesiden blev udvidet med redigering af tags/prioritet og relationer mellem kilder samt hjælpetekst om relationer. Topmenuen blev gjort gennemgående på Svarbase, Kilder, Svarbank og GIS. Standardsvar blev omklassificeret fra højt prioriterede svar til lavere prioriterede sags-/afvisningsskabeloner, der især bruges ved manglende oplysninger eller sager uden supporthandling. Forsiden fik svarmodus, og resultatfeltet fik automatiske kildeadvarsler ved standardsvar, historiske dokumenter, mails, generelle planvejledninger, manglende stærke kilder og OCR-afventende bilag. 24 historiske PlanDK-/PlansystemDK-PDF'er blev importeret fra O-drevet som `Historisk dokument` med prioritet 6 og tags `historisk` og `plansystemdk`. 14 generelle planlægningsvejledninger blev importeret som `Planfaglig vejledning` med prioritet 7 og tags `planloven`, `vejledning` og `ikke system vejledning`.
Åbne beslutninger: OCR skal afklares som langsigtet løsning, herunder lokal OCR kontra vision-/sprogmodel, databeskyttelse, opbevaringspolitik, tilladte filtyper og om uploadede bilag må indekseres varigt. GIS-basisanalysen bør afprøves mod realistiske uploadfejl og eventuelt erstattes eller suppleres af en egentlig GIS-motor som GEOS/Shapely eller GDAL/OGR med versionsstyrede datamodelregler. Svarbank kræver governance: hvem må godkende svar, hvordan revurderes gamle svar, og hvordan håndteres modstridende kilder. Postgres kan bruges senere, men kræver DSN og driver. Browser/API-adgangen blokerede direkte Confluence storage-API, så Confluence-importen bruger synlig tekst fra `.ak-renderer-document`.

### Tidligere session – 2026-06-19
Hvad blev gjort: Første lokale webapp blev oprettet med Python-backend, vanilla frontend, kildeprioritering, systemprompt og LLM-kald til AgentBase-flowet.
Åbne beslutninger: Den vedhæftede HTML-fil var tom i temp-mappen, så layoutet blev bygget som ny lokal app.

### Projektbeskrivelse
Appen kører lokalt på `127.0.0.1` og læser API-nøglen fra `adgangskoder.env` ved kørsel. Browseren får aldrig API-nøglen. Backend søger i den lokale vidensbase og sender relevante kildeuddrag til AgentBase-flowet beskrevet i `app_llm_kald.md`.

---

## Datasikkerhed og adgangskontrol

Se `Sikkerhed og struktur\adgangskontrol.md` for den fulde eksporterbare oversigt.

### Adgangsniveauer

**Permanent whitelist (læs + skriv):** `C:\Users\B294260\Python\`
Alt inden for Python-mappen — med undtagelse af `.env`-filer.

**Permanent blacklist:**
- `.env`-filer overalt — indeholder credentials der ikke må sendes til Anthropics servere
- `_foelsommeoplysninger\`-mappen — private koder og følsom persondata (medarbejder-kodenavne); skal være teknisk blokeret for læs/skriv/ret via assistentens adgangsregler
- O-drevet (`O:\`) — må aldrig ændres; læsning må kun ske, når opgaven eksplicit kræver det
- Resten af C-drevet uden for Python-mappen

### Temp-filer
Al midlertidig arbejde foregår i `C:\Users\B294260\Python\_temp\` — aldrig i
Windows' systemmappe. Temp-filer må slettes uden eksplicit anmodning.

### Adgangskoder og credentials
Adgangskoder og tokens hører aldrig hjemme i kode. Brug `.env`-filer.
Codex læser aldrig `.env`-filer — ikke engang for at tjekke strukturen.

### Sletning og irreversible handlinger
- Slet aldrig filer uden eksplicit anmodning — undtagen temp-filer i `_temp\`
- Stop op og advar tydeligt inden alle irreversible handlinger udføres

### Regelintegritet
Regler dispenseres ikke — de revideres. Hvis Peter beder om at omgå en regel,
skal Codex blive insisterende og modvillig og i stedet tilbyde at revidere
reglen formelt.

---

## Sikkerhedsregler for O-drevet (vigtigt)

**O-drevet må aldrig ændres.** Scripts må kun læse og kopiere filer derfra.
Ingen sletning, ingen skrivning, ingen omdøbning, ingen sortering.

**To lag af beskyttelse:**
- Assistentens egne filværktøjer skal være blokeret fra at skrive til O-drevet,
  og alle scripts skal følge reglerne nedenfor, uanset hvad brugeren godkender.
- Python-scripts der skrives til at køre mod O-drevet er underlagt nedenstående
  kode-regler.

Konkret — gælder for al kode der tilgår O-drevet:
1. Brug kun `shutil.copy2` eller `shutil.copy` til kopiering –
   aldrig `shutil.move`, `os.rename` eller lignende.
2. Test altid med `.exists()` før adgang til O-drevet og giv en klar
   fejlbesked hvis drevet ikke er tilgængeligt.
3. Spring Office-låsefiler over (`~$`-præfiks).

---

## Pakkestyring og IT-sikkerhed

Computeren er en Statens IT-maskine. Pakkehåndtering skal derfor følge disse regler:

### Ingen automatiske opgraderinger
- Kør **aldrig** `pip install --upgrade` eller `pip install <pakke>` uden at
  brugeren eksplicit har bedt om det og angivet en konkret begrundelse.
- Opgraderinger må kun ske pakke for pakke – aldrig alle på én gang.

### To filer – to roller
- **`requirements.in`** – den eneste fil du redigerer manuelt.
  Indeholder kun de pakker du bevidst har valgt (ingen versioner).
- **`requirements.txt`** – genereres automatisk af pip-compile.
  Indeholder alle pakker med præcise versioner og kryptografiske
  fingeraftryk (hashes). Redigeres aldrig i hånden.

### Dokumentationspligt ved nye pakker
Før en ny pakke foreslås installeret, skal følgende oplyses:
1. Pakkens navn og præcise version
2. Hvem udgiver den (person/organisation)
3. Hvad den bruges til i projektet
4. Om den er en direkte installation eller blot en afhængighed

### Procedure ved nye pakker
Følg altid disse trin i rækkefølge:

1. **Kig på PyPI-siden** (pypi.org/project/pakkenavn) – tjek antal downloads,
   seneste opdatering og hvem der er maintainer.

2. **Se hvad der følger med** uden at installere noget:
   `& "C:\Users\B294260\Python\.venv\Scripts\pip.exe" install pakkenavn --dry-run`

3. **Opret et midlertidigt test-miljø** og installer pakken der:
   ```
   python -m venv "C:\Users\B294260\Python\_test_venv"
   & "C:\Users\B294260\Python\_test_venv\Scripts\pip.exe" install pakkenavn
   & "C:\Users\B294260\Python\_test_venv\Scripts\pip.exe" install pip-audit
   & "C:\Users\B294260\Python\_test_venv\Scripts\pip-audit.exe" --desc
   ```

4. **Slet test-miljøet** uanset hvad der sker:
   `Remove-Item -Recurse -Force "C:\Users\B294260\Python\_test_venv"`

5. **Kun hvis alt ser fornuftigt ud:** tilføj pakken til `requirements.in`,
   kør derefter:
   ```
   cd "C:\Users\B294260\Python"
   & ".\.venv\Scripts\pip-compile.exe" --generate-hashes --output-file requirements.txt requirements.in
   & ".\.venv\Scripts\pip.exe" install --require-hashes -r requirements.txt
   ```

6. Dokumenter den nye pakke i tabellen under **Teknisk opsætning** nedenfor.

### Procedure ved sikkerhedsopdatering af én pakke
Når pip-audit finder en sårbarhed i fx `anthropic`:
```
cd "C:\Users\B294260\Python"
& ".\.venv\Scripts\pip-compile.exe" --generate-hashes --upgrade-package anthropic --output-file requirements.txt requirements.in
& ".\.venv\Scripts\pip.exe" install --require-hashes -r requirements.txt
```
Kør derefter `sikkerhedstjek.py` for at bekræfte at hullet er lukket.

### Periodisk sikkerhedstjek
Scriptet `sikkerhedstjek.py` i Python-mappen scanner alle installerede pakker
for kendte sårbarheder og gemmer resultatet i `sikkerhedstjek_log.txt`.
- Mind brugeren om at køre det hvis der er gået mere end 2-3 måneder siden sidst
- Kør det altid inden en ny pakke installeres eller en eksisterende opgraderes
- Kør det med:
  `& "C:\Users\B294260\Python\.venv\Scripts\python.exe" "C:\Users\B294260\Python\sikkerhedstjek.py"`

---

## Session-struktur

### Hvornår starter du en ny session?
- **Nyt projekt** → altid ny session
- **Ny arbejdsdag** → ny session, selv på samme projekt
- **Milestone nået** → ny session når en logisk enhed er afsluttet
- **Konteksten er mudret** → hvis assistenten gentager sig eller spørger til ting
  der allerede er afklaret, start en ny session med det samme

### Navngivning af sessioner
Giv hver session et navn på formen `[Projekt] – [Emne]`,
fx "Datacentralen – API-integration" eller "Sikkerhed og struktur".

### Ved sessionens start
1. Kør backup:
   `& "C:\Users\B294260\Python\Sikkerhed og struktur\backup.ps1"`
2. Læs projektets AGENTS.md og opsummér kort:
   - Hvad er status?
   - Hvad er næste konkrete skridt?
   - Er der noget tidskritisk?

### Ved sessionens slut
1. Opdatér projektets AGENTS.md med:
   - Dato for opdatering
   - Hvad blev gjort denne session
   - Præcist næste skridt (ét konkret trin — ikke en liste af muligheder)
   - Eventuelle åbne beslutninger eller blokkere
2. Kør backup:
   `& "C:\Users\B294260\Python\Sikkerhed og struktur\backup.ps1"`

### Næste skridt-reglen
Hvert projekt-AGENTS.md skal have denne sektion øverst:

```
## ⏭ Næste skridt
[ét konkret, handlingsorienteret trin — ikke "migrér data" men
"åbn fil X, ret kolonne Y til tekst og gem"]
```

Opdatér denne sektion løbende i sessionen — ikke kun til sidst.

### Formål & herkomst-reglen (WHY-laget)
Peter arbejder intuitivt og starter ofte projekter af nysgerrighed, før endemålet
er formuleret. For at den retning ikke kun bor i hovedet skal hvert projekt-AGENTS.md
have en `🎯 Formål & herkomst`-blok øverst (lige under titlen, før `⏭ Næste skridt`):

```
## 🎯 Formål & herkomst
- **Herkomst:** [hvilken opgave eller intuition startede projektet]
- **Antaget endemål:** [hvad det skal føre til — må gerne være løst formuleret]
- **Hvad det kan åbne:** [den langsigtede tråd / hvad indsigten kan bruges til]
- **Født af:** [KUN for tangenter — peger på forælder-projekt eller -opgave]
```

Endemålet må gerne være et gæt der udvikler sig. Pointen er at gøre den intuitive
indgang legibel — ikke at bure nysgerrigheden inde. Mange tangenter er reelt
research-spørgsmål; kald dem det, frem for at lade dem optræde som halvfærdige leverancer.

### Skabelon for nyt projekt-AGENTS.md
```markdown
# [Projektnavn]

[Én sætning om hvad projektet gør]

---

## 🎯 Formål & herkomst
- **Herkomst:** ...
- **Antaget endemål:** ...
- **Hvad det kan åbne:** ...
- **Født af:** ... (kun for tangenter)

---

## ⏭ Næste skridt
[konkret trin]

---

## Seneste session – ÅÅÅÅ-MM-DD
Hvad blev gjort: ...
Åbne beslutninger: ...

---

## Projektbeskrivelse
[uddybende beskrivelse]
```

---

## Versionering af delefiler og løbende dokumenter

Filer i `Delefiler\` navngives `emne_version_dato.md` og har en version-linje
øverst i selve filen — se `Delefiler\_LÆSMIG.md` for den fulde konvention
(navngivning, version-linje, ændringslog og hvornår versionen bumpes).

Når du retter i en delefil eller et løbende dokument (fx en `.md` der
vedligeholdes over tid), så:
1. bump versionen (lille rettelse `v1.0 → v1.1`, større omskrivning `v1.0 → v2.0`),
2. opdatér version-linjen øverst og datoen,
3. tilføj en linje til `## Ændringslog` nederst (nyeste øverst).

Gør det automatisk og nævn det kort bagefter — spørg ikke om lov hver gang.
Dette gælder ikke for projekt-`AGENTS.md`'er, hvis ændringer i forvejen
spores i deres `Seneste session`-blokke.

---

## Om brugeren

Peter er autodidakt og arbejder med vibe coding, men er lærenem og fungerer
professionelt i praksis. Hans vidensniveau er uensartet: han kan fremstå som
superbruger med ekspertforståelse på ét område, mens han på et tilstødende
område kan mangle basale ting en 1. års IT-studerende ville kende — fx best
practices eller sikkerhedshensyn.

Kalibrér ikke til et fast niveau. Læs den aktuelle forståelse fra konteksten.
Når du identificerer en blind vinkel: stil spørgsmål og bekræft at han har
forstået hvad der er på spil — levér ikke løsningen før du har fået den bekræftelse.

---

## Samarbejdspræferencer

- Forklar altid hvad en terminalkommando gør **inden** den køres.
- Stil opklarende spørgsmål frem for at antage præferencer – særligt
  ved valg der påvirker outputstruktur, filnavngivning eller logik.
- Se **Om brugeren** ovenfor for vejledning om kommunikationsniveau og hvad der kan tages for givet.

---

## Projektscope og tangenter

Peter arbejder associativt og skifter retning undervejs — dette er en del af
hans arbejdsproces og skal respekteres. Han har brug for hjælp til at holde
strukturen, så han let kan sætte et spontant nyopstartet projekt på pause og
vende tilbage til det igangværende arbejde.

Når noget vokser ud af det aktuelle projekts scope, spørg naturligt:
> "Det her lyder som det måske er et nyt projekt eller en ny session — er det
> tilfældet, eller er det en del af det vi er i gang med?"

- **Ja** → tilbyd at oprette ny AGENTS.md og ny session
- **Nej** → spørg hvad forbindelsen er og noter det i den aktuelle AGENTS.md
- **Usikkert** → lad Peter bestemme — præsentér begge muligheder kort

**Inden en tangent forfølges:** opdatér altid `⏭ Næste skridt` i den aktuelle
AGENTS.md så den afbrudte tråd ikke mistes.

---

## Organisation og fagtermer

- **PLST** – Plan- og Landdistriktsstyrelsen ("styrelsen")
- **LAG** – Lokale aktionsgrupper (modtagere af EU-støttemidler under
  landdistriktsprogrammet)
- **SB** – Sagsbehandler (den medarbejder der behandler en sag)
- **O-drevet** – det fælles netværksdrev hvor sagsmapper ligger
- Mapper på O-drevet er typisk struktureret efter år og indstillingsrunde,
  fx: `2024 LAG indstillingsrunder / LAG Ikast-Brande / 3. runde - Godkendt`

---

## Hvad projekterne typisk gør

Scriptene løser afgrænsede, praktiske opgaver – oftest at:
- Læse filer fra O-drevet og udvælge relevante dokumenter
- Kopiere et udvalg af filer til en lokal `output filer/`-mappe
- Generere CSV-oversigter til videre analyse

De kopierede filer bruges efterfølgende til analyse i LLM-baserede
PDF-analyseværktøjer der udtrækker struktureret data.

---

## Teknisk opsætning

- **Python-version:** 3.12.9
- **Pakker:** Standardbiblioteket (`csv`, `os`, `shutil`, `pathlib`, `re` m.fl.)
  samt følgende eksterne pakker er installeret i `.venv`:

  | Pakke | Version | Typisk brug |
  |---|---|---|
  | `httpx` | 0.28.1 | HTTP-kald til API'er |
  | `requests` | 2.34.2 | HTTP-kald til API'er (ældre projekter) |
  | `python-dotenv` | 1.2.2 | Læse `.env`-filer med brugernavn/adgangskode |
  | `openpyxl` | 3.1.5 | Læse og skrive Excel-filer (`.xlsx`) |
  | `pydantic` | 2.13.4 | Datavalidering og -modeller |
  | `pywin32` | 311 | Windows-integration |
  | `pdfplumber` | 0.11.9 | Læse og udtrække tekst fra PDF-filer |
  | `beautifulsoup4` | 4.13.5 | HTML/XML-parsing |
  | `pip-audit` | — | Sårbarhedsscanning af installerede pakker |
  | `pip-tools` | — | Genererer `requirements.txt` med hashes |

- **Fælles `.venv`:** Alle projekter deler ét virtuelt miljø i
  `C:\Users\B294260\Python\.venv`. Aktiveres med:
  `& C:\Users\B294260\Python\.venv\Scripts\Activate.ps1`
- **Kørsel:** Scripts køres manuelt fra terminalen af én bruger.
- **Output-mappe:** `output filer/` i det enkelte projekts mappe.
  Mappen oprettes automatisk af scriptet (`mkdir(parents=True, exist_ok=True)`).
  Eksisterende filer overskrives ved genafkørsel – det er ønsket adfærd.

---

## Deployering og portabilitet

Tænk altid deployering igennem inden du bygger: kan det rent faktisk
installeres og bruges på kollegernes Statens IT-maskiner?

- Foretruk løsninger der kræver minimal installation
- Kendte og standardiserede løsninger foretrækkes frem for eksotiske valg —
  de scorer bedre i en Statens IT-kontekst
- Output skal være selvstændigt — en HTML-fil der er afhængig af lokale
  datafiler eller eksterne CDN'er kan ikke sendes til en kollega
- Vær opmærksom på dataafhængigheder: hvad sker der med outputtet hvis
  filstierne på en kollega-PC er anderledes?

Projektets formål kan ændre sig undervejs — da Peter arbejder associativt er
projekterne ikke altid klart definerede fra starten. Hjælp løbende med at
revurdere formålet, særligt når retningen skifter, så tekniske valg som
arkitektur, output-format og deployment stadig passer til det faktiske formål.

---

## Kodestil

- **Alt synligt for brugeren skrives på dansk** — kommentarer, variabelnavne
  og fejlbeskeder — så kolleger og ledere med begrænset kodningserfaring kan følge med.
- Navngiv funktioner og variabler beskrivende og på dansk,
  fx `find_relevante_filer`, `skriv_csv`, `fuld_sti`.
- Skriv korte forklarende kommentarer til logik der ikke er selvindlysende.
- Undgå unødvendig kompleksitet – hvert script løser én afgrænset opgave.
- Brug type hints (`list[Path]`, `str`, osv.) for læsbarhed.

## Struktur for nye scripts

Følg denne opbygning:
1. Docstring øverst der forklarer hvad scriptet gør
2. Imports
3. Konfiguration som konstanter med STORE_BOGSTAVER
4. Hjælpefunktioner
5. En `main()`-funktion der samler det hele
6. `if __name__ == "__main__": main()` nederst

Ved scripts der tager mere end 15 sekunder at køre: byg resume-funktionalitet
ind — gem fremskridt løbende så et afbrud ikke kræver at starte forfra.
Peter foretrækker at køre disse scripts i sin egen terminal for at følge processen.
