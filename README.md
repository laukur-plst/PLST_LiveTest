# Plandata Supportmentor

Lokal svarbase til Plandata Support. Appen tager en supporthenvendelse, finder relevante kilder og kalder AgentBase-flowet fra `app_llm_kald.md` for at lave et kvalitetssikret svarudkast.

## Kør lokalt

```powershell
python server.py --host 127.0.0.1 --port 8765
```

Åbn derefter:

```text
http://127.0.0.1:8765
```

Kildeadministrationen ligger her:

```text
http://127.0.0.1:8765/kilder.html
```

Svarbanken ligger her:

```text
http://127.0.0.1:8765/svarbank.html
```

GIS-fejlsøgning ligger her:

```text
http://127.0.0.1:8765/gis.html
```

## API-nøgle

API-nøglen skal ligge i `adgangskoder.env` eller som miljøvariabel. Appen leder efter et af disse navne:

```text
API_KEY
SYV_API_KEY
AGENTBASE_API_KEY
FLOW_API_KEY
```

Hvis ingen af navnene findes, bruger appen første ikke-tomme værdi i `adgangskoder.env`.

`adgangskoder.env` er ignoreret af Git og må ikke kopieres ind i kode eller dokumentation.

## Kildegrundlag

Kildekonfigurationen ligger i `data/videnskilder.json`.

Godkendte Confluence-områder ligger i:

```text
data/godkendte_confluence_omraader.json
```

Offentlige Plandata.dk-kilder ligger i:

```text
data/plandata_offentlige_kilder.json
```

Importerede sider gemmes i en lokal SQLite-database:

```text
data/vidensbase.sqlite3
```

Databasen er ignoreret af Git.

Svarbank, tags og kilderelationer gemmes i samme SQLite-database.

Historiske PlanDK-/PlansystemDK-PDF'er kan importeres med:

```powershell
python importer_historiske_datamodel_pdf.py
```

Scriptet læser kun de angivne PDF-filer fra O-drevet og skriver udtrukket tekst til den lokale SQLite-vidensbase.

Generelle planlægningsvejledninger kan importeres med:

```powershell
python importer_planlaegningsvejledninger_pdf.py
```

Scriptet læser kun de angivne PDF-filer fra O-drevet og skriver udtrukket tekst til den lokale SQLite-vidensbase.

## Prioritet

Plandata.dk har prioritet `0` og kommer før Confluence i svargrundlaget. Godkendte Svarbank-svar og egentlig system-/vidensdeling bør vægte højere end standardsvarsskabeloner.

Confluence-kilderne er kun de fire godkendte områder:

- Standardsvar
- Supportens vidensdeling
- Datamodel/API/Digital Kommuneplan
- Fejl og kendte sager

Vedhæftede `.msg`-mails kan importeres som kilde-type `Mail` med prioritet `3` under området `Tidligere supportsager`.

Godkendte spørgsmål/svar fra Svarbank gemmes som kilde-type `Svarbank`. Kun svar med status `godkendt` bliver indekseret og brugt som kilde i nye svar.

Standardsvar skal forstås som skabeloner til sager, der ikke er tilstrækkeligt oplyst eller ikke kræver egentlig supporthandling fra Plandata Support. De må derfor ikke automatisk behandles som det rigtige svar til borgeren, kommunen eller rådgiveren, hvis sagen kræver konkret support, datamodelafklaring, systemvejledning eller fejlsøgning. I kildeprioriteringen ligger de lavere end Plandata.dk, Svarbank, relevant vidensdeling og datamodel/API-kilder.

Historiske PlanDK-/PlansystemDK-dokumenter er importeret som kilde-type `Historisk dokument` under området `Historisk PlansystemDK datamodel` med prioritet `6` og tags:

- `historisk`
- `plansystemdk`

De må bruges som baggrunds- og fejlsøgningskilder, men skal altid kontrolleres mod Plandata.dk, gældende datamodel og nyere godkendte kilder.

Generelle planlægningsvejledninger er importeret som kilde-type `Planfaglig vejledning` under området `Generel planlægning og planlovsvejledning` med prioritet `7` og tags:

- `planloven`
- `vejledning`
- `ikke system vejledning`

De må bruges som planfaglig baggrund, men er ikke systemvejledning og skal kontrolleres mod gældende lovgivning, Plandata.dk og nyere godkendte kilder.

## Svarbank

