# Survey — Real Estate Automation Discovery

Lead-gen survey for Avlok AI. Prospects answer 14 questions; the backend calls OpenAI, generates a branded PDF report with 10 automation recommendations + INR pricing, fires it to n8n for email delivery, and shows the client only a thank-you screen.

---

## Architecture

```
Frontend (Cloudflare Pages)          Backend (VPS + Cloudflare Tunnel)
surveyrealty.avlokai.com      →      survey-realty.avlokai.com
  index.html (static)                  FastAPI / uvicorn
                                        └── main.py
                                        └── submissions.json  (runtime, gitignored)
```

**Flow:**
1. Client fills 14-question survey at `surveyrealty.avlokai.com`
2. Frontend POSTs answers to `https://survey-realty.avlokai.com/api/submit`
3. Backend calls OpenAI (gpt-4o-mini) → returns 10 automations with INR pricing
4. Backend saves submission to `submissions.json`
5. Backend generates a PDF report with reportlab
6. PDF is POSTed in background to n8n webhook (client never sees this)
7. Client sees thank-you screen only — no analysis, no pricing

---

## Backend

**VPS:** `45.196.196.156`
**Directory:** `/root/backend_survey_realty/`
**Venv:** `/root/upload_backend/venv/` ← pm2 uses THIS venv, not the local one
**Process name:** `survey_realty`
**Exposed via:** Cloudflare Tunnel → `https://survey-realty.avlokai.com`

### Run / restart

```bash
pm2 restart survey_realty
pm2 logs survey_realty --lines 50
```

### Install dependencies (use the correct venv)

```bash
/root/upload_backend/venv/bin/pip install -r /root/backend_survey_realty/requirements.txt
```

### API endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/questions` | None | Returns the 14 survey questions |
| POST | `/api/submit` | None | Accepts submission, returns `{"success": true}` |
| GET | `/api/admin/submissions` | None | All raw submissions |
| GET | `/api/admin/stats` | None | Total submissions + token cost |

### Environment variables

```
OPENAI_API_KEY=sk-...
```

Set in `/root/backend_survey_realty/.env`

### Dependencies

```
fastapi==0.115.0
uvicorn==0.30.6
openai==1.51.0
python-dotenv==1.0.1
pydantic==2.9.2
reportlab==4.2.5
httpx==0.27.2
```

---

## Frontend

**Hosted:** Cloudflare Pages
**URL:** `https://surveyrealty.avlokai.com`
**Files:** `frontend/index.html`, `frontend/avlokai_logo.jpeg`
**No build step** — static HTML/JS

The API base URL is hardcoded in `index.html`:
```js
const API = 'https://survey-realty.avlokai.com';
```

---

## CORS

Explicit origins are whitelisted (wildcard `*` gets stripped by Cloudflare):

```python
allow_origins=[
    "https://surveyrealty.avlokai.com",
    "https://survey-realty.avlokai.com",
    "http://localhost:8000",
    "http://localhost:3000",
]
```

---

## Webhook (n8n)

**URL:** `https://n8n.avlokai.com/webhook/send-mails`
**Trigger:** fires after every successful submission (background task, client doesn't wait)
**Payload:** multipart form

| Field | Type | Value |
|-------|------|-------|
| `data` | binary file | PDF report (`automation_report.pdf`, `application/pdf`) |
| `name` | text | respondent name |
| `email` | text | respondent email |
| `phone` | text | respondent phone |
| `company` | text | company name (empty string if not provided) |
| `summary` | text | 2-sentence AI business summary |

---

## PDF Report

Generated with `reportlab`. Contains:
- Avlok AI header (navy)
- Client info table (name, email, phone, company, date)
- Business profile summary (2 sentences from OpenAI)
- Pricing table — 10 automations with: name, why it fits, priority badge, build fee (INR), monthly fee (INR)
- Totals row (sum of all build fees + monthly fees)
- Confidentiality footer

---

## OpenAI

**Model:** `gpt-4o-mini`
**max_tokens:** 900
**Response format:** `json_object`

Returns:
```json
{
  "summary": "2-sentence business profile",
  "recommendations": [
    {
      "name": "Automation name",
      "why": "Why it fits this business",
      "priority": "High | Medium | Low",
      "build_fee_inr": 75000,
      "monthly_fee_inr": 12000
    }
    // × 10, ordered High → Low priority
  ]
}
```

Pricing guidance in prompt:
- Simple: build ₹25k–₹60k / monthly ₹3k–₹8k
- Medium: build ₹60k–₹1.5L / monthly ₹8k–₹18k
- Complex: build ₹1.5L–₹3L / monthly ₹18k–₹40k

---

## What the client sees

After submitting:
- "Thank You, [First Name]! Your response has been recorded."
- "We've received your answers… Our team will reach out within 24 hours."
- WhatsApp CTA button

No analysis, no automations, no pricing is shown to the client.

---

## Deploy checklist

1. Edit `main.py` locally
2. `scp survey/backend/main.py root@45.196.196.156:/root/backend_survey_realty/`
3. `ssh root@45.196.196.156` → `pm2 restart survey_realty`
4. Edit `index.html` locally → push to git → Cloudflare Pages auto-deploys

---

## Known gotchas

- **Wrong venv:** pm2 uses `/root/upload_backend/venv/`, not `/root/backend_survey_realty/venv/`. Always pip install into the former.
- **CORS:** never revert to `allow_origins=["*"]` — Cloudflare strips it. Use explicit origins.
- **Cloudflare analytics beacon** (`cloudflareinsights.com/beacon.min.js`) being blocked by ad blockers in the browser console is harmless — ignore it.
- `submissions.json` and `uploads/` are runtime state — gitignored, not backed up automatically.
