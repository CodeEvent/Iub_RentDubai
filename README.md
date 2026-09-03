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

ocr/        A Python/FastAPI service running PaddleOCR's PP-OCRv4 models
            (github.com/PaddlePaddle/PaddleOCR) via RapidOCR's ONNX export
            (github.com/RapidAI/RapidOCR) — turns an uploaded tenancy
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
clear "OCR service unavailable" error otherwise rather than hanging. The
OCR models ship inside the `rapidocr-onnxruntime` pip package itself (no
external download at all, from any host), so the very first request is
only slightly slower than the rest (constructing the ONNX runtime
session), not a multi-second model fetch.

To run the MCP server standalone (e.g. to attach it to Claude Desktop):

```bash
npm run dev:mcp
```

Or with Docker (builds all three services, `ocr` included):

```bash
docker compose -f docker/docker-compose.yml up --build
```

### Sharing a click-through UI preview (no backend required)

Because this is now a real multi-service app, there's no single file to
just send someone anymore — seeing it live normally means running `api/`
and `vue/` (and `ocr/` for the chat's document upload) yourself. For
sharing the UI itself without any of that:

```bash
cd vue
npm run build:preview     # -> dist-preview/index.html (self-contained,
                           #    JS + CSS inlined, one file)
```

This is a separate build path (`vite.preview.config.js` +
`vite-plugin-singlefile`), not the real deployment (`docker/web.Dockerfile`
still builds the normal multi-file bundle for that). Every backend-
dependent feature — saving a notice, the chat's document upload, the
saved-notices list, the Settings API health check — fails exactly as
gracefully in this build as when the real `api/` is simply offline; none
of it is mocked. `npm run build:preview` also runs
`scripts/strip-html-shell.js`, which produces `dist-preview/content-only.html`
— the page content with the `<!doctype>/<html>/<head>/<body>` wrapper
tags removed, for pasting into a tool that supplies its own document
skeleton (e.g. an Artifact-hosting service). Publish `dist-preview/index.html`
directly instead if the destination wants a complete, self-contained page.

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
ocr/ (main.py, RapidOCR running PaddleOCR's PP-OCRv4 models)
  → extracts text: OCR for images, page-by-page rasterize+OCR for PDFs
    (via pypdfium2), direct read for .txt
api/ (documents.js)
  → shared/complianceCheck.js scans the extracted text for
    "<N> days notice" clauses under the 365-day statutory minimum,
    and for an Ejari number
  → returns { ocr, analysis } to Vue
Vue (ChatDrawer.vue)
  → renders the actual findings (or "nothing suspicious found" if
    clean) and auto-fills Ejari only if the OCR text actually had one
```

**This is genuinely verified end-to-end**, not just written and hoped for
— including the image/PDF path, not only `.txt`. The original plan used
the `paddleocr` pip package directly, whose first-use model download
reaches HuggingFace/ModelScope/BOS; every one of those hosts turned out to
be blocked by this project's own dev sandbox, so that path couldn't be
exercised for real. The fix: `ocr/` runs the identical PP-OCRv4
detection/recognition models via **RapidOCR**
(github.com/RapidAI/RapidOCR), an ONNX export of PaddleOCR's own models
maintained specifically for easier deployment — the model files ship
inside the `rapidocr-onnxruntime` pip wheel itself, so there is no
external download at all, from any host, ever. That unblocked full
verification:

- A real PDF, rendered to an image and OCR'd, correctly extracted
  "Landlord may terminate with 60 days notice" and "Ejari Certificate No:
  1234567890" — the API's compliance checker correctly flagged the 60-day
  clause, and driving the actual Vue app in a browser confirmed the alert
  rendering in the chat and `1234567890` landing in the wizard's real
  Ejari input field (not a hardcoded placeholder).
- A clean document with a 365-day clause correctly produces no alert.
- **A real, honest limitation surfaced by this testing, not hidden**: on
  a lower-quality test image, OCR misread "60" as "6o" (a genuine
  character-confusion artifact on noisy input), and the compliance
  regex — which requires actual digits — missed that clause as a result.
  The higher-quality PDF read the same text correctly. This means OCR
  accuracy on a blurry phone photo is a real limiting factor for the
  compliance check, not just a theoretical one — worth knowing before
  relying on it for anything high-stakes.

`analyzeTenancyText` is deliberately simple regex matching, not a
language model — it catches the literal pattern "&lt;number&gt; days
notice" and nothing worded differently, or misread by OCR. A clean scan
is a real signal, not proof the document has no other issues.

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
                          AI-reviewed — computed from saved notices, not
                          fake numbers) + a recent-notices panel.
  NoticeBuilderView.vue  The wizard + live preview (what used to be the
                          whole app) at /notices/new.
  NoticesListView.vue    Every saved notice as a table, at /notices.
  SettingsView.vue       Live API health check, service charges, default
                          add-ons, and app info.
```

`App.vue` is now just the shell (`Sidebar` + `TopBar` + `<router-view>`)
with `ChatDrawer` and `PaymentModal` mounted globally so they overlay
whichever page is active, exactly as before.

**Known limitation:** the production Docker build serves `vue/` as a static
bundle, which doesn't proxy `/api/*` the way the Vite dev server does — a
production deployment needs a reverse proxy or a configurable API base URL
before `docker compose up` is a real one-command deploy.

The router uses hash history (`/#/notices/new`, not `/notices/new`)
deliberately — it needs no server-side SPA-rewrite rule to serve a deep
link or survive a refresh, which matters for a static bundle (Docker,
`vue/dist` opened directly, or a single-file preview build).

## Pricing (shared/pricing.js)

A base generator fee plus optional add-on services, priced and selected
individually — a checkbox cart, not a flat two-tier toggle. Modeled on how
jurist.ae's Tenant Eviction Notice product structures its checkout (a base
price plus add-ons like Apostille, MOFA Attestation, and Express Service),
but priced for what this platform actually is — an instant self-serve
generator — not what Jurist is selling: a human-lawyer-drafted, physically
notarized, ID-verified, courier-served document for 3,950 AED base plus
hundreds-to-thousands in add-ons. This platform doesn't perform that labor,
so it isn't priced like it does.

```
Bilingual Notice Generator ............ 95 AED   (base — always included)
+ Add Notarization Service ........... 249 AED   (add-on)
+ Add AI Compliance Review ............ 99 AED   (add-on — auto-selected
                                                   when the chat's document
                                                   upload finds something)
```

`shared/pricing.js` is the single source of truth (`BASE_PRICE_AED`,
`ADD_ONS`, `calculateTotal()`) — imported by the Pinia store for the
add-ons checklist and payment-modal breakdown, and by `api/` for
`GET /api/pricing` and for computing `totalPriceAed` on every saved
notice. `add_notarization` and `add_ai_review` are separate boolean
columns on the `notices` table (replacing the old single `tier` column).