`/svarbank.html` bruges til at oprette gode spørgsmål og kvalitetssikrede svar, der senere kan bruges som kildegrundlag.

Hvert svar har:

- spørgsmål
- svar
- status: `kladde`, `godkendt` eller `forældet`
- prioritet
- tags
- eventuelle bilag

Kun `godkendt` indhold indekseres i vidensbasen. Hvis et svar sættes tilbage til `kladde` eller `forældet`, fjernes det fra den søgbare kildeindeks, men bevares i svarbanken.

Status betyder:

- `kladde`: gemt i Svarbank, men bruges ikke som kilde endnu
- `godkendt`: indekseres og kan bruges som kilde i nye svar
- `forældet`: bevares til historik, men fjernes fra søgeindekset

Bilag til Q&A læses via samme uploadfunktion som hovedsiden. Når et Q&A-svar er `godkendt`, indgår den udtrukne tekst fra bilagene i det indekserede kildegrundlag.

## Tags og relationer

`/kilder.html` kan bruges til at ændre prioritet og tags på importerede kilder. Tags bruges i søgningen og kan løfte relevante kilder, når brugerens spørgsmål matcher et tema.

Kilder kan også forbindes med relationer:

- `supplerer`
- `erstatter`
- `erstattes af`
- `modsiger`
- `eksempel på`
- `kræver`

Relationerne er første version af en vidensgraf. De bruges primært til overblik og governance, men kan senere vægtes direkte i søgningen og i LLM-prompten.

Relationer ændrer ikke indholdet i kilderne. De gemmer kun metadata om, hvordan kilderne bør forstås i forhold til hinanden.

## Kildeadministration

`/kilder.html` viser alle importerede kilder, kilde-type, område og prioritet/ranking.

Plandata.dk-kilder kan opdateres fra kildesiden eller via:

```text
POST http://127.0.0.1:8765/api/kilder/opdater-plandata
```

Confluence-opdatering kræver fortsat en indlogget session eller et særskilt Atlassian-token.

## Status-endpoints

```text
GET http://127.0.0.1:8765/api/vidensbase/status
GET http://127.0.0.1:8765/api/vidensbase/sider
```

## LLM-flow

Flowet kaldes med:

- `indhold_tekst`: henvendelse, intern kontekst, forhåndsintent og konkrete kildeuddrag
- `instruktion_tekst`: systemprompten og regler for ikke at opfinde dokumentation

Hvis API-nøglen mangler, eller LLM-kaldet fejler, laver serveren et lokalt fallback-svar, der tydeligt markerer manglende dokumentation.

LLM-kaldet bruger en direkte HTTPS-forbindelse uden Python/urllib-proxy. Det skyldes, at nogle lokale miljøer sætter proxy til `127.0.0.1:9`, hvilket får Python-kald til AgentBase til at fejle med `WinError 10061`, selv om `curl` kan nå endpointet.

## Svarmodus og kildeadvarsler

Forsiden har et felt til svarmodus, som hjælper svarbasen med at vælge den rigtige type svar:

- `Supportfagligt svar`: almindeligt eksternt svarudkast med konkret supportvejledning.
- `Bed om flere oplysninger`: kort svar, hvor standardsvarsskabeloner gerne må bruges til at bede om manglende oplysninger.
- `Intern vurdering`: internt notat med tydelig skelnen mellem dokumenteret viden, antagelser og næste handling.
- `Teknisk fejlsøgning`: analyse af fejlbeskeder, GIS-/filanalyse, datamodel, API og kendte fejl.
- `Planfaglig baggrund`: planfaglig kontekst, hvor generelle vejledninger markeres som baggrund og ikke systemfacit.

Resultatfeltet viser kildeadvarsler, når svaret bygger på svagere eller mere kontekstafhængige kilder:

- standardsvarsskabeloner uden at svarmodus er `Bed om flere oplysninger`
- historiske PlanDK-/PlansystemDK-dokumenter
- tidligere mails
- generelle planfaglige vejledninger
- manglende Plandata.dk-, Svarbank- eller datamodel/API-kilder
- uploadede bilag der kræver OCR/vision-læsning

## Filupload og OCR

Forsiden kan uploade bilag til den konkrete henvendelse. Filerne gemmes lokalt i:

```text
data/uploads/
```

Mappen er ignoreret af Git. Udtrukket tekst sendes med som ekstra kontekst til AgentBase-flowet, men kun for den aktuelle besvarelse.

Aktuel håndtering:

