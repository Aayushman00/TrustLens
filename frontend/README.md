# TrustLens Frontend

React 19 + Vite 6 + TypeScript dashboard for the full journey without curl:
**import HF model → create evaluation (per-dimension draft) → poll status →
(Assisted: review) → report → publish / keep private**. Plain CSS, native
`fetch`, `react-router-dom` — no UI framework. Single-user local app: no login.

## Run

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (backend at http://localhost:8000)
npm run build      # tsc -b + vite build
npm test           # node --test format.test.ts + vitest
```

Or via Compose (`docker compose up --build -d` starts the Vite dev server in a
container). The API origin comes from `VITE_API_BASE_URL` (Compose sets it;
default `http://localhost:8000`). Backend CORS already allows
`http://localhost:5173`.

## Routes

| Path | Page |
|------|------|
| `/` | Overview: models + recent evaluations |
| `/models` | Model list (cursor pagination) |
| `/models/import` | HF import (repo id or URL, optional revision) |
| `/models/:id` | Model detail, documentation sources, start a new evaluation |
| `/evaluations` | Evaluation history |
| `/evaluations/new` | Per-dimension evaluation draft (dataset intake, column roles, confirm) |
| `/evaluations/:id` | Live status + timeline, mode disclosure, evidence dossier, O/S/D, confidence, FRIES, publish/unpublish, report link |
| `/evaluations/:id/review` | Assisted O/S/D review + finalize |
| `/reports/:evaluationId` | Report v-latest (auto-generates), JSON download, traceability |
| `/documentation` | Methodology notes |
| `/settings` | Local settings |
| `/gallery` | Design-system primitives gallery (outside the app layout) |

Unknown paths redirect to `/`.

## Demo script

1. **Import HF model** → `distilbert-base-uncased-finetuned-sst-2-english` →
   open model → create an **AI-Autonomous** evaluation → watch it poll to
   FINALIZED → View report → back → **Publish**.
2. Same model → create an **AI-Assisted** evaluation → status parks at
   AWAITING REVIEW → **Review O/S/D** → accept all or edit values → submit +
   finalize → FRIES appears, report shows *human-reviewed*.

## Known limitations

- Report PDF/JSON storage URIs are not browser-fetchable; the page offers a
  JSON download built from the inline `report_json` instead.
- No E2E suite; the demo script above is the manual checklist.
