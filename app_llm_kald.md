# App: Minimalistens LLM kald

> Sidst opdateret: 2026-06-17 · Status i AgentBase: **Udgivet** (Privat) · Kørsler: 0

Generisk LLM-kald: send en instruktion + et indhold, få et tekstsvar tilbage.

---

## Overblik
- **Formål:** Behandl et stykke tekst efter en fri instruktion (opsummér, omskriv,
  klassificér, udtræk osv.) via en sprogmodel.
- **Ejer / Team:** Peter Kure / Center for Landdistriktsudvikling
- **app_id:** `b6d24a0b-7473-4f1a-93ef-38793b529b96`
- **Endpoint:** `POST https://api.flows.syv.ai/api/v1/apps/b6d24a0b-7473-4f1a-93ef-38793b529b96/run`
- **Underliggende model (flow-config):** `gpt-5.4`, reasoning slået til, system-instruktion
  `"You are a helpful assistant."` (kan ændres i flowet inde i AgentBase).

---

## Inputs (request body)
| Felt | Type | Beskrivelse |
|---|---|---|
| `indhold_tekst` | str | Teksten der skal behandles |
| `instruktion_tekst` | str | Hvordan indholdet skal behandles |

## Outputs (response body)
| Felt | Type | Beskrivelse |
|---|---|---|
| `svar` | str | Sprogmodellens svar |

---

## Eksempel — request body
```json
{
  "inputs": {
    "indhold_tekst": "<Indhold_Tekst>",
    "instruktion_tekst": "<Instruktion_Tekst>"
  }
}
```

## curl
```bash
curl -X POST "https://api.flows.syv.ai/api/v1/apps/b6d24a0b-7473-4f1a-93ef-38793b529b96/run" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "indhold_tekst": "<Indhold_Tekst>",
      "instruktion_tekst": "<Instruktion_Tekst>"
    }
  }'
```

---

## Bemærkninger
- Output er ren tekst (`str`), ikke struktureret JSON.
- Hvis de offentlige inputnavne ændres i flowets API-kontrakt, skal denne fil opdateres.

## Praksis-erfaringer
_(udfyldes efterhånden som appen bruges — fx typiske instruktioner, svartider, kvalitet)_