- Tekst, Markdown, CSV, JSON, XML og HTML læses direkte.
- DOCX læses via dokumentets interne XML.
- PDF forsøges læst med en lokal PDF-læser, hvis runtime har en tilgængelig.
- GeoJSON analyseres for feature-antal, geometrityper, bbox, CRS, attributfelter og simple polygonfejl som manglende lukning, nulareal, gentagne nabopunkter og mulige selvskæringer.
- GML/XML analyseres for GML-geometrielementer, koordinater, bbox og attribut-/elementfelter.
- Zippede shapefiles analyseres for `.shp`, `.shx`, `.dbf`, `.prj`, record-antal, bbox, shape type, DBF-felter og simple polygonringfejl.
- Scannede PDF'er og billedfiler markeres som OCR-krævende.
- MSG-filer markeres som krævende særskilt mailimport eller MSG-parser.

OCR er bevidst ikke endeligt løst endnu. Der skal tages aktivt stilling til den langsigtede model:

- Skal OCR køre lokalt, fx Tesseract, eller via en godkendt vision-/sprogmodel?
- Må bilag med personoplysninger, fortrolige oplysninger eller sagsdata sendes til ekstern modelbehandling?
- Hvilke filtyper og størrelsesgrænser skal være tilladt i produktion?
- Hvor længe må uploadede filer gemmes, og skal de automatisk slettes?
- Skal brugeren aktivt godkende, at OCR-tekst bruges i et LLM-kald?
- Hvordan skal OCR-kvalitet, fejllæsninger og kildehenvisninger vises i svaret?
- Skal uploadede filer kunne indekseres varigt i vidensbasen, eller kun bruges midlertidigt i den aktuelle sag?

## GIS-filer og uploadfejl

Supportmentoren kan hjælpe med første fejlsøgning på GIS-filer, typisk når en kommune eller leverandør får uploadfejl i Plandata.dk.

`/gis.html` er et særskilt GIS-modul til upload og basisanalyse af GeoJSON, GML/XML, enkeltstående `.shp` og zippede shapefiles. Modulet danner en teknisk rapport med status, geometri-/strukturkontrol, bbox, CRS/PRJ og attributfelter. Rapporten kan kopieres eller sendes videre til forsiden, hvor den indsættes som intern kontekst og automatisk sætter svarmodus til `Teknisk fejlsøgning`.

Under upload dannes en teknisk GIS-rapport, som sendes med til LLM'en sammen med spørgsmålet. Rapporten kan blandt andet bruges til at vurdere:

- om filen har geometri og forventet feature-/record-antal
- om polygonringe ser lukkede ud
- om der er nulareal, gentagne nabopunkter eller mulige selvskæringer
- om bbox og koordinater ser sandsynlige ud
- om CRS/PRJ er angivet
- hvilke attributfelter der findes i filen
- om attributfelter bør sammenholdes med Plandata.dk's datamodel, kodelister og obligatoriske felter

Det er en basisanalyse uden fuld GIS-motor. Den må derfor ikke bruges som endelig geometrivalidering. I drift bør der tages aktivt stilling til, om appen skal have en egentlig GIS-valideringsmotor, fx GEOS/Shapely, GDAL/OGR eller en kontrolleret serverkomponent.

Typiske afhjælpningsspor, som modellen må foreslå med forbehold:

- kør `make valid` eller tilsvarende geometrireparation i GIS
- prøv `buffer(0)` på polygoner, når fejlen ligner selvskæring eller ringproblem
- eksportér filen igen med korrekt koordinatsystem
- sørg for at shapefiles uploades samlet som ZIP med `.shp`, `.shx`, `.dbf` og `.prj`
- kontroller feltnavne, datatyper og kodelisteværdier mod Plandata.dk's datamodel

Andre udeståender før egentlig drift:

- Afklaring af adgangsstyring og logging.
- Beslutning om SQLite fortsat er nok, eller om Postgres skal bruges til fælles drift.
- Klar prioriteringsmodel mellem Plandata.dk, Confluence, mails, uploads og eventuelle fremtidige sagskilder.
- Retningslinjer for kvalitetssikring, når svaret bygger på tidligere mails eller uploadede bilag.
- Beslutning om GIS-validering skal være ren basisanalyse, eller om der skal bruges en egentlig GIS-motor med versionsstyrede datamodelregler.
- Governance for Svarbank: hvem må godkende, hvornår skal svar revurderes, og hvordan markeres forældede svar.
