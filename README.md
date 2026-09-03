# Dubai Rent Shield

A bilingual (English / Legal Arabic) statutory tenancy-notice platform for
Dubai landlords, property managers, and agents — generates RERA-compliant
12-month eviction notices (Law No. 33 of 2008, Article 25(2)) and 30-day
lease-breach notices (Article 25(1)).

## Repo layout

This repo is structured after [minthcm](https://github.com/minthcm/minthcm)'s
module conventions (`api/`, `vue/`, `mcp/`, `docker/`, `install/`) — **as an
architectural reference only**. MintHCM itself is an AGPL-3.0-licensed HR
platform with no eviction/tenancy domain logic; none of its code, modules,
or license carry over here. Everything in `api/`, `vue/`, `mcp/`, `ocr/`, and
`shared/` is original to this project.

```
shared/     Single source of truth for the legal logic: statutory reasons,
            RERA date math (365-day / 30-day), the bilingual notice
            templates, and the compliance-clause checker. Imported by api/,
            vue/, and mcp/ as a workspace package (@rentshield/shared) so
            the legal text, date rules, and clause detection can never
            drift between the three.

api/        Express + Node's built-in SQLite (node:sqlite — no external
            database to install). CRUD for saved notices (re-renders the
            bilingual document from shared/ on every read), and a
            /api/documents/analyze route that forwards an upload to ocr/
            and runs shared/'s compliance checker on the result.

vue/        Vue 3 + Vite + Pinia + Tailwind v4 + Vue Router. A dashboard-
            platform shell (collapsible sidebar navigation, top bar) around
            the wizard + live bilingual preview, ported from the original
            single-file prototype (legacy/index.html) onto this real
            frontend.

mcp/        A real MCP (Model Context Protocol) server — calculate_notice_
            expiry, draft_eviction_notice, list_statutory_reasons — the
            actual integration point the prototype's chat panel only
            simulated locally. Any MCP client (Claude Desktop, Claude Code)
            can attach to it over stdio.

ocr/        A Python/FastAPI service wrapping PaddleOCR
            (github.com/PaddlePaddle/PaddleOCR) — turns an uploaded tenancy
            addendum (image, PDF, or .txt export) into text for api/'s
            compliance checker to scan. The only non-Node service, so it
            isn't an npm workspace; see "Running it locally" below.

docker/     Dockerfiles + compose for the ocr, api, and vue services.

install/    seed.js — seeds the local SQLite database with example notices.

legacy/     The original single-file HTML/CSS/JS prototype this platform
            was rebuilt from. Kept for reference; not part of the build.
```

## Running it locally

```bash
npm install                 # installs all Node workspaces (shared/api/vue/mcp)
npm run seed                # optional: seed example notices

# ocr/ is Python, not an npm workspace — set up its venv once:
python3 -m venv ocr/.venv
source ocr/.venv/bin/activate
pip install -r ocr/requirements.txt
deactivate

source ocr/.venv/bin/activate && npm run dev:ocr   # http://localhost:8001
npm run dev:api                                     # http://localhost:4000
npm run dev:vue                                     # http://localhost:5173 (proxies /api -> :4000)
```

The chat drawer's document upload works without `ocr/` running for `.txt`
uploads (no OCR needed) but needs it for images/PDFs — the API returns a
clear "OCR service unavailable" error otherwise rather than hanging.
PaddleOCR downloads its detection/recognition models on first real use
(a few MB, from HuggingFace/ModelScope/BOS) and caches them under
`~/.paddlex`; that first request will be slower than the rest.

To run the MCP server standalone (e.g. to attach it to Claude Desktop):

```bash
npm run dev:mcp
```

Or with Docker (builds all three services, `ocr` included):

```bash
docker compose -f docker/docker-compose.yml up --build
```

## What's ported from the prototype vs. not yet

**Ported to the new architecture:** the 4-step wizard, the full bilingual
(EN/AR) document for both notice types, the 365-day/30-day date engine, the
reason-specific compliance warnings, the pre-payment blur, real persistence
via the API, the RentShield AI chat drawer (conversational intake, off-topic
refusal, drag-and-drop document upload — now backed by **real OCR**, see
below), and the simulated Stripe-style paywall modal (fake card form →
processing → success → unblur → print).

The chat drawer is still a local simulation, same as the prototype — no
network calls, no API key in the browser. `mcp/server.js` is the real
integration point for wiring it to an actual hosted model later: its tool
descriptions (Dubai-only focus, hedged legal language, the 12-month vs
30-day distinction) are written to match what the simulated chat already
does, so swapping the simulation for real tool calls shouldn't change the
UX contract.

The mobile/PWA polish is ported too: `viewport-fit=cover` + safe-area
insets on the header, the chat toggle button, and the chat input bar, the
16px-on-mobile fix for form inputs (prevents iOS Safari's zoom-on-focus),
`format-detection` so Ejari/plot numbers don't become tap-to-call links,
an inline SVG favicon/apple-touch-icon, and a runtime-generated Web App
Manifest (`vue/src/pwa.js`, a Blob URL — no static manifest file needed)
so "Add to Home Screen" launches it standalone on both iOS and Android.

At this point everything from `legacy/index.html` has a counterpart in the
new architecture except payment, which is still fully simulated (no real
Stripe integration) — true of the original prototype too, not a regression.

## Real OCR (ocr/, replacing the scripted response)

The prototype's document-analysis card always said the same thing — "found
a clause stating 60 days notice" — no matter what was actually uploaded.
That's now a real pipeline:

```
Vue (ChatDrawer.vue)
  → POST /api/documents/analyze (multipart file)
api/ (documents.js)
  → POST ocr:8001/extract (forwards the file)
ocr/ (main.py, PaddleOCR)
  → extracts text (OCR for images/PDFs, direct read for .txt)
api/ (documents.js)
  → shared/complianceCheck.js scans the extracted text for
    "<N> days notice" clauses under the 365-day statutory minimum,
    and for an Ejari number
  → returns { ocr, analysis } to Vue
Vue (ChatDrawer.vue)
  → renders the actual findings (or "nothing suspicious found" if
    clean) and auto-fills Ejari only if the OCR text actually had one
```

Verified end-to-end: a `.txt` upload reading "Landlord may terminate with
60 days notice... Ejari Certificate No: 1234567890" produces a real
RERA Compliance Alert quoting that exact clause and auto-fills
`1234567890` (not a placeholder) into the wizard's Ejari field; a clean
365-day clause produces no alert. Image/PDF OCR is written against
PaddleOCR's real 3.x API (confirmed installing and importing correctly)
but its first-use model download reaches HuggingFace/ModelScope/BOS —
hosts this project's own dev sandbox couldn't reach to fully exercise that
path end-to-end; the service returns a clear 502 rather than hanging when
that happens, so this is a "verify once you deploy somewhere with normal
internet access" note, not a known bug.

`analyzeTenancyText` is deliberately simple regex matching, not a
language model — it catches the literal pattern "&lt;number&gt; days
notice" and nothing worded differently. A clean scan is a real signal,
not proof the document has no other issues.

## App shell (dashboard-platform layout)

The prototype was a single-page tool; the Vue app is now a routed
dashboard-platform shell, matching MintHCM's UI pattern (sidebar nav + top
bar + module switcher) rather than just its folder structure:

```
vue/src/components/shell/
  Sidebar.vue   Dark sidebar, module nav (Dashboard / New Notice / Saved
                Notices / Settings) driven by router.js's route meta, plus
                an "AI Assistant" entry that opens the chat drawer. Slides
                in as an overlay under the lg: breakpoint; at lg: and above
                it's collapsible to an icon rail (a "Collapse" toggle at
                the bottom), remembered per browser via localStorage.
  TopBar.vue    Page title (from route meta), a "New Notice" quick action,
                and a mobile hamburger to open the sidebar.

vue/src/views/
  DashboardView.vue      Real stat tiles (total / 12-month / 30-day /
                          premium — computed from saved notices, not fake
                          numbers) + a recent-notices panel.
  NoticeBuilderView.vue  The wizard + live preview (what used to be the
                          whole app) at /notices/new.
  NoticesListView.vue    Every saved notice as a table, at /notices.
  SettingsView.vue       Live API health check, default tier, and app info.
```

`App.vue` is now just the shell (`Sidebar` + `TopBar` + `<router-view>`)
with `ChatDrawer` and `PaymentModal` mounted globally so they overlay
whichever page is active, exactly as before.

**Known limitation:** the production Docker build serves `vue/` as a static
bundle, which doesn't proxy `/api/*` the way the Vite dev server does — a
production deployment needs a reverse proxy or a configurable API base URL
before `docker compose up` is a real one-command deploy.
