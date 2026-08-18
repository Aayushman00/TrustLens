# TrustLens Frontend (Phase 23 — demo UI)

React 19 + Vite 6 + TypeScript dashboard for the full supervisor journey without
curl: **login → import HF model → create evaluation → poll status → (Assisted:
review) → report → publish / keep private → leaderboard**. Plain CSS, native
`fetch`, `react-router-dom` — no UI framework.

## Run

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (backend at http://localhost:8000)
npm run build      # tsc -b + vite build
```

Or via Compose (`docker compose up --build -d` starts the Vite dev server in a
container). The API origin comes from `VITE_API_BASE_URL` (Compose sets it;
default `http://localhost:8000`). Backend CORS already allows
`http://localhost:5173`.

## Routes

| Path | Page |
|------|------|
| `/login` | Email/password sign-in (dev seed users listed on the page) |
| `/` | Dashboard: models + recent evaluations |
| `/models` | Model list (cursor pagination) |
| `/models/import` | HF import (repo id or URL, optional revision) |
| `/models/:id` | Model detail + new-evaluation form (mode/task/dataset) |
| `/evaluations/:id` | Live status polling, mode disclosure, agent O/S/D (PROPOSED), confidence, FRIES scores, publish/unpublish, report link |
| `/evaluations/:id/review` | Assisted O/S/D review + finalize (reviewer/admin only) |
| `/reports/:evaluationId` | Report v-latest (auto-generates), JSON download, artifact URIs |
| `/leaderboard` | Published-only entries with task/dataset/mode filters |

All routes except `/login` redirect there when no session exists.

## Auth

- `POST /v1/auth/login` stores `access_token` + `refresh_token`; `GET /v1/auth/me`
  supplies the role used for gating.
- On any 401 the client refreshes once (`POST /v1/auth/refresh`, rotated pair,
  single-flight across concurrent requests), retries, and logs out if that fails.
- **Tokens live in `localStorage`** — an MVP tradeoff: simple and survives
  reloads, but readable by any JS running on the page (XSS). Acceptable for the
  local demo; a production build should move to httpOnly cookies or at least
  `sessionStorage` + a hardened CSP.

## Role gating (mirrors backend RBAC)

| Action | Who sees it |
|--------|-------------|
| Assisted review + finalize | reviewer / admin (researcher sees "waiting for reviewer") |
| Publish / unpublish | evaluation owner or admin |
| Everything else (import, evaluate, reports, leaderboard) | any signed-in user |

The backend enforces the same rules — the UI gating is UX, not security.

## Demo script (seed users via `make seed-users`)

1. Login `researcher@trustlens.local` / `trustlens-researcher-dev` → **Import HF
   model** → `distilbert-base-uncased-finetuned-sst-2-english` → open model →
   create **AI-Autonomous** evaluation (task e.g. `sentiment`) → watch it poll to
   FINALIZED → View report → back → **Publish to leaderboard** → Leaderboard
   shows the entry.
2. Same model → create **AI-Assisted** evaluation → status parks at AWAITING
   REVIEW; researcher sees *waiting for reviewer* (no review button).
3. Log out → login `reviewer@trustlens.local` / `trustlens-reviewer-dev` → open
   the evaluation → **Review agent O/S/D** → accept all or edit values →
   submit + finalize → FRIES appears, report shows *human-reviewed*.
4. Log out → login as the researcher again → publish the assisted evaluation →
   leaderboard lists both entries (filter by mode to compare).

## Known limitations

- Report PDF/JSON `s3://` URIs point at MinIO and are not browser-fetchable; the
  page offers a JSON download built from the inline `report_json` instead.
- The leaderboard requires a Bearer token (MVP choice) — "public" means
  published-only visibility, not anonymous access.
- No E2E suite; the demo script above is the manual checklist.
