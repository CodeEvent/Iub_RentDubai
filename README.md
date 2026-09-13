# Dubai Rent Shield

A bilingual (English / Legal Arabic) statutory tenancy-notice platform for
Dubai landlords, property managers, and agents — generates RERA-compliant
12-month eviction notices (Law No. 33 of 2008, Article 25(2)) and 30-day
lease-breach notices (Article 25(1)).

## History and current foundation

This platform went through five architectures:

1. A single-file HTML/CSS/JS prototype (`legacy/`).
2. A Node monorepo — Vue 3 + Express + `node:sqlite` + a real MCP server +
   a Python OCR microservice, with real DocuSeal/OpenSign e-signature
   integration, an `mcp/skills/` legal-guidance library, and an
   OpenContracts-inspired citation graph (`legacy-v1/`).
3. Rebased onto [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)
   (vendored at upstream commit `a3851c157a4591cd0e213296f632432f05daa7c8`,
   `main` branch) — a Django 5.2 + DRF + Celery/Redis + Angular document
   management system. This was an explicit choice to discard the Node
   stack and use paperless-ngx's actual codebase as the base, not just a
   bolt-on service or an architecture reference (both were offered and
   declined). The tenancy-notice domain logic was added as a first-party
   `rentshield` Django app alongside paperless-ngx's own `documents` app,
   with its own `Notice` database table carrying a foreign key to
   paperless-ngx's `Document`.
4. `rentshield` as a Django app — with its own database table — was
   removed entirely. Every notice became a real paperless-ngx `Document`,
   and every notice field (landlord, tenant, reason, e-sign status, ...)
   a paperless-ngx `CustomField` value on that Document — see "What's in
   `documents/rentshield/`" below. paperless-ngx itself became the sole
   system of record for RentShield data. The Angular frontend at this
   point still had its own separate branded shell (a dark "Rent Shield /
   RERA · DLD Compliant" sidebar, a 4-step wizard with a live preview
   panel) sitting alongside paperless-ngx's own UI, talking only to
   paperless-ngx's stock REST API underneath.
5. **The current foundation**: that separate branded shell was removed
   too. There is no "Rent Shield" product identity in the UI any more —
   `RentshieldFrameComponent` is deleted, and "New Notice"/"Notices"/
   "Legal Skills" are plain entries in paperless-ngx's own sidebar
   (`AppFrameComponent`), rendered inside paperless-ngx's own shell with
   paperless-ngx's own branding. The 4-step wizard with its live preview
   panel is gone too, replaced by a single-page "Generate Notice" form —
   still the same backend call, still auto-generating the real bilingual
   PDF, just without a bespoke multi-step UX. A generated notice now opens
   directly in paperless-ngx's own document detail view, where every
   RentShield field is a native, editable custom field alongside the
   rendered PDF — indistinguishable from any other document paperless-ngx
   manages. See "The Angular frontend" below for exactly what remains.

None of the four prior architectures are deleted — `legacy/` and
`legacy-v1/` are kept intact for reference, and every removed component's
history (the Phase-3 `rentshield` Django app, the Phase-4 branded shell
and wizard) is preserved in git even though none of it is in the working
tree any more.

**This repository is GPL-3.0-licensed** (`LICENSE`, paperless-ngx's own
license) as a direct consequence of that choice. This is a real, material
change from the previously-unlicensed root — read `LICENSE` before treating
any part of `src/` or `src-ui/` as usable under different terms.

```
src/            Django 5.2 + DRF backend, vendored from paperless-ngx —
                document management, OCR ingestion, tagging, full-text
                search (tantivy), Celery task queue.

src/documents/rentshield/  The tenancy-notice domain logic — a plain
                Python subpackage inside paperless-ngx's own `documents`
                app, not a separate installed Django app and not a
                separate database table. Ported 1:1 (same statutory
                citations, same wording) from legacy-v1/shared/ — see
                "What's in `documents/rentshield/`" below.

src/documents/rentshield_views.py  The handful of endpoints paperless-ngx
                has no native equivalent for (bilingual PDF rendering,
                pricing/notice-period math, e-signature orchestration),
                mounted directly under the documents/ URL namespace in
                paperless/urls.py rather than a separate API prefix.

src-ui/         Angular frontend, vendored from paperless-ngx.
                paperless-ngx's own UI shell (AppFrameComponent, its own
                sidebar/topbar/branding) is unmodified except for one new
                "Notices" nav-group added to its sidebar; a
                `src-ui/src/app/rentshield/` area holds the plain page
                components those links route to (notice-form, notices-list,
                legal-skills) as children of paperless-ngx's own frame
                route — not a separate branded shell — see "The Angular
                frontend" below. They talk only to paperless-ngx's own
                stock REST API plus the endpoints above; there is no
                separate rentshield API to maintain a parallel contract
                for.

docling-service/       Isolated FastAPI service wrapping Docling — see
                       "Document parsing" below.

deepseek-ocr-service/  Isolated FastAPI service wrapping DeepSeek-OCR
                       (GPU-only) — see "Document parsing" below.

docker/         paperless-ngx's own Docker Compose files (sqlite/postgres/
                mariadb variants, with/without Tika). This fork's own
                docker-compose.yml (repo root) composes paperless-ngx +
                docling-service (+ deepseek-ocr-service under the "gpu"
                profile) instead.

docs/           paperless-ngx's own documentation, including
                docs/development.md — the dev workflow this project's
                own setup below follows.

legacy-v1/      The retired Vue + Express + node:sqlite + MCP + Python-OCR
                monorepo, moved here intact (not deleted) when this repo
                was rebased onto paperless-ngx. Its own README.md
                documents that stack in full — real DocuSeal/OpenSign
                e-signature integration, an mcp/skills/ legal-guidance
                library, and a citation-graph document analyzer among it.

legacy/         The original single-file HTML/CSS/JS prototype. Kept for
                reference; not part of either subsequent build.
```

## What's in `documents/rentshield/`

There is no `rentshield` database table. A RentShield notice is a real
paperless-ngx `Document`; every notice field lives as a paperless-ngx
`CustomField` value on that Document (bootstrapped by the data migration
`documents/migrations/0026_rentshield_custom_fields.py` — 18 fields plus
a `RentShield Notice` tag, all `get_or_create`'d by name so it's safe to
re-run). This is what "paperless-ngx is the system of record" means
concretely: open any generated notice in paperless-ngx's own Documents
view and every field the wizard collected — landlord, tenant, reason,
e-sign status — is right there as a custom field, full-text search finds
the OCR'd notice text, and the notice is tagged, versioned, and
permissioned exactly like any other document paperless-ngx manages.

- `custom_fields.py` — the field-name/data-type table the bootstrap
  migration reads, plus `key_to_id_map()`/`id_to_key_map()` helpers used
  by every other module here to translate between short Python keys
  (`landlord_name`) and live `CustomField.id`s.
- `constants.py` — the six statutory/breach grounds (sale, personal use,
  demolition, renovation; non-payment, unauthorized subleasing), ported
  from `legacy-v1/shared/reasons.js`.
- `dates.py` — the 365-day / 30-day expiry math (Article 25(2) vs.
  25(1)), ported from `legacy-v1/shared/dateRules.js`.
- `notice_builder.py` — the full bilingual (EN/AR) notice content, ported
  from `legacy-v1/shared/noticeTemplate.js`.
- `pricing.py` — the base fee + add-ons pricing model, ported from
  `legacy-v1/shared/pricing.js`.
- `pdf.py` — renders a notice to HTML then to a real PDF via headless
  Chromium (Playwright for Python), a port of
  `legacy-v1/api/src/services/esign/renderNoticeHtml.js` +
  `renderPdf.js`.
- `service.py` — `generate_and_consume(fields, owner_id)` renders the PDF
  and hands it to paperless-ngx's own `documents.tasks.consume_file` task
  (the same one its own upload API uses) with every field passed through
  as a `CustomField` value and the `RentShield Notice` tag applied, via
  `DocumentMetadataOverrides.custom_fields`/`tag_ids` — paperless-ngx's
  own upload API (`POST /api/documents/post_document/`) supports exactly
  this same mechanism, confirmed by reading its serializer before relying
  on it. `read_notice_fields(document)`, `request_notarization(document)`,
  and `check_notarization_status(document)` read/write those
  `CustomFieldInstance` rows directly — no separate row to keep in sync.
- `service_methods.py` — the recognized/unrecognized notice-service
  methods under Article 25(3) (Notary Public, registered mail, court
  bailiff vs. WhatsApp, plain email, verbal, unwitnessed hand delivery),
  ported from `legacy-v1/shared/serviceMethods.js`.
- `citation_graph.py` — `build_citation_graph()`, an
  OpenContracts-inspired graph linking each notice-period clause and
  service-method mention found in a document to the specific Article 25
  provision it satisfies or violates, ported from
  `legacy-v1/shared/citationGraph.js`. Run automatically on every
  `POST /api/documents/notice/analyze/` call, against whichever engine
  (Docling/DeepSeek-OCR) extracted the text.
- `skills/*.md` + `skills_lib.py` — the three-skill legal-guidance library
  (RDSC filing, security deposit disputes, valid notice service methods)
  ported from `legacy-v1/mcp/skills/` — same files, copied verbatim
  (plain Markdown + YAML frontmatter, no JS-specific content), reparsed
  with PyYAML instead of gray-matter. Exposed at
  `/api/documents/notice/legal-skills/` (+ `/<id>/`) and
  `/api/documents/notice/check-service-method/`, matching what the MCP
  server (`list_legal_skills`/`get_legal_skill`/
  `check_notice_service_method_validity`) exposed in `legacy-v1/`.
- `esign/` — `docuseal_client.py`, `opensign_client.py`,
  `orchestrator.py`: real notarization via a self-hosted
  [DocuSeal](https://github.com/docusealco/docuseal) (primary) with
  automatic fallback to [OpenSign](https://github.com/opensignlabs/OpenSign),
  ported 1:1 from `legacy-v1/api/src/services/esign/` — same endpoint
  shapes (DocuSeal's `/api/submissions/html`, OpenSign's Parse-Server
  `createdocumentfromapp` Cloud Function), same primary/fallback
  behavior. Triggered via
  `POST /api/documents/notice/<document_id>/notarize/` and polled via
  `GET .../notarize-status/`, operating on the Document's own
  `CustomFieldInstance` rows.

`documents/rentshield_views.py` (one level up, not inside the
subpackage — it's the URL-facing layer) wires all of the above to HTTP:
`/api/documents/notice/reasons/`, `/pricing/`, `/preview/`, `/create/`,
`/analyze/`, `/legal-skills/[<id>/]`, `/check-service-method/`,
`/<document_id>/notarize/`, `/<document_id>/notarize-status/` — all
mounted inside the same `documents/` URL include block as paperless-ngx's
own `post_document`/`bulk_edit`/etc. endpoints in `paperless/urls.py`, not
under a separate `rentshield/` prefix. **Listing** notices and **polling
consumption status** use paperless-ngx's own stock endpoints directly —
`GET /api/documents/?tags__id__in=<rentshield_tag_id>` and
`GET /api/tasks/?task_id=<id>` (the same endpoint paperless-ngx's own
Tasks page uses) — with no RentShield-specific endpoint for either.

**Verified**: `citation_graph.py` reproduces the exact same
violating/compliant/empty-document test cases used to verify the
original JS version; the legal-skills endpoints and citation-graph were
exercised through a real HTTP round trip (Django → docling-service →
`citation_graph.py` → back), not just unit-level. The e-signature clients
were verified against mock HTTP servers shaped like each real API
(including the primary-fails → fallback-succeeds path, with a real
Playwright PDF render in the loop for OpenSign), and
`POST /api/documents/notice/<id>/notarize/` was exercised over real HTTP
with no live DocuSeal/OpenSign running — confirmed it degrades gracefully
(502 with both providers' actual error messages) exactly like the
original Node version did, plus the `add_notarization`-not-selected and
no-landlord-email 400 validation paths. The full create → consume →
custom-fields → list → notarize round trip was also exercised end to end
after the move onto CustomFields specifically: creating a notice with a
reason label containing a literal `/` ("Personal Use / Recovery") caught
a real, previously-latent filename-sanitization bug (the temp file
written to disk was sanitized but the `DocumentMetadataOverrides.filename`
passed to paperless-ngx's consumer wasn't, so the consumer's own working-
copy path build failed on the raw `/`) — fixed by sanitizing once and
reusing the sanitized name everywhere, not two independently-maintained
copies.

## Document parsing: Docling + DeepSeek-OCR

Two more open-source projects, evaluated and implemented as isolated
services (their own `pyproject.toml`/venv each — same reason `ocr/` was
its own service in `legacy-v1/`: keeping heavy ML dependency trees out
of the main paperless-ngx venv):

- **`docling-service/`** — [Docling](https://github.com/docling-project/docling)
  (IBM / LF AI & Data Foundation, MIT). Primary document parser for the
  "AI Compliance Review" add-on's upload: structured layout/table
  extraction to Markdown, not just flat OCR text.
- **`deepseek-ocr-service/`** — [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR)
  (DeepSeek AI, MIT). An opt-in, higher-accuracy OCR path for hard scans
  (handwriting, poor photos of a physical contract) — the caller chooses
  it explicitly (`use_deepseek_ocr=true`), it is never an automatic
  fallback.

Both are wired into `documents/rentshield/document_analysis.py` and
reachable via `POST /api/documents/notice/analyze/`.

**What's genuinely verified vs. what isn't, in this dev sandbox:**

- Docling: fully verified for text-native formats (`.txt`, and by the
  same code path DOCX/PPTX/XLSX/HTML) — a real request through Django →
  `docling-service` → the actual `docling` library → back, end to end.
  **PDF/image conversion is not verified here** — Docling's layout and
  table-structure models are only distributed via Hugging Face, which
  this sandbox's network policy blocks, and (unlike the OCR-engine
  ModelScope issue, fixed by pinning Tesseract in `main.py`) there is no
  pip-bundled alternative for those specific models. The service code is
  correct and would work wherever Hugging Face is reachable; here it
  fails cleanly with a clear 502 rather than hanging or crashing —
  confirmed directly.
- DeepSeek-OCR: **cannot run at all in this sandbox** — its own reference
  implementation calls `.cuda()` unconditionally (no CPU fallback), and
  this environment has no GPU. What's verified: the service starts, its
  `/health` correctly reports `cuda_available: false`, and `/extract`
  fails with a clear 503 explaining exactly why, rather than crashing —
  confirmed directly. Real inference needs a CUDA GPU deployment (see
  `deepseek-ocr-service/README.md` and the `gpu` Compose profile).

## AI Compliance Review — now actually wired up, not just a price toggle

Before this, "Add AI Compliance Review" in the notice form was a real
`CustomField` and a real line on the price total — with **nothing behind
it**. `documents/rentshield/document_analysis.py`'s `analyze_document()`
and `citation_graph.py`'s `build_citation_graph()` existed and were unit-
verified, but nothing in the actual notice-creation flow ever called
them, and nothing persisted a result anywhere. That gap is now closed:

1. Upload a tenancy contract through paperless-ngx's **own native
   uploader** — no new frontend was built for this. Either name the file
   with "contract" in it, or tag it `Tenancy Contract` after upload.
2. Two Workflows created by `manage.py create_rentshield_workflows`
   (#11/#12, one trigger on filename, one on tag) fire automatically on
   `Document Added` and call a webhook back into this same Django
   process at `/api/documents/notice/analyze-uploaded/`.
3. That endpoint (`documents/rentshield_views.py::analyze_uploaded_view`)
   only dispatches a Celery task and returns — paperless-ngx's own
   Workflow webhooks time out after 5 seconds, and the actual analysis
   (a docling-service HTTP call plus the citation graph) takes longer
   than that.
4. `documents.tasks.run_ai_review_task` → `documents/rentshield/service.py`'s
   `run_ai_review()` does the real work: reads the document's own file
   (`document.source_path`), calls `analyze_document()`, runs
   `build_citation_graph()` against the extracted text, and writes the
   result back onto **that same Document's own CustomFieldInstance
   rows** — `RentShield: AI Review Summary` (a human-readable ✓/✗ list
   citing the specific Article 25 provision each clause satisfies or
   violates) and `RentShield: AI Review Findings Count` — then swaps its
   `Needs AI Review` tag for `AI-Reviewed`.

**Verified end-to-end, not just unit-level**: uploaded a real test
document via `POST /api/documents/post_document/` (the same endpoint
paperless-ngx's own UI upload button hits) containing a deliberately
non-compliant 30-day clause, a WhatsApp service-of-notice clause, a valid
Notary Public clause, and an Ejari number; confirmed via the Celery log
that the filename-based Workflow trigger matched and fired the webhook;
confirmed the webhook hit `analyze-uploaded` and dispatched the Celery
task; and confirmed via `GET /api/documents/<id>/` that the resulting
custom fields correctly flagged both violations, correctly credited the
valid clause, and correctly extracted the Ejari number — all with zero
manual intervention after the initial upload.

One real bug surfaced during this verification and is worth knowing
about, not just a passing curiosity: the **first** `run_ai_review_task`
run inside a freshly-started Celery worker took far longer than a direct
synchronous call of the same function (which returned near-instantly) —
almost certainly an httpx/connection-pool cold-start cost specific to a
freshly-forked prefork worker's first outbound HTTP call. Every
subsequent run on the same warmed-up worker completed promptly. Not a
logic bug (confirmed by running `run_ai_review()` directly in
`manage.py shell`, which worked immediately and correctly on the first
document too) — just a first-request latency spike to expect after a
worker restart, not a stall to debug.

## Running it locally

No Docker daemon is assumed — this follows paperless-ngx's own
Docker-free dev workflow (`docs/development.md`), run from `src/`:

```bash
# from the repo root
uv sync --group dev

# a Redis-compatible broker is required
redis-server --daemonize yes

cd src
export PAPERLESS_DBENGINE=sqlite
export PAPERLESS_SECRET_KEY=<any value for dev>
export PAPERLESS_REDIS=redis://localhost:6379
export PAPERLESS_DATA_DIR=../pgx-data
export PAPERLESS_MEDIA_ROOT=../pgx-media
export PAPERLESS_CONSUMPTION_DIR=../pgx-consume

uv run manage.py migrate
uv run manage.py createsuperuser

uv run manage.py runserver &
uv run celery --app paperless worker -l INFO --pool=solo &

# in another shell — docling-service (see "Document parsing" above)
cd docling-service && uv sync && uv run uvicorn main:app --port 8010 &
# deepseek-ocr-service needs a real CUDA GPU; start it the same way
# (cd deepseek-ocr-service && uv sync && uv run uvicorn main:app --port 8011)
# only on GPU-equipped infrastructure.
```

Real document consumption (OCR + PDF/A conversion) additionally needs
`tesseract-ocr`, `ghostscript`, `imagemagick`, `unpaper`, `qpdf`, and
`poppler-utils` installed as system packages — all verified working in
this project's dev sandbox via `apt-get install`.

**Verified end-to-end** (not just "should work"): creating a notice via
`POST /api/documents/notice/create/` renders a real PDF, hands it to
paperless-ngx's real consumption pipeline with every field attached as a
`CustomField` value, produces a real OCR'd `documents.Document` row, and
that document is found by paperless-ngx's own full-text search
(`GET /api/documents/?query=...`) — both the 365-day statutory path and
the 30-day breach path were tested this way, including confirming the
correct expiry-date math landed in the OCR'd text.

`uv sync` deliberately excludes `torch`/`sentence-transformers`/
`llama-index-*` (paperless-ngx's `paperless_ai` semantic-search feature,
not wired into `INSTALLED_APPS` by default) — this project's sandbox
cannot reach `download.pytorch.org`'s wheel host. Re-add them from
upstream paperless-ngx's `pyproject.toml` for a deployment that wants
that feature.

## The Angular frontend

There is no separate "RentShield" product shell any more. `New Notice`,
`Notices`, and `Legal Skills` are plain entries in paperless-ngx's **own**
sidebar (`src-ui/src/app/components/app-frame/app-frame.component.html`,
a new "Notices" `nav-group` next to its existing "Manage"/"Administration"
groups), rendered inside paperless-ngx's own shell — its own branding,
its own dark-navy top bar, its own collapse/slim-sidebar behavior. The
`src-ui/src/app/rentshield/` directory that remains holds only the page
*components* those sidebar links route to, as plain children of
paperless-ngx's own `AppFrameComponent` route (not a separate route tree
with its own frame). They talk **only to paperless-ngx's own stock REST
API** — `/api/documents/`, `/api/tags/`, `/api/custom_fields/`,
`/api/tasks/` — plus the thin `documents/notice/*` endpoints described
above; there is no rentshield-specific data API to keep in sync with a
separate backend contract.

```
notice-form/            Single-page "Generate Notice" form — fields +
                        a Generate button, no step indicator, no live
                        preview panel, no watermark. Submitting renders
                        a real PDF and dispatches it into paperless-ngx's
                        async consumption pipeline (POST .../notice/create/
                        returns a Celery task id), then polls paperless-
                        ngx's own GET /api/tasks/?task_id=... until it
                        resolves into the created Document's id. On
                        success, links straight to that Document's own
                        paperless-ngx detail page (/documents/<id>) —
                        there is no separate RentShield notice-detail page.
notices-list/           Table of every saved notice (with total/
                        statutory/breach/AI-reviewed stat cards above it),
                        listed via paperless-ngx's own
                        GET /api/documents/?tags__id__in=<tag_id> and
                        mapped from each Document's custom_fields array
                        — not a RentShield-specific list endpoint.
legal-skills/           Master-detail browser over the ported
                        legacy-v1/mcp/skills/ Markdown library — the one
                        piece of UI with no paperless-ngx equivalent to
                        fold into.
services/rentshield-api.service.ts   Typed HTTP client wrapping
                        paperless-ngx's stock documents/tags/custom_fields/
                        tasks endpoints plus the documents/notice/*
                        endpoints — including the CustomField id ↔ short-
                        key mapping and the Document → Notice-shaped
                        client-side view model every component reads.
```

A generated notice is, deliberately, not distinguishable in the UI from
any other paperless-ngx document: open it from the Notices table or from
`/documents/<id>` directly and you get paperless-ngx's own document
detail page — the real rendered PDF, the `RentShield Notice` tag, and
every notice field as a native, editable paperless-ngx custom field
(`RentShield: Landlord Name`, `RentShield: Reason`, ...) right there
alongside paperless-ngx's own Title/Correspondent/Document type/Tags
fields, editable the same way.

**Verified end-to-end in a real browser** (Playwright against a live
`ng serve` + `manage.py runserver` + `celery worker`, not just "should
work"): confirmed the root URL redirects to paperless-ngx's own
`/dashboard` (not a RentShield-branded landing page); confirmed the
sidebar's new "Notices" group renders inside paperless-ngx's real shell
with no leftover "Rent Shield"/"RERA · DLD Compliant" branding anywhere;
filled out the single-page form for a statutory (Demolition) notice and
confirmed Generate correctly waits through the real async create → Celery
consume → poll-until-resolved sequence before showing "Notice #N
generated"; followed its "Open in Documents" link and confirmed
paperless-ngx's own document detail page shows the real rendered PDF plus
every RentShield field as a native, editable custom field; and confirmed
Notices and Legal Skills both render correctly inside paperless-ngx's
shell with matching screenshots.

Non-obvious bugs hit and fixed along the way (kept here since they're
easy to reintroduce):
- A `computed(() => this.form.valid)` never re-evaluates because
  `FormGroup.valid` is a plain getter, not a tracked Signal — both the
  old wizard and the current form use a real `signal()` kept in sync via
  `form.statusChanges`/`valueChanges` instead.
- An uncaught error thrown inside a `toSignal()`'d `router.events`
  subscription (from walking a freshly-injected `ActivatedRoute` before
  its tree was populated) silently broke the Router's own child-route
  activation, leaving nested `<router-outlet>` content blank — fixed by
  reading `router.routerState.snapshot.root` instead. (This was in the
  now-deleted `RentshieldFrameComponent`; recorded here as a general
  Angular Signals/Router gotcha, not because that component still exists.)
- A filename-sanitization bug in `documents/rentshield/service.py`:
  `DocumentMetadataOverrides.filename` was built from an unsanitized
  reason label, so a reason containing `/` ("Personal Use / Recovery")
  broke paperless-ngx's own consumer when it tried to build a working-
  copy path from that raw filename — fixed by sanitizing once, before
  the name is used anywhere, not sanitizing only the temp file's own
  path and reusing the raw string for `DocumentMetadataOverrides`.

### Running the frontend dev server

`ng serve` (via `pnpm start` in `src-ui/`) runs against Django on a
different origin (`:4200` vs `:8000`), which needs three things paperless-
ngx's own dev docs don't call out for this project's auth path:

```bash
# Django must run with DEBUG on — paperless-ngx only allowlists
# http://localhost:4200 in CORS_ALLOWED_ORIGINS when DEBUG=True
export PAPERLESS_DEBUG=true

# At least one is_staff user must exist — paperless's
# AngularApiAuthenticationOverride (DEBUG-only, Referer-checked dev auth)
# does `User.objects.filter(is_staff=True).first()` and 500s on None
uv run manage.py createsuperuser

# Do NOT set PAPERLESS_AUTO_LOGIN_USERNAME for this dev path — it swaps
# in AutoLoginMiddleware, which establishes a real Django session, which
# makes DRF's SessionAuthentication the active authenticator, which
# enforces CSRF — and no CSRF cookie is ever set because Angular is
# served by vite, not Django's own @ensure_csrf_cookie IndexView.

cd src-ui && pnpm install && pnpm start   # http://localhost:4200
```

## Workflows

`manage.py create_rentshield_workflows` idempotently creates 12 paperless-ngx
native Workflows (`documents/management/commands/create_rentshield_workflows.py`)
built entirely on paperless-ngx's own Workflow engine (Manage > Workflows) —
no custom trigger code. Safe to re-run; skips anything already created by
name, so edits made afterward in the UI aren't clobbered.

1. **Statutory expiry reminder** — scheduled off `RentShield: Notice Date`
   + 335 days, statutory reasons only. Alerts staff that a 12-month notice's
   legal period is closing.
2. **Breach deadline reminder** — same idea, +25 days, breach reasons only.
3. **Notarization requested, not dispatched** — fires on notice creation
   when the notarization add-on is set but no e-sign status exists yet.
4. **Notarization stalled** — same condition, recurring every 2 days, so a
   stuck request keeps getting flagged instead of alerting once and going
   quiet.
5. **File into a Tenancy Notices storage path** — keeps generated notices
   out of the general document inbox.
6. **AI-review queue tag** — tags notices that requested the AI Compliance
   Review add-on with `Needs AI Review`, turning a buried boolean field into
   an actual filterable queue.
7/8. **Document-type split** — tags statutory vs. breach notices with a real
   paperless-ngx Document Type, so the built-in type filter is useful here.
9. **Notify an external tool** — webhook on every new notice, for syncing
   into a CRM or other external system (see Twenty CRM integration below).
10. **Restrict sensitive notices** — Personal Use/Recovery and Demolition/
    Renovation notices (real legal exposure if mishandled) get view/change
    permissions limited to a `Lawyer` group.
11/12. **AI review on upload** — fires the real AI Compliance Review
    pipeline (see below) automatically on any document uploaded through
    paperless-ngx's own uploader with "contract" in the filename or
    tagged `Tenancy Contract` — no custom UI needed for this one at all.

**Real, load-bearing limitations, not glossed over:**
- Workflows #1, #2, #3, #4, and #9 are created **disabled**, with
  placeholder values (`changeme@example.com`, `https://example.com/rentshield-webhook`)
  — confirmed this via a real round trip through `GET /api/workflow_triggers/`
  and `/api/workflow_actions/`, not assumed. Edit them with real values under
  Manage > Workflows, then enable.
- paperless-ngx's own Workflow email/webhook templates only expose a fixed
  placeholder set (`title`, `doc_url`, `doc_id`, `added`, `created`,
  `correspondent`, `document_type`, `owner_username`, `filename` —
  `documents/templating/workflows.py`'s `_known_placeholder_names`) —
  **custom field values are not available in those templates.** A workflow
  can't put the landlord's name or the actual reason into an email body
  directly; the receiving system should call
  `GET /api/documents/<doc_id>/` with the id the webhook/email gives it to
  get the full RentShield custom-field data.
- Email workflows do nothing until paperless-ngx's own `PAPERLESS_EMAIL_*`
  settings are configured (`settings.EMAIL_ENABLED` gates it entirely).
- Workflow #10's `Lawyer` group is created with no members and no
  object-level permissions configured beyond what the workflow itself
  grants — it's a minimal placeholder for the role-based permissions work
  described below, not a finished access-control setup.
- Workflows #11/#12's webhook is `settings.RENTSHIELD_INTERNAL_URL`
  (default `http://localhost:8000`, env var
  `PAPERLESS_RENTSHIELD_INTERNAL_URL`) — this Django process calling
  *itself* from its own Celery worker. Correct for a single-host dev
  setup; in docker-compose/production, where the worker and web process
  may not both resolve `localhost` to the same container, set that env
  var and re-run `create_rentshield_workflows` (it only creates
  workflows that don't already exist by name — delete the two AI-review
  ones first if you need to change an already-created URL).
- **Bug found and fixed while building demo data**: workflows #3/#4's
  "notarization requested, not dispatched" condition originally used
  `esign_status: isnull True` to mean "notarization was requested but no
  e-sign status exists yet." That's not what `isnull` means in
  paperless-ngx's custom-field-query DSL — it only matches a
  `CustomFieldInstance` row whose value column is SQL NULL, which
  `request_notarization()` never produces (it only ever writes a real
  status string). A notice that never had notarization requested has no
  `esign_status` instance row *at all*, so the query silently matched
  zero documents, always — confirmed by creating a real un-notarized demo
  notice and getting 0 back instead of 1. Fixed to use `exists: False`
  (`documents/filters.py`'s `CustomFieldQueryParser`, `"basic"` category),
  which correctly means "this custom field was never set on this
  document." Re-running `create_rentshield_workflows` now also repairs
  any already-created workflow whose trigger still carries the old,
  broken query (matches by exact old value, so a real edit made
  afterward in the UI is left alone).

## Dashboards

`manage.py create_rentshield_dashboards` idempotently creates 8 paperless-ngx
native Saved Views (`documents/management/commands/create_rentshield_dashboards.py`)
and pins them to show on the Dashboard (and in the sidebar) for every existing
superuser — paperless-ngx's own dashboard-widget mechanism (Manage > Saved
Views), no custom dashboard UI or bespoke stats endpoint. Each one is a real,
live filter over the same custom fields and tags the notice form and
workflows already write, so the numbers move as notices/contracts come in —
not a static count.

1. **All Notices** — every document tagged `RentShield Notice`. The top-level
   "how many notices exist" view.
2. **Statutory Notices (365-day)** — reason in sale/personal/demolition/
   renovation, the notices with the 12-month legal runway.
3. **Breach Notices (30-day)** — reason in nonpayment/sublease, the ones on
   the tight legal clock.
4. **Notarization Pending** — notarization add-on requested but no e-sign
   status recorded yet; the queue of requests that haven't actually been
   dispatched.
5. **Sensitive Notices (Legal Review)** — personal use/demolition/
   renovation, the same set Workflow #10 restricts to the `Lawyer` group;
   surfaced here so legal staff have one place to see what they're
   responsible for.
6. **Needs AI Review** — tagged `Needs AI Review` by Workflow #6; the queue
   the AI Compliance Review pipeline hasn't processed yet.
7. **Contracts Under Review** — tagged `Tenancy Contract` but not yet
   `AI-Reviewed`; uploaded contracts still waiting on Workflows #11/#12 to
   pick them up.
8. **Non-Compliant Contracts** — `RentShield: AI Review Findings Count` >= 1;
   the actual output of the AI review pipeline, not just that it ran.

Verified end-to-end, not just unit-level: created all 8 via the management
command, confirmed each view's stored `filter_rules` produces the correct,
distinct document set by replaying the equivalent `custom_field_query`
directly against `/api/documents/`, then loaded paperless-ngx's own
`/dashboard` page in a real browser and confirmed all 8 widgets render with
the correct titles, tags, and counts (screenshot: All Notices 4, Breach
Notices 1, Non-Compliant Contracts 2 with the two actually-flagged test
contracts, Statutory Notices 3, Sensitive Notices 2).

**Real, load-bearing limitations, not glossed over:**
- Dashboard/sidebar visibility is a **per-user preference**
  (`UiSettings.settings.saved_views.dashboard_views_visible_ids`/
  `sidebar_views_visible_ids`), not a field on the Saved View itself —
  confirmed by reading the `SavedViewSerializer`, where
  `show_on_dashboard`/`show_in_sidebar` are only populated for legacy API
  versions (< 10); the real, current source of truth is
  `GET /api/ui_settings/`. The command only pins these 8 views for accounts
  that are already superusers at the time it runs — any account created
  later (including the tenant/notary/lawyer/owner roles from the
  permissions work below) needs the same pinning done for it, or a user can
  star/unstar any Saved View themselves from the sidebar.
- There is no `?view_id=` document-filtering parameter in the backend —
  paperless-ngx's Angular UI resolves a Saved View into the equivalent
  direct query params (`custom_field_query`, `tags__id__in`, etc.)
  client-side. Verifying a view's correctness means replaying that
  equivalent query directly, not querying by view id.
- Re-running the command is safe: it skips any view that already exists by
  name, and only *adds* newly-created view ids to a user's dashboard/sidebar
  list — it won't re-add a view a user deliberately unpinned.
- "Notarization Pending" shared the `isnull`-vs-`exists` bug described in
  the Workflows section above (it used the same query helper) — it showed
  0 in the original screenshot only because there was no genuinely-pending
  notice to test against yet. Fixed the same way; re-running
  `create_rentshield_dashboards` also repairs an already-created view's
  filter rule if it still carries the old, broken query.

## Demo Data

`manage.py create_rentshield_demo_data` idempotently seeds 8 realistic
(fictitious) notices and 3 uploaded tenancy contracts
(`documents/management/commands/create_rentshield_demo_data.py`) — so a new
install, or a prospective user clicking through the self-guided tour, sees a
platform that already has real data in it instead of an empty shell. Every
document is created through the same code real usage goes through
(`documents.rentshield.service.generate_and_consume`/`run_ai_review`,
paperless-ngx's own consumption pipeline) — there is no seed-only shortcut
that writes rows directly, so the demo data also exercises the Workflow
engine's `DOCUMENT_ADDED` triggers exactly like a real upload would.

The 8 notices span every statutory and breach reason, with a deliberate mix
of add-ons so every dashboard widget has something to show: 3 have the
notarization add-on requested but not yet dispatched, 2 are tagged `Needs AI
Review`. Of the 3 contracts, one is written to fail AI review (a 7-day
notice-period clause, well short of the 365-day statutory minimum, plus a
verbal-notice service-method mention), one is written to pass cleanly (a
365-day clause via registered mail), and the third is deliberately left
un-reviewed — its filename avoids "contract" and its `Tenancy Contract` tag
is applied only after consumption, so neither AI-review-on-upload workflow's
`DOCUMENT_ADDED` trigger catches it — to show a genuine, non-empty
"Contracts Under Review" queue.

Verified end-to-end: ran the command against the real dev stack (Django +
Celery + docling-service all live), confirmed the correct tags/custom-field
values landed on every document, and re-loaded the Dashboard in a real
browser — all 8 widgets showed correct, non-zero, mutually-consistent counts
(this is also how the `isnull`/`exists` bug above was actually found: a
demo notice with notarization requested and no e-sign status yet was the
first real "genuinely pending" case this project had ever created).

**Real, load-bearing limitations, not glossed over:**
- Building the notices calls `generate_and_consume(..., synchronous=True)`
  — a new parameter added specifically for this command
  (`documents/rentshield/service.py`) that calls paperless-ngx's own
  `consume_file` task in-process instead of dispatching it through Celery,
  so the command works even with no worker running and gets the created
  `Document` back immediately instead of a task id to poll. The API view
  used by the real notice-generation form is unaffected — it still
  dispatches via Celery, as it always has.
- AI-reviewing the 2 contracts calls `run_ai_review()` directly and
  requires docling-service to be reachable; if it isn't, the command
  degrades gracefully (creates the documents, prints a warning, leaves
  them tagged `Tenancy Contract` only) rather than failing outright.
- Idempotency here is coarser than the other commands: it checks for the
  existence of a `Demo Data` tag at all, not per-document. Re-running after
  a partial failure without first deleting anything tagged `Demo Data`
  will skip entirely rather than filling in what's missing.
- If a Celery worker is running when this command runs, the real
  `DOCUMENT_ADDED` workflows (storage path assignment, document-type
  tagging, the notarization-pending webhook, etc.) also fire on these
  documents asynchronously, same as any real upload — the two contracts
  meant to demonstrate the AI-review pipeline get reviewed twice (once
  synchronously by this command, once again by the async webhook); both
  writes are idempotent so this is harmless, just redundant.

## Roles & Permissions

`manage.py create_rentshield_roles` idempotently creates 4 role Groups —
Tenant, Property Owner, Notary, Lawyer — with real, model-level Django
Document permissions (`documents/rentshield/roles.py`,
`documents/management/commands/create_rentshield_roles.py`). There is no
custom roles/permissions framework: these are plain `django.contrib.auth.
Group` objects, the exact same mechanism paperless-ngx's own Settings >
Users & Groups admin UI already manages, given real permissions instead of
being left as an empty placeholder. The 5th role, full-access Admin, is
just Django's own `is_staff`/`is_superuser` — not a group at all, since
paperless-ngx (and Django itself) already treats a superuser as
unrestricted everywhere; a separate "Admin" group would only be a second,
weaker notion of admin alongside the real one.

Every `documents/rentshield_views.py` endpoint that creates or dispatches a
real legal document now requires real auth instead of `AllowAny`:
- `create_notice_view` / `analyze_document_view`: require `CanManageNotices`
  (`documents/rentshield/roles.py`) — Django's own `documents.add_document`
  permission, i.e. the same "Add" checkbox under Document in Settings >
  Users & Groups (or on an individual user) that an admin already sees and
  edits — not a hidden rule checking group membership by name. A notice's
  `owner` is now always the authenticated requester (paperless-ngx's own
  `Document.owner` field), never `None`.
- `notarize_view`: requires `CanActOnDocument` — Django's own
  `documents.change_document` permission, since dispatching notarization
  modifies an existing document rather than creating a new one.
- `notarize_status_view`: any authenticated user who can already *see* the
  document (owns it, or has a Workflow-granted object permission, or is
  Admin) — read-only, so not limited to `CanManageNotices`.
- `legal_skills_view` / `legal_skill_detail_view` / `check_service_method_view`:
  any authenticated user — informational reference content, not gated by
  role.
- `analyze_uploaded_view` stays `AllowAny`, on purpose: it's the internal
  server-to-server webhook callback Workflows #11/#12 hit
  (`settings.RENTSHIELD_INTERNAL_URL`), not a human-facing endpoint — see
  its own docstring.

**Which specific documents a role's members see is narrowed per-document,
not just per-model**, reusing paperless-ngx's existing guardian-backed
object permissions (`documents/permissions.py`) rather than anything new:
- **Property Owner**: sees the notices they personally generated
  (`Document.owner`, paperless-ngx's own ownership model) — one Property
  Owner cannot see another's notices, verified directly (a second Property
  Owner account got `404` on the first owner's notice, `200` creating
  their own).
- **Notary**: sees a notice only once notarization is actually requested
  on it — granted by the new Workflow #13, "RentShield: grant Notary
  access on notarization request" (`DOCUMENT_ADDED`, `add_notarization`
  exact `True` → `assign_view_groups`/`assign_change_groups` on the Notary
  group), the exact same mechanism Workflow #10 already used for Lawyer.
- **Lawyer**: sees only sensitive-reason notices (personal use, demolition,
  renovation) — Workflow #10, unchanged, now paired with real model-level
  permissions on the Lawyer group (see the bug note below).
- **Tenant**: gets `view_document` at the model level, but **no automatic
  per-notice visibility** — `tenant_name` on a notice is free text, not a
  link to a real user account, so there's no way to know which Tenant user
  a given notice belongs to without a bigger schema change (named here, not
  silently skipped). A Tenant sees nothing until an admin manually grants
  them view access to their specific notice(s) (Documents > select > Edit
  permissions in paperless-ngx's own UI).

Verified end-to-end with 4 real test users (one per role, `force_login`'d
through Django's real request/response cycle, not mocked) plus a second
Property Owner account: `create_notice_view` returned `200` only for the
Property Owner and `403` for Tenant/Notary/Lawyer; after the Property Owner
created a notarization-requested notice and a sensitive-reason notice, the
Notary could `GET` the former (`200`) but not the latter (`404`), the
Lawyer the reverse, and the Tenant neither — exactly the intended matrix.

The Angular frontend gates on the same real permissions, not a separate
check: "New Notice" (`app-frame.component.html`) and its route
(`app-routing.module.ts`) require `Add`/`Document`; "Notices" and "Legal
Skills" require `View`/`Document` — both via paperless-ngx's own existing
`*pngxIfPermissions` directive and `PermissionsGuard`, the same mechanism
already gating every other nav item, not a bespoke role check.

**Bug found and fixed while verifying this**: the `Lawyer` group (created
as an empty placeholder by `create_rentshield_workflows.py` back in task
1) had never been given model-level Document permissions — only the
object-level grant from Workflow #10. `create_rentshield_roles` fixes this
(and will heal it again if the group's permissions are ever edited into an
inconsistent state, since it always sets the group's permission set to
exactly what's defined in `roles.py` rather than only adding on first
creation).

**Second bug found and fixed, this time via real browser testing, not just
API-level automated checks**: every role group 403'd on `GET
/api/ui_settings/` — the very first API call paperless-ngx's own Angular
app makes on every single page load, before it even knows what permissions
the logged-in user has (so it can't itself be gated behind a permission
check). It requires the plain Django model-level `view_uisettings`/
`change_uisettings` permissions, which `create_rentshield_roles` only ever
granted for Document, never for `UiSettings` — meaning the app shell never
even finished loading for a Tenant/Property Owner/Notary/Lawyer account. The
automated verification described above never caught this because it drove
specific endpoints directly via Django's test client rather than actually
booting the Angular app as one of these roles. Fixed by adding
`BASELINE_PERMISSIONS` (`documents/rentshield/roles.py`) — granted to every
role group alongside its Document permissions — and re-verified via a real
logged-in request to `/api/ui_settings/` returning `200` instead of `403`.

**Third bug found and fixed, same way**: after fixing the above, a real
Lawyer-group account logging in still saw zero notices under "Notices" —
including ones with a sensitive reason, which should have been visible.
Root cause: Workflow #10's object-level grant only ever fires at
`DOCUMENT_ADDED` time, so any sensitive-reason notice consumed *before*
that Workflow existed (or before the Lawyer group had its permissions
fixed) never got the grant, and never will just because the Workflow
exists now — confirmed directly in this project's own sandbox, where
documents created early in this project had no Lawyer grant while ones
created later did. `create_rentshield_workflows` now also backfills this:
after creating/repairing the workflows themselves, it scans every
already-existing document for a sensitive reason or a notarization
request and grants the matching group's access via the exact same
`set_permissions_for_object()` call the Workflow action itself uses (see
`_backfill_object_permissions()`) — `merge=True`, so it only ever adds a
grant, never revokes one, and is safe to re-run. Re-running it in this
project's sandbox correctly backfilled the 2 sensitive-reason documents
that were missing it and left the rest untouched (0 backfilled on a
second run), and a real Lawyer-group API request went from seeing 0
sensitive notices to seeing all of them.

**Fourth bug found and fixed, by an admin actually using the real
permissions UI**: `CanManageNotices` originally checked group membership
directly (`user_in_group(user, PROPERTY_OWNER_GROUP_NAME)`) rather than an
actual Django permission. That meant Settings > Users & Groups' own
"Document > Add" checkbox — the exact control an admin would reach for to
grant someone notice-creation access — silently did nothing for any group
other than Property Owner: an admin ticking "Add" for Lawyer (confirmed by
doing exactly this) still got `403` on notice creation, because the check
never looked at that permission at all. The Angular frontend was never
wrong here — "New Notice" is (and always was) gated on the real
`Add`/`Document` permission via `*pngxIfPermissions`, so the nav link
correctly appeared while the backend silently refused the action, a
confusing split. Fixed by changing `can_manage_notices()`/
`CanManageNotices` to check `user.has_perm("documents.add_document")`
directly — the same permission the checkbox controls, and the same one
Django already treats a superuser as always having, so no separate staff/
superuser check is needed either. `notarize_view` was moved to a new
`CanActOnDocument` checking `documents.change_document` instead (dispatching
notarization modifies an existing document, so "Change," not "Add," is the
correct permission). Property Owner already has both by default, so
nothing changes for the out-of-the-box role; any other group or individual
user now genuinely gains notice-creation ability the moment "Add" is
ticked for them, with no code change required. Verified directly: a Lawyer
account with `add_document` manually granted went from `403` to `200` on
notice creation, and back to `403` once the permission was removed.

**Fifth bug found and fixed, same real-browser-testing pattern**: the
Notices list 403'd on `GET /api/tags/?name__iexact=RentShield%20Notice`
for every role — `rentshield-api.service.ts` resolves the "RentShield
Notice" tag's id this way to build its document-list filter, and
`BASELINE_PERMISSIONS` only covered `UiSettings`, never `Tag`. Added
`view_tag` to `BASELINE_PERMISSIONS`; tag *creation* on notice generation
was never affected, since that happens server-side via the ORM directly
in `documents/rentshield/service.py`, not through this API. Verified: a
real Lawyer-group request to that exact endpoint went from `403` to `200`.

**Real, load-bearing limitations, not glossed over:**
- No user is a member of any role group by default — an admin has to
  assign real users to Tenant/Property Owner/Notary/Lawyer under
  Settings > Users & Groups, based on who they actually are.
- The backfill only covers what `create_rentshield_workflows` already
  knows to grant (sensitive-reason → Lawyer, notarization-requested →
  Notary) — it's not a general "recompute every permission" tool. If you
  add a new Workflow-driven grant later, give it the same backfill
  treatment rather than assuming existing documents will pick it up.
- `reasons_view`/`pricing_view` (static reference data: the list of
  reasons, the price table) are intentionally left as plain, ungated Django
  views — no document data, nothing role-specific to protect.

## Landing Page

`GET /welcome/` is the one URL in this project deliberately **not** behind
paperless-ngx's `login_required` gate — a real public marketing page for
prospective users (`documents/rentshield_views.py`'s `landing_view`,
`documents/templates/rentshield/landing.html`), styled with paperless-ngx's
own static color tokens (`documents/static/base.css`'s `--pngx-primary:
#17541f` and friends — the exact same green as the app itself, not an
approximation) rather than Angular's SCSS pipeline.

**Why a Django template, not an Angular route**: the entire Angular app is
served through one view, `IndexView`, which is wrapped in Django's
`login_required` at the URL level (`paperless/urls.py`) — an anonymous
visitor hitting *any* path is redirected to `/accounts/login/` before
Angular ever bootstraps, so there was no way to add a public route inside
the SPA. `/welcome/` is registered as its own URL pattern, ahead of the
Angular catch-all, so it's reachable without a login at all — confirmed by
requesting `/` while logged out and getting a real `302` to
`/accounts/login/?next=/`, while `/welcome/` itself returns `200`.

The page's content is all real: the reason chips in the hero's mock
"Generate a Notice" panel and the pricing cards are rendered from
`documents/rentshield/constants.py`/`pricing.py` (the same values the real
notice form and pricing endpoint use), and the "Applicable Law" section
quotes the same statute citations (`Law No. (33) of 2008`, Article 25(1)/
(2)/(3), RERA) already used throughout `notice_builder.py` and the legal
skills library — nothing on this page asserts anything about UAE law that
isn't already backed elsewhere in this codebase. There are no fabricated
client logos, testimonials, or stats.

### Self-service signup, with a role chosen at registration

"Get Started"/"Log In" link to real paperless-ngx auth pages
(`/accounts/signup/`, `/accounts/login/`) — not a dead end. Signups are
open by default for RentShield specifically (`ACCOUNT_ALLOW_SIGNUPS`
defaults to enabled in `paperless/settings/__init__.py`, unlike stock
paperless-ngx which defaults this closed — still overridable via
`PAPERLESS_ACCOUNT_ALLOW_SIGNUPS` for anyone who wants to lock it down).

The signup form itself has one RentShield-specific addition: an "I am a"
choice between **Property Owner** and **Tenant**
(`documents/rentshield/forms.py`'s `RentShieldSignupExtra`, wired in via
django-allauth's own `ACCOUNT_SIGNUP_FORM_CLASS` extension point — not a
custom auth flow). Whichever the new user picks, they're added to the
matching real Django Group (see Roles & Permissions above) the moment
their account is created. Notary and Lawyer are deliberately **not**
self-service choices here — those represent a vetted real-world
relationship (a licensed notary, a retained lawyer) an admin assigns under
Settings > Users & Groups, not something anyone can declare about
themselves at signup.

The "Generate Notice" button in the hero opens an in-page modal
(`rsAuthModal` in `landing.html`, plain CSS/vanilla JS, no framework)
rather than leaving the page: pick a role first, then a Sign Up/Log In tab
pair with real form fields. These aren't a fake preview — the forms POST
directly to paperless-ngx's own `/accounts/signup/`/`/accounts/login/`
endpoints (same field names, same CSRF token, rendered from the same
Django template as the real account pages) and create real accounts.

Verified end-to-end, not just visually: a real Playwright browser session
clicked "Generate Notice," chose "Property Owner," filled in the signup
form, submitted it, and the resulting account was confirmed server-side to
exist with the correct email and — critically — actually assigned to the
**Property Owner** Django group, not just created.

**Real, load-bearing limitations, not glossed over:**
- The page is static per-request (Django template context, not live data)
  — pricing/reasons update automatically if `pricing.py`/`constants.py`
  change, but nothing on it reflects a specific user's account.
- Validation errors on the modal's forms (e.g. a taken username, a
  password mismatch) redirect the browser to the real, full
  `/accounts/signup/`/`/accounts/login/` page to show the error, rather
  than showing it inline in the modal — a real UX rough edge, not
  pretended away. Inline validation would need either a JS-driven
  fetch/AJAX submit or server-rendered partial re-render of the modal,
  neither attempted here.
- In this project's local *split* dev setup (Django on port 8000, the
  Angular dev server separately on port 4200, no proxy stitching them into
  one origin) a successful signup/login redirects back to port 8000's own
  copy of `index.html`, which doesn't render correctly there since the
  Angular bundle is only served by `ng serve` on port 4200, not collected
  as static files on 8000. This is a real, known friction point for local
  testing (not a bug in the signup/login flow itself, and not present in a
  real single-origin deployment) — after registering/logging in locally,
  manually navigate to `http://localhost:4200/dashboard` to actually use
  the app.

## Interactive Product Tour

RentShield's onboarding walkthrough extends paperless-ngx's own existing
guided tour (`ngx-ui-tour-ng-bootstrap`, already a dependency, already
wired up in `app.component.ts`/`.html` for the stock app) rather than
adding a second tour mechanism. It's one continuous, 20-step tour: Dashboard
→ RentShield's dashboard widgets → generate a notice (reason picker,
add-ons) → the Notices list (stats, table) → Legal Skills → then straight
into paperless-ngx's own stock steps (Documents, filters, Saved Views,
Tags, Mail, Workflows, Tasks, Settings) → outro. Same "Start tour" entry
points as stock paperless-ngx: the welcome widget on an empty dashboard, or
the permanent button under Settings.

Each step is a real popover (`ngb-popover-window`) anchored to a real
element via the `tourAnchor` directive, with a spotlight cutout in a
backdrop over the rest of the page — not a custom overlay of our own.
RentShield's new anchors live in `app-frame.component.html` (the "New
Notice"/"Notices"/"Legal Skills" nav items, on the `<li>` wrapper, matching
the stock nav-item anchors) and inside `notice-form`, `notices-list`, and
`legal-skills` components' own templates (the reason picker, add-ons
section, stat cards, notice table, skills list). The new steps themselves
live in the same array as the stock ones, in `app.component.ts`.

**Bugs found and fixed while building this** (both real, both would have
made new anchors silently non-functional or broken the *whole* tour):
- The 3 new page-level components (`notice-form`, `notices-list`,
  `legal-skills`) are standalone Angular components that never imported
  anything tour-related — `tourAnchor` was inert on them: the attribute
  rendered in the DOM (confirmed via a direct DOM check) but
  `TourAnchorNgBootstrapDirective` was never actually applied, so the
  anchor never registered with `TourService` at all. Fixed by adding
  `TourNgBootstrap` (the directive bundle export, same as `app.component.ts`
  already uses) to each component's own `imports` array.
- The first version of the 3 new nav-item anchors was placed on the `<a>`
  tag itself — which already carries its own `ngbPopover` for the
  slim-sidebar hover tooltip. Every *existing* stock nav-item anchor
  (`tour.tags`, `tour.mail`, `tour.workflows`, `tour.settings`,
  `tour.file-tasks`) is on the parent `<li>`, specifically avoiding that
  same element. Because `ngx-ui-tour-core`'s anchor registry throws on a
  genuinely duplicate `anchorId` but silently does nothing useful when a
  tour step's target anchor is present-but-non-interactive this way, the
  step just... never showed a popover, and because it wasn't marked
  `isOptional`, the *entire tour silently ended* the moment it reached that
  step — found by reading `ngx-ui-tour-core`'s actual `showStep()`/
  `register()` source in `node_modules` after black-box testing gave no
  console error to go on. Fixed by moving the anchor to the `<li>`, matching
  the stock pattern exactly.

Verified end-to-end: a real Playwright run started the tour, clicked
"Next" through all 20 steps, and logged each step's URL and popover text —
every RentShield step landed on the right page with the right content, in
order, with zero anchor-registration warnings, flowing seamlessly into the
unmodified stock steps through to the outro.

**Real, load-bearing limitations, not glossed over:**
- Several RentShield steps are `isOptional: true` (skipped, not shown, if
  their anchor isn't in the DOM) — the "New Notice" nav item only exists
  for a user with `add_document` permission (see Roles & Permissions
  above), so an account without it (an admin can still remove that
  permission from anyone, including Property Owner) won't see that step;
  this is intentional, not a bug, and mirrors how the stock tour already
  treats `tour.tags`/`tour.mail`/etc. as effectively permission-gated
  (their anchors are behind the same `*pngxIfPermissions` checks). This
  was more load-bearing back when Tenant/Notary/Lawyer were separate,
  more-restricted self/admin-assignable roles (see the dated "Roles
  simplified" section below) — with only Property Owner and Admin left,
  it's now an edge case rather than the common path.

## Roles simplified: 4 login roles down to 2 (2026-09-04)

**What existed before**: Tenant, Property Owner, Notary, and Lawyer as
separate self/admin-assignable Groups (see "Roles & Permissions" above),
alongside full-access Admin (Django's own `is_staff`/`is_superuser`).

**Why cut, role by role** (a decision made after reviewing how each role
actually got used and bugged out during testing, not a guess):
- **Tenant** delivered no working value: `tenant_name` on a notice is
  free text, not linked to a real user account, so a self-registered
  Tenant saw a permanently empty Notices list — dead weight with a
  signup form and a permission set behind it.
- **Notary** duplicated what the DocuSeal/OpenSign e-signature
  integration already automates end to end (see "What's in
  `documents/rentshield/`" above) — there was never a real task for a
  separate human "Notary" login to do inside the app.
- **Lawyer** had real, narrow value (flagging sensitive-reason notices
  for review), but its group-permission/object-grant machinery was this
  project's single biggest source of real bugs — the `isnull`-vs-`exists`
  query bug, the `UiSettings` 403, the retroactive-grant backfill, and
  the `CanManageNotices`-checks-group-membership bug documented under
  "Roles & Permissions" above all trace back to this one role's
  object-permission layer.
- **Property Owner** is the only role that ever delivered real,
  self-evident value (generate a notice, see the notices you made) and
  is the only one that should be a paying customer.

**Decision**: collapse to 2 account types — Property Owner (self-service
signup) and Admin (`createsuperuser`/Django admin only, unchanged).
Lawyer's one real use, legal review, became a priced add-on instead of a
role — same shape as the existing Notarization/AI Review add-ons
(`documents/rentshield/pricing.py`'s `ADD_ONS["legal_review"]`, 349 AED),
fulfilled operationally rather than through in-app RBAC: ticking it at
notice-creation time (`create_notice_view`'s `add_legal_review`) tags the
resulting Document `Legal Review Requested` (created the same
`get_or_create`-by-name way as every other RentShield tag) and sends a
plain email to `settings.RENTSHIELD_LEGAL_REVIEW_NOTIFY_EMAIL`
(`PAPERLESS_RENTSHIELD_LEGAL_REVIEW_NOTIFY_EMAIL`, empty/no-op by
default — notice creation never fails just because this isn't
configured; a send failure is logged and swallowed, not raised). An
admin filters Documents by that tag and loops in counsel outside the
app — no new Group, no object-permission grant, no separate login.

**What was removed, concretely**: `TENANT_GROUP_NAME`/
`NOTARY_GROUP_NAME`/`LAWYER_GROUP_NAME` and their
`ROLE_DOCUMENT_PERMISSIONS` entries (`documents/rentshield/roles.py`);
Workflow "RentShield: restrict sensitive notices" and Workflow
"RentShield: grant Notary access on notarization request", along with
the `_backfill_object_permissions()` method those two workflows' object
grants relied on (`create_rentshield_workflows.py` — nothing else called
it, so it was deleted rather than left dead); the role radio-buttons in
the self-service signup form and its landing-page auth-modal role-chooser
step (`documents/rentshield/forms.py`'s `RentShieldSignupExtra`,
`templates/account/signup.html`, `templates/rentshield/landing.html`'s
`#rsAuthModal` — every self-serve signup now joins Property Owner
unconditionally, with no user choice, per `RentShieldSignupExtra.signup()`).
The landing page's public "Who it's for" section was also trimmed from 5
role cards to 2, since leaving Tenant/Notary/Lawyer advertised there
would have been actively misleading about what a visitor can actually
sign up as.

**What's explicitly NOT done, on purpose**:
- **No destructive migration.** Any Tenant/Notary/Lawyer Group row that
  already existed in a database, and any user's membership in one, is
  left exactly as it was — `create_rentshield_roles`/
  `create_rentshield_workflows` simply stop creating or repairing them
  going forward. A test account like `lawyer` still logs in fine and
  keeps whatever stale Document permissions that group happens to carry;
  harmless, since no view or workflow gates on group membership by name
  any more, only on the plain Django `add_document`/`change_document`
  permission itself (`can_manage_notices()`/`can_act_on_document()` in
  `roles.py`, unchanged by this cut).
- **The pay-per-notice flow itself is untouched** — Notarization and AI
  Review add-ons, the notarization review-gate pipeline (Pending Review →
  Being Notarized → Notarized/Notarization Failed), and every dashboard/
  workflow not tied to Tenant/Notary/Lawyer all work exactly as before.
- Verified for real, not just read: ran `create_rentshield_roles` and
  `create_rentshield_workflows` against this project's own dev database
  and confirmed only the Property Owner group was created/repaired (no
  Tenant/Notary/Lawyer group creation attempted); generated a real notice
  as a Property Owner test account with Legal Review checked and
  confirmed the `Legal Review Requested` tag landed on the resulting
  Document; confirmed the existing `lawyer` test account still
  authenticates with no error anywhere in the stack, despite its now-
  unmaintained group membership.

## Mobile responsiveness audited and fixed (2026-09-07)

**Audited first, per explicit instruction not to assume anything was
broken** — every page/component was loaded via real Chromium (Playwright,
headless, not just reasoning about CSS) at 375px (iPhone SE), 393px
(iPhone 14/15), and 412px (common Android), checking actual
`document.documentElement.scrollWidth` vs. `window.innerWidth` for
horizontal overflow, not just eyeballing screenshots.

**What was actually broken — one real bug, and it was worse than
expected**: `/welcome/`'s top nav bar (`documents/templates/rentshield/
landing.html`'s `.rs-nav-links`/`.rs-nav-cta`) had **zero** responsive
handling — no `@media` query at all, unlike every other section on the
page (`.rs-hero-grid`, `.rs-steps`, `.rs-role-grid`, `.rs-pricing-grid`,
`.rs-security-grid`, and `.rs-footer-grid` all already had correct
stacking breakpoints from when the page was first built). Brand + 4 nav
links + Log In + Get Started in one un-wrapping flex row forced the
*entire page* to 543px wide on a 375px viewport (168px of horizontal
overflow, confirmed by measurement, not estimated) — every section below
the fold inherited that overflow even though their own grids were
already correctly responsive.

**Fixed**: added a hamburger toggle (`#rsNavToggleBtn`/`#rsNavMenu`),
plain CSS + vanilla JS matching this file's existing style (no new
framework/dependency) — below 768px, links + Log In/Get Started collapse
into a full-width dropdown panel instead of squeezing into one row.
Verified: 0px overflow at 375/393/412px both with the menu closed and
open, 0px overflow at 1280px desktop with the nav visually unchanged
(confirmed via screenshot diff, not assumed from the CSS alone).

**What was checked and found already correct — not rebuilt, per
instruction**: the `#rsAuthModal` signup/login modal already used
`width: 100%; max-width: 26rem` with `overflow-y: auto` (never clips on
a narrow screen); every signup/login `<input>` already computes to
16px via Bootstrap's own `.form-control` (no iOS auto-zoom risk, already
true before this audit); the `notice-form`, `notices-list`, and
`legal-skills` Angular components all already used Bootstrap's
`col-md-*`/`col-6 col-md-3` grid classes, meaning every field/stat
card/checkbox already stacked to a single column below `768px` with no
code change needed; `notices-list`'s table was already wrapped in
Bootstrap's own `.table-responsive` (contained horizontal scroll on the
table only, never the page — exactly the pattern paperless-ngx's own
stock document list uses, already followed here). paperless-ngx's own
frame (hamburger sidebar), dashboard widgets, document card grid, and
document detail view were all confirmed already fully responsive by
loading them for real, not assumed from paperless-ngx's reputation as a
mature app.

**Sanity swept, not just spot-checked**: grepped `landing.html` and
every `src-ui/src/app/rentshield/**/*.scss` file for fixed `width`/
`min-width` in pixels and for `white-space: nowrap` outside a
scrollable container — no hits beyond `max-width` caps already paired
with `margin: 0 auto` (never forces overflow) or an existing responsive
override.

**Real, load-bearing limitation, not glossed over**: this was verified
via browser *emulation* (Playwright/Chromium device-size viewports), not
an actual physical iPhone or Android handset — the agent doing this work
has no physical device to test on. Real-device confirmation (Safari's
own rendering quirks, actual on-screen-keyboard behavior, real touch
target accuracy) is still outstanding and needs to happen on real
hardware before treating this as fully closed.

## Real payment collection (demo mode) + honest add-on tier split (2026-09-09)

**Why**: before this, every notice generated in this project's entire
history was free -- `total_price_aed` was computed and stored on the
Document as a record, but nothing ever charged a card. Monetizing the
platform genuinely starts here, not with notarization automation (see
the notary-provider research below): no payment collection meant no
revenue regardless of how good the product was.

**What was built**: a new installed Django app,
`documents/rentshield_billing/` (`documents.rentshield_billing.apps.RentshieldBillingConfig`
in `INSTALLED_APPS`) -- a genuinely new app, not another plain
subpackage like `documents/rentshield/`, because an `Order` has to
exist *before* any Document does (payment happens before generation),
the same reasoning a future `MonitoredProperty`/`Subscription` model
will need.

- `Order` model: owner, the exact notice-creation payload it's for,
  `amount_aed`, `status` (pending/paid/demo_paid/failed/canceled),
  `stripe_checkout_session_id`, `document_id` (set once generation
  completes), `paid_at`.
- `stripe_client.py`: thin wrapper around the real `stripe` package
  (added as a project dependency, `stripe~=13.2.0`) -- Checkout Session
  creation and webhook signature verification, nothing more.
- `views.py`: `POST /api/documents/notice/checkout/` (creates the Order,
  then either a real Stripe Checkout redirect or, in demo mode,
  generates the notice synchronously and returns its id in the same
  response), `GET .../checkout/<id>/status/` (polled after a real-Stripe
  redirect returns), `POST /api/documents/notice/stripe-webhook/`
  (`AllowAny`, Stripe calls this server-to-server; rejects anything
  whose signature doesn't verify, same reasoning as
  `analyze_uploaded_view`'s own docstring).
- **Demo mode is not a separate code path bolted on** -- it's what
  `create_checkout_view` does automatically whenever `STRIPE_SECRET_KEY`
  is unset (`PAPERLESS_STRIPE_SECRET_KEY`, empty/no-op-safe by default,
  same pattern as every other optional integration in this project). No
  real charge happens; the Order is stamped `Status.DEMO_PAID`, never
  `PAID`, so a demo run can never be mistaken for real revenue later.
  This exists specifically so the whole pay-then-generate pipeline could
  be built, wired into the frontend, and verified end to end without
  waiting on a real Stripe account -- flipping it to real payments later
  needs only `PAPERLESS_STRIPE_SECRET_KEY`/`PAPERLESS_STRIPE_WEBHOOK_SECRET`
  set, no code change.
- The Angular notice-form's "Generate Notice" button is now "Pay &
  Generate Notice" and calls this checkout endpoint
  (`RentshieldApiService.checkout()`), not `create_notice_view`
  directly. `create_notice_view` itself is kept, unpaid, for direct/
  scripted use (demo data, tests) -- its validation logic was factored
  out into `validate_notice_fields()` so both paths share exactly the
  same rules, not two copies that can drift.
- The existing Pending Review -> Details Confirmed gate (see the AI
  Compliance Review / notarization sections above) needed no new code
  to sit in front of this: payment now happens *before* generation, and
  the confirmation gate still runs *after* generation, before any
  e-signature dispatch, exactly as before -- verified directly, not
  assumed, by checking a real paid demo order's resulting Document still
  picked up its `Pending Review` tag correctly.

**Add-on tier split (the other must-have from this pass)**: the
"Notarization Service" TODO flagged earlier in this README's history is
resolved, not silently decided. `documents/rentshield/pricing.py`'s
`ADD_ONS` key is renamed `notarization` -> `certified_esignature`, with
an honest label ("Certified E-Signature Service") and description that
no longer claims a licensed UAE notary -- because it still isn't one
(DocuSeal/OpenSign, unchanged). A second entry, `real_notarization`
("Real Notary Public (Coming Soon)", `available: False`), is listed but
not purchasable -- `validate_notice_fields()` rejects any request that
sets `add_real_notarization` with a clear "coming soon" error, matching
this project's docling-service/DeepSeek-OCR precedent of degrading
visibly rather than pretending to work. It exists at all because the
notary-provider research (this project's own live search, not guessed)
confirms no UAE notary currently exposes a third-party API -- see that
section below. Every other page that repeated the old "licensed notary"
claim (the landing page's hero line, its "How it works" step 3, its
"Who it's for" section, and 3 of the FAQ answers added earlier) was
swept and reworded to match, not just the pricing card itself.

**Deliberately NOT renamed**: the underlying `add_notarization` fields
key, the `RentShield: Notarization Add-on` CustomField, and the
notarization pipeline's own tag vocabulary (`Being Notarized`,
`Notarized`, `Notarization Failed`, etc.) are unchanged. None of these
are customer-facing text -- the legal/chargeback risk this TODO named
was specifically about what a paying customer reads and pays against,
not internal Python identifiers, so renaming those would have been a
large, blast-radius-heavy refactor (touching workflows.py's trigger
conditions, custom-field bootstrapping, tag creation across multiple
management commands) for no reduction in the actual risk.

**Verified end-to-end, not just read**: a real Property Owner test
account ran the full demo checkout with Certified E-Signature selected
-- confirmed the Order's `amount_aed` (328 = 29 + 299) matches the
generated Document's own `total_price_aed` custom field exactly, and
confirmed that Document still picked up its `Pending Review` tag
correctly (the confirmation gate, unaffected by the new payment layer).
Separately confirmed a checkout attempt that only sets
`add_real_notarization` is rejected with a clear 400 before any Order
is even created. Confirmed a checkout request that fails validation
creates no orphan Order row. Not verified: real Stripe Checkout Session
creation or the real webhook path -- no live Stripe account/keys exist
in this environment; that needs real or Stripe test-mode keys supplied
before it can be exercised for real.

## Notary-provider research scanner (2026-09-09)

Built while researching whether any UAE notary service exposes a
third-party API (the still-open question behind the `real_notarization`
tier above) -- `documents/rentshield/notary_research/` is a small,
recurring background check of a real, live-search-verified list of UAE
notary and notice-delivery services (`targets.py`, 10 URLs: Dubai
Courts' own Smart Electronic Notary, the UAE Ministry of Justice's
E-Notary system, 7 private notary/notary-support services, and
Emirates Post's Registered Email service) for any public sign of a
developer/API/partner program. Runs daily (03:15 UTC by default,
`PAPERLESS_RENTSHIELD_NOTARY_SCAN_CRON`) via
`documents.tasks.run_notary_provider_scan_task`, and on demand via
`manage.py scan_notary_providers`. Uses Scrapfly
(`PAPERLESS_SCRAPFLY_API_KEY`, empty/no-op-safe like every other
optional integration here) to fetch each page, diffs each scan against
the previous one (a JSON snapshot per target under
`DATA_DIR/notary_research/`, not a new database model -- this is
exploratory research data, not product data), and emails
`PAPERLESS_RENTSHIELD_NOTARY_RESEARCH_NOTIFY_EMAIL` only when a target
shows a genuinely *new* signal, not on every run.

**What the research already found, real and worth acting on directly**:
no UAE notary service currently exposes a third-party API. Dubai
Courts' and the Ministry of Justice's own e-notary systems both require
the party themselves to verify via UAE Pass and complete a live video
call -- a strong signal they may not be automatable by a SaaS on a
landlord's behalf at all. The closest thing to a "notary API" found
(e.g. OneNotary) is a US-based Remote Online Notarization platform, not
valid under UAE Federal Decree-Law No. 20/2022. One private service,
E-Notary Dubai (checked directly, not guessed), explicitly advertises
"licensed notification service delivery" for eviction/legal notices
specifically -- closer to this product's actual use case than a generic
notary listing, and the better candidate for direct manual-partnership
outreach than for API integration, since it doesn't expose one either.

**A genuinely more promising lead, found from user-supplied source URLs
(hhslawyers.com, poa.ae, idbooth.ae, emiratespost.ae), not this
project's own search**: Emirates Post's Registered Email/Registered
Digital Communication service is real, TRA-accredited, and produces
legally admissible delivery certificates -- it's Article 25(3)'s
"registered mail with acknowledgment of receipt" channel specifically,
a genuinely recognized method (unlike certified e-signature, which
isn't one of the three 25(3) channels at all). Emirates Post has a
real, live developer API program ("EMX API", `developers.emx.ae`,
`api@emx.ae`, sandbox at `tracking-stg.epservices.ae` /
`local-stg.epservices.ae`) -- **confirmed on 2026-09-09** (via a
publicly shared Postman collection plus the `developers.emx.ae`
`/local.html` and `/faqs.html` docs pages) to cover **only** courier/
parcel shipment: `CreateBooking`, `Tracking`, `Cancel`, label printing.
No registered-email/registered-mail/legal-notice-delivery endpoint
exists in that API today -- this closes the "not yet confirmed"
question from the earlier finding. This is still the strongest lead
found so far for automating a real, 25(3)-valid delivery channel, but
it is now confirmed **not self-serve**: the real next step is direct
manual outreach to `api@emx.ae` asking them to extend API access to
the registered-email product specifically, not waiting on this scan or
their public docs to change. A new FAQ entry on the landing page
(`#faq`) tells visitors this option exists today (self-service via
Emirates Post directly) while RentShield doesn't yet dispatch it on
their behalf.

The real next step this research points to is outreach, not more
scraping.

**Verified for real**: the keyword-matching and diff logic was verified
against three simulated scan runs (mocked fetch, since no Scrapfly key
exists in this environment) -- confirmed a baseline run reports nothing,
a real change on one target is caught precisely, and a repeat scan with
unchanged content does not re-report the same signal. Confirmed the
no-key path no-ops cleanly (`manage.py scan_notary_providers` prints a
clear message and exits 0, doesn't crash). Confirmed the notification
email fires through the app's real configured mail backend when
triggered. Not verified: the actual Scrapfly API or the real target
sites -- needs a real `PAPERLESS_SCRAPFLY_API_KEY`.

## Real Notary Public: human-fulfilled, not API-driven (2026-09-09)

The `real_notarization` add-on (`documents/rentshield/pricing.py`) is
now purchasable (`available: True`, was `False`). The decision behind
it: with no UAE notary exposing a third-party API (confirmed, see the
research above), the honest way to actually offer real notarization
today is to have a real person fulfill it manually, the same way it
worked before this feature existed -- and label it as exactly that, not
dress it up as automated.

**What's actually automated** (the small part that is): selecting this
add-on at checkout tags the notice `Awaiting Notary Public`, sets
`RentShield: Notary Public Status` to `pending`, and emails
`PAPERLESS_RENTSHIELD_NOTARY_FULFILLMENT_NOTIFY_EMAIL` (empty/unset is
a no-op, same pattern as every other optional notify setting here) --
see `documents/rentshield/service.py`'s `_notify_notary_fulfillment_requested()`,
wired into `generate_and_consume()` next to the existing Legal Review
add-on handling it mirrors exactly.

**What's manual, deliberately** (everything past that email): the
fulfiller -- a real notary-services contact, not an API -- works the
`RentShield: Notary Public Queue` saved view
(`manage.py create_rentshield_dashboards`, filtered to the `Awaiting
Notary Public` tag, oldest first) entirely through paperless-ngx's own
native document editor. No bespoke completion endpoint or Angular
screen exists for this on purpose -- see `documents/rentshield/
custom_fields.py`'s comment above `AWAITING_NOTARY_PUBLIC_TAG_NAME` for
why: the old Lawyer role's object-permission-grant machinery was this
project's biggest source of real bugs (see "Roles simplified" above),
and there is no reason to rebuild anything like it for a single trusted
back-office user. She:

1. Opens a notice from the queue, reads the notice details (already
   visible as custom fields -- landlord/tenant/reason/date).
2. Does the actual physical notarization herself, exactly as before.
3. Uploads the scanned/stamped notarized copy as a normal document
   (paperless-ngx's own stock uploader).
4. On the original notice: links that upload via the `RentShield:
   Notarized Copy` field (a `documentlink` CustomField -- paperless-ngx's
   own document-picker widget, no custom UI needed), fills in
   `RentShield: Notary Reference No.`, sets `RentShield: Notary Public
   Status` to `completed` (or `rejected` with a note in `RentShield:
   Notary Notes`), and swaps the `Awaiting Notary Public` tag for
   `Notary Public Completed` (or `Notary Public Rejected`) herself.

A demo staff/superuser account was created for this (`notary` --
also the pre-role-simplification legacy account of the same name,
upgraded to staff/superuser and taken out of the now-vestigial
"Notary" group rather than left as a second, confusing account;
credentials given directly to the user, not committed here) since
paperless-ngx's own document-visibility queryset only bypasses
ownership filtering for an active superuser, not merely `is_staff` --
confirmed by reading `documents/permissions.py`'s
`permitted_object_ids()`/`user_is_unrestricted()` before assuming
otherwise.

**Verified for real**: a real `generate_and_consume()` call with
`add_real_notarization=True` tags the resulting Document `Awaiting
Notary Public`, sets `notary_status="pending"`, and computes the
correct total (29 + 599 = 628 AED) -- confirmed against a real Document
row, then cleaned up. Confirmed via a real authenticated Django test
client call to `POST /api/documents/notice/checkout/`: omitting
`landlord_email` with this add-on selected returns 400 with the honest
message, and a full valid request succeeds in demo mode (no Stripe key)
and produces the same tag/field state. Not verified: the actual manual
completion path (linking a notarized copy, flipping status/tags) --
that's paperless-ngx's own already-shipped document editor, not new
code, so there's nothing here to unit-test.

## Notarization *is* service on the tenant, so completion now closes the loop (2026-09-11)

A process audit (see the diagram artifact from this date) surfaced a
real gap: nothing in this codebase ever delivered a notice to the
tenant. Certified E-Signature certifies the landlord's side; Real
Notary Public only attached a stamped copy and stopped. Both looked
like "notarization" but neither actually served anyone.

The fix isn't a new delivery pipeline -- it's recognizing what already
exists: under Article 25(3) of Law No. (33) of 2008
(`documents/rentshield/service_methods.py`), a notary-public visit
**is** one of the three legally recognized ways to serve a tenancy
notice. So the fulfiller completing a Real Notary Public request (the
same manual edit in paperless-ngx's own document editor described
above -- no new UI) now *is* the legal service event, not just a
stamped-copy upload.

`documents/rentshield/signals.py` (new) watches for that one
transition -- `RentShield: Notary Public Status` flipping into
`completed` or `rejected` -- via a plain `pre_save`/`post_save` pair on
`CustomFieldInstance`, wired in `apps.py`'s `ready()`. A native
paperless-ngx Workflow couldn't do this instead: its `EMAIL` action
type's recipient is a fixed string set at workflow-config time, and its
Jinja2 templating only exposes a fixed allowlist of Document attributes
(`documents/templating/workflows.py`) -- neither can reach a
per-document `landlord_email` CustomField value, which differs on every
notice.

On that transition:
- **`completed`**: `RentShield: Served Date` (new CustomField,
  `0031_rentshield_service_fields.py`) is stamped with today's date
  automatically -- one less manual field for the fulfiller, since the
  system already knows the moment it learns completion happened -- and
  the landlord is emailed that their notice has been notarized and
  legally served, with the reference number and served date.
- **`rejected`**: the landlord is emailed that it could not be
  notarized/served, with her notes.

Both are `service.py`'s new `_notify_notice_served()` -- same
fire-and-forget shape as `_notify_legal_review_requested()`/
`_notify_notary_fulfillment_requested()`, but reading the recipient
from the notice's own `landlord_email` field instead of a fixed
`settings.*` address, since every notice has a different landlord.

**Verified for real**: a real `CustomFieldInstance` save simulating the
fulfiller's edit (pending -> completed) on a real demo Document stamps
`served_date` and produces a real outbound email (DEBUG's
filebased backend, `src/sent_emails/`) addressed to that document's own
landlord, with the reference number and served date in the body;
resaving `completed` again sends no duplicate; the `rejected` path was
also confirmed to send the correct message and not stamp `served_date`.

**Not done yet**: Certified E-Signature still doesn't map to any
Article 25(3) service method (see its own entry below) -- that add-on
certifies a signature, it doesn't serve anyone. Also not done: this
only handles the manual per-instance `.save()` path (the document
editor); paperless-ngx's separate bulk-edit-multiple-documents endpoint
writes via `bulk_update()`, which bypasses Django signals entirely --
irrelevant today since nobody bulk-completes notarizations, but worth
knowing if that ever changes.

**Correction (2026-09-12)**: the served_date/notify write above was
originally run inline in the signal (even behind
`transaction.on_commit()`) -- verified for real that this does NOT
reliably persist through the actual DRF PATCH `/api/documents/<id>/`
path the notary officer's browser uses: the write is visible to its own
connection immediately after, then silently gone moments later, with
nothing raising. Moved to a real Celery task
(`documents.tasks.notify_notice_served_task`, dispatched from the same
`on_commit` hook) -- same reasoning `run_ai_review_task`/
`run_notarization_task` already give for keeping this class of work off
a request's own transaction. Confirmed fixed via the real PATCH path,
repeatedly.

**Also discovered while chasing that (not a bug in the above -- a
pre-existing API characteristic, documented here so nobody rediscovers
it as a live incident)**: `documents/serialisers.py`'s
`DocumentSerializer` treats a submitted `custom_fields` list as the
*complete* desired set for that request -- any existing custom field
not included gets removed. The real Angular editor is not exposed to
this: `document-detail.component.ts`'s `getChangedFields()` submits
`this.documentForm.get('custom_fields').value`, which is the *entire*
FormArray's current value, not a diff. It only bites a caller that
PATCHes a hand-built partial `custom_fields` array (exactly what my own
verification scripts did, which is how this got noticed) -- worth
knowing before anyone builds a script or third-party integration against
this API expecting PATCH-style partial semantics on `custom_fields`.

## Legal-compliance pass: the app's own researched legal logic wasn't all enforced (2026-09-12)

Prompted by wanting the platform's process to actually follow Dubai
tenancy law rather than just cite it, audited where this codebase's own
already-researched legal knowledge (Article 25(3) service methods,
per-reason notice periods and prerequisites) wasn't enforced by the real
generate/serve path. Fixed the ones that were straightforward
correctness bugs regardless of any product-policy question; left the
ones that are genuine business decisions (see the "not done yet" note
above about Certified E-Signature) for a human call.

**The generated notice was asserting service before service happened.**
`documents/rentshield/notice_builder.py` printed "Served via Notary
Public" and "...in accordance with Article 25(3)" on *every* notice, in
both languages, at generation time -- before any add-on, let alone
actual service, occurred. Changed to state the requirement ("must be
served... to take legal effect") instead of a false completed-action
claim. This is a correctness fix, not a policy choice: a document
asserting something happened before it happened is wrong regardless of
which add-on strategy this project eventually settles on.

**Ejari number was optional, but cited as if real.** Falls back to the
literal placeholder `"[Ejari No.]"` in `notice_builder.py` if blank,
printed straight into the "Ejari Contract No." line. Made required on
both `notice-form.component.ts` (`Validators.required`) and
`rentshield_views.py`'s `validate_notice_fields()` -- same pattern as
`landlord_name`/`tenant_name`/`notice_date`.

**Reason-specific legal warnings were informational only.** Every entry
in `documents/rentshield/constants.py`'s `ALL_REASONS` carries a
`warning` (e.g. demolition/renovation need an RDSC-presentable permit;
personal-use carries a 2-year non-relet restriction) -- previously
just displayed, never gated. Added `RentShield: Reason Requirements
Acknowledged` (new CustomField, `0032_rentshield_reason_acknowledgment.py`),
a required checkbox next to the warning box in `notice-form.component.html`
that resets whenever the reason changes (each reason's warning is
distinct), enforced again server-side in `validate_notice_fields()`.
RentShield can't verify a government permit exists -- it can require the
landlord to affirmatively represent that it does, recorded on the
notice for the record, instead of silently assuming it.

**The property owner is now told, plainly, when a notice isn't legally
served.** `notice-form.component.html`'s post-generation screen and
`document-detail.component.html`'s notice banner (extending the
existing Real Notary Public guidance alert) both distinguish three
states: legally served (green, with the served date), queued for Real
Notary Public (info), or not legally served at all -- Certified
E-Signature and the no-add-on path both fall into that last bucket, and
now say so instead of implying otherwise. `pricing.py`'s Certified
E-Signature description was also corrected to say outright that it does
not satisfy Article 25(3) service.

## Property-owner identity verification (2026-09-12)

Real NFC passport-chip reading needs either a native app with hardware
NFC access (iOS CoreNFC / Android NFC) or a physical PC/SC reader --
researched several options (selfxyz/self, pypassport, JMRTD,
tananaev/passport-reader, AppliedRecognition) and none fit a pure
Angular + Django web app without either building a whole separate
native app or asking every landlord to install a third-party wallet
app first. Went with the practical alternative instead: camera-based
MRZ/document capture + liveness + face match, via a self-hosted
[Idswyft](https://github.com/team-idswyft/idswyft-community) instance
-- MIT licensed, works entirely in-browser, no native app, no
per-verification vendor fee.

**New app: `documents/rentshield_identity/`** -- a real Django app
with its own model (`IdentityVerification`, one row per user), not a
Document/CustomField (same reasoning as `rentshield_billing`: this has
to exist independently of any notice). `idswyft_client.py` mirrors
`documents/rentshield/esign/docuseal_client.py`'s shape exactly (thin
`requests` wrapper, env vars read directly, not through Django
settings -- `IDSWYFT_BASE_URL`/`IDSWYFT_API_KEY`, unset is a deliberate
"not configured" state).

**Unlike Stripe's demo-mode fallback, an unconfigured Idswyft never
fakes a pass.** `start_verification_view` returns a clear 503 instead
-- faking a payment for demo purposes is fine, faking a KYC/identity
result never is, even in a dev environment.

**QR-code phone handoff**: a laptop webcam is a bad way to photograph
a passport, so the frontend (`rentshield/identity-verification/`)
renders the hosted verification URL as a QR code -- scan it with a
phone, or use the "continue on this device" link if already on one.
QR rendering uses `qrcode-generator` (MIT, zero runtime deps)
**vendored directly as a `.js` file, not installed via npm**: this
project's `node_modules` is actually pnpm-managed (`.pnpm` store
layout), and running plain `npm install` against it hits a real
npm/arborist bug (`Cannot read properties of null (reading 'matches')`)
unrelated to the package being added -- confirmed by testing with
`qrcode-generator` specifically, likely reproducible for any new npm
dependency added this way. Use `pnpm add`, not `npm install`, next time
a real dependency needs adding to `src-ui`.

**Verified for real**: the backend end-to-end via a real Django test
client, not just read -- and this caught two genuine bugs, not
hypotheticals: (1) `start_verification_view` originally checked "is
Idswyft configured" before checking "is this user already verified,"
so an already-verified user got a spurious 503 on every subsequent
visit -- reordered so an existing `verified` record short-circuits
before the configuration check; (2) the same view unconditionally
created a `pending` `IdentityVerification` row even when Idswyft wasn't
configured, meaning a user who tried during an unconfigured window
would show as permanently "pending" (implying progress that never
started) -- moved the row creation to after the configuration check, so
an unconfigured attempt leaves no misleading trace.

**Frontend verified for real, on retry once memory freed up**: two
initial build attempts were killed by the OS's OOM killer (this
sandbox's memory was critically low -- under 700MB free, swap nearly
full -- from the user's own Firefox/Chrome processes, not from
anything this feature added); a `tsc --noEmit` type-check passed
cleanly in the meantime as a lighter partial check. Once memory freed
up, `ng build --configuration=dev-single-origin` completed cleanly, and
a real Playwright pass confirmed: the sidebar link navigates correctly;
the real "not configured" 503 renders as a plain, correct message with
no leaked internal references (an earlier draft of the copy said "see
the README," meaningless to an actual user -- caught in review, fixed
before this pass); and, with the network boundary mocked at exactly the
`/identity/verify/start//status/` endpoints (Idswyft itself still isn't
deployed anywhere -- see below), the real QR code renders correctly via
the vendored library, the "continue on this device" link carries the
right URL, and the pending -> verified transition renders correctly
after two poll ticks.

**Update (2026-09-12, later the same day): idswyft-community actually
deployed and tested against for real**, once memory freed up (cloned to
`~/idswyft-community`, sibling to this repo, not inside it -- `docker
compose up -d` with `SANDBOX_MODE=true`, port 8090; core services only
run ~450MB combined, well under the `mem_limit` ceilings). This is what
real testing is for: the README's documented API contract above turned
out to be incomplete, and reading the actual backend source
(`backend/src/routes/newVerification.ts`) surfaced three real bugs the
"not configured" path could never have caught:

1. **`POST /api/v2/verify/initialize` requires a `user_id` (UUID)** --
   not mentioned anywhere in the README. `idswyft_client.py` wasn't
   sending one at all, which would have 400'd against a real instance
   every time. Fixed: `rentshield_user_uuid()` derives a stable
   `uuid.uuid5()` from the Django user's own id -- deterministic, no new
   stored field needed.
2. **The initialize response's URL field is `verification_url`**, not
   `hosted_url` -- `_hosted_url()`'s fallback chain already checked both,
   now checks `verification_url` first since that's what's actually
   returned.
3. **`GET .../status`'s `status` field is the granular session step**
   (`AWAITING_FRONT`, `FACE_MATCHING`, `COMPLETE`, ...), never one of
   `IdentityVerification.Status`'s values -- the field that actually
   means "verified/failed/manual_review" is `final_result`, which stays
   `null` until the session completes. `get_verification_status()` now
   reads that field and returns `None` while still in progress;
   `verification_status_view` was fixed alongside it to treat `None` as
   "leave the stored status alone," not a value to write.

**Also fixed, in Idswyft's own deployment, not this repo**: its shipped
`docker-compose.yml` never wired `FRONTEND_URL` through to the `api`
service at all, so the backend guessed the verification page's origin
from request headers and produced a URL missing the port
(`http://localhost/user-verification...` instead of `:8090`) -- added
the env passthrough and set `FRONTEND_URL` in `.env`.

**Verified for real, the whole way through**: a real authenticated
call to `POST /api/documents/identity/verify/start/` against the live
Idswyft instance returns a genuine `verification_id` and a working
`hosted_url`; the real Angular page renders a real QR code pointing at
it; following that link lands on Idswyft's actual hosted verification
page (screenshotted) offering its own "scan QR to continue on your
phone" / "continue on this device" choice -- confirming the whole chain
from RentShield's UI through to Idswyft's real API and back is sound,
not just individually mocked pieces.

**Still not done**: this Idswyft deployment is local-sandbox-only (a
sibling directory, not committed, not on a real server) and was
created with a LIVE-type API key, not a sandbox key -- a full
document-upload + selfie + face-match run would invoke the real
PaddleOCR/TensorFlow pipeline (~1.5GB spike) and wasn't exercised, since
that needs real passport-photo images this environment doesn't have.
Webhook signature verification is also still not implemented
(undocumented scheme) -- `verification_status_view`'s active polling is
the real, relied-upon path regardless.

## Identity verification moved fully in-platform (2026-09-12, later still)

Three real user reports drove this round, in order:

**1. "Still spinning" after logging back in.** Root cause: the status
endpoint never returned the session's `hosted_url`, so a reload had
nothing to redraw the QR from -- just a permanent spinner with no way
out. Fixed as part of the bigger change below (redrawing is now moot;
resuming re-fetches the right capture step instead).

**2. Wanted a reset button.** `start_verification_view` already allowed
starting a fresh session over an existing pending one (only blocks on
already-`verified`), so `reset()` in the Angular component is just
`start()` again -- no new backend logic needed, just a button that was
missing from the UI.

**3. Wanted Idswyft fully white-labeled as RentShield, not a redirect
to a separate branded page.** Checked: idswyft-community's hosted
verification page can't be white-labeled without their paid enterprise
plan. Rather than accept that branding, rebuilt the flow to use
Idswyft purely as a backend API -- the photo capture and selfie now
happen directly inside RentShield's own `identity-verification` page
(native `<input type="file" capture="environment/user">`, which opens
the phone's camera directly, or a file picker on desktop -- no custom
camera UI needed, no new dependency). The property owner never sees
Idswyft's name or leaves RentShield's page. The old QR-code/redirect
approach is gone entirely, and with it `vendor-qrcode.js`/`.d.ts` --
deleted rather than left as dead code.

**New backend contract, verified against real source again** (`backend/
src/routes/newVerification.ts`), not assumed from docs:
- `create_verification_session()` now always requests
  `verification_mode: "identity"` -- the default "full" mode expects a
  back-page document upload, which doesn't exist for a passport
  (single-sided); "identity" mode's flow (front document -> live
  capture -> face match -> complete) is the one that actually fits.
- Two new endpoints, `upload_front_document_view`/
  `upload_live_capture_view`, forward the photo/selfie as multipart
  uploads (`document`/`selfie` field names, confirmed from source) to
  Idswyft's `POST .../front-document` and `POST .../live-capture`.
  Both can hard-reject on their own (bad document, no face detected) --
  both responses are checked for `final_result` and written to the
  stored status immediately, not just left for the next poll. This
  closes the same "stuck forever" failure mode as fix #1, at both
  points it could actually occur, not just the one already reported.
- `verification_status_view` now also returns Idswyft's granular
  session step (`AWAITING_FRONT`, `AWAITING_LIVE`, ...), which is what
  lets the frontend resume at the correct capture step after a reload
  instead of losing its place.

**Verified for real, the whole way through, including actual ML
inference**: generated two synthetic test images (a plain rectangle
with drawn text standing in for a passport photo, a plain oval standing
in for a selfie) and ran them through the real flow via Playwright.
The engine's real OCR genuinely read the drawn text back
(`full_name: "SAMPLE TEST"` from "Surname: TEST" / "Given Names:
SAMPLE") and advanced the session correctly to `AWAITING_LIVE`; the
selfie step correctly `HARD_REJECTED` (no real face in a plain oval)
and the UI correctly showed the failure state with a working retry --
confirming the full real pipeline (multipart upload, real OCR, real
face-match, status write-back, UI transition) end to end, not a mocked
approximation of it. Confirmed "Idswyft" appears nowhere in RentShield's
own rendered page.

**Still not done**: the front-document hard-reject path (fix, not yet
independently re-tested with a real forced rejection -- it mirrors the
already-proven live-capture handling exactly, but wasn't separately
exercised this round). No liveness challenge (head-turn/blink) is
requested -- Idswyft's "identity" flow doesn't require one, a single
selfie is enough for its own liveness+face-match analysis.

## Admin identity-verification review page + evidence retention (2026-09-12, later still)

The property owner's uploaded passport photo and selfie were being
forwarded to Idswyft and then discarded on RentShield's own side --
Idswyft never returns them once processed, so there was no way for
staff to review what was actually submitted. Fixed by having RentShield
keep its own copy:

- `IdentityVerification` gained `passport_photo`/`selfie_photo`
  (`FileField`) plus `latitude`/`longitude`/`location_accuracy_m`
  (migration `0002_verification_evidence`). Both upload views now save
  the raw bytes locally (`ContentFile`, since the upload stream is
  already consumed by the time Idswyft's own upload needs the same
  bytes) before forwarding to Idswyft, and record the browser's
  geolocation (captured once via `navigator.geolocation` when
  verification starts -- evidence of where it happened, never a gate on
  the result; a denied/unsupported permission is a normal, silently
  accepted outcome).
- `MEDIA_URL` was entirely undefined in this project's settings
  (paperless-ngx's own Document storage doesn't route through Django's
  standard static-file serving) -- added, plus DEBUG-only media serving
  in `urls.py`, so the new evidence files are actually fetchable.
- New `IsRentshieldAdmin` permission (`is_staff` alone, matching the
  frontend's own `permissionsService.isAdmin()` -- not `is_superuser`)
  gates a new `GET /api/documents/identity/verify/admin/list/`
  (`admin_views.py`), returning every verification with its
  photo URLs, status, and location.
- New admin-only nav item ("Identity Verification Admin",
  gated the same `*ngIf="permissionsService.isAdmin()"` way as the
  existing Notary Guide link) opens `identity-admin`: passport/selfie
  thumbnails side by side, status badge, provider, and a link to an
  OpenStreetMap pin when location was captured.

**Verified for real**: ran a full upload cycle (front-document +
geolocation, then selfie) through the live API with synthetic test
images, confirmed the admin list returned correct JSON with
downloadable (200) photo URLs, and confirmed a non-admin account gets a
real `403` from the same endpoint (not a 401/redirect). Rebuilt the
Angular frontend and drove it with Playwright as a real logged-in
admin: nav link present, page renders the real record with its
thumbnails/status/location link; logged in as a non-admin property
owner and confirmed the nav link is absent and the endpoint 403s.
Cleaned up the synthetic test records/tokens afterward.

**External repos evaluated, not adopted this round**: the user shared
six repos (ballerine-io/ballerine, two Faceplugin-ltd repos,
jumbojett/OpenID-Connect-PHP, CCCpan/Gebaini, FaceOnLive/
ID-Verification-OpenKYC) hoping one would make verification "more
efficient." None replace anything currently in use: the two
Faceplugin-ltd repos and FaceOnLive are marketing funnels for paid
closed-source SDKs (empty implementation folders, license-gated
binaries, sales contact links) rather than usable open-source
libraries; ballerine's admin case-review UI is real but the project
self-describes as "undergoing a major rebuild and not actively
supported," and would replace, not complement, the admin page built
above on this project's own Django/Angular stack; jumbojett's OIDC
client and Gebaini aren't identity-verification tools at all. If a
genuine face-match step independent of Idswyft is ever needed (e.g.
matching an NFC chip photo against a selfie), CompreFace
(exadel-inc/compreface) is the one real, mature, self-hostable
candidate identified so far.

**Known, deliberate limitation, explained to the user three times this
session**: Face ID/Android biometric unlock and NFC passport-chip
reading are both real, but neither can be combined the way "scan a QR
code to trigger the phone's Face ID and match it against the passport
chip" implies. No app or website on any platform -- iOS or Android --
can read a raw biometric signal from the OS's Face ID/fingerprint APIs;
they only return a yes/no "the device owner unlocked this," which
proves nothing about a passport. A QR code doesn't change this -- it
only opens a link, and whatever loads is still bound by the same OS
rule. Real NFC chip reading (BAC/PACE per ICAO 9303) does need a native
app (there is no browser API for it on any platform), which is what
`/home/giova/RentShieldPassportReader/` (a working, compiled Android
app using JMRTD) was built for earlier this session -- but the user has
since said they don't want property owners downloading an APK, so that
native app is parked, not integrated, pending a decision on that
tradeoff.

## AI pre-screening for Notary review, and a real Celery infra bug found along the way (2026-09-13)

First of three requested Claude-powered features (pre-screening the
identity-verification queue, real LLM compliance reasoning on notices,
a support chatbot) -- built this one completely, the other two are
still to come. Confirmed first that no Claude/Anthropic integration
existed anywhere in this codebase already: the existing "AI Compliance
Review" add-on (`documents.rentshield.service.run_ai_review`) is a
deterministic citation-graph/rules engine, not an LLM call.

`documents/rentshield_identity/ai_prescreen.py` calls Claude (official
`anthropic` SDK, `claude-opus-5` by default -- this project's own Claude
API guidance says default to Opus and let the user trade down for cost
themselves) with everything the automated pipeline already gathered --
OCR-vs-chip cross-check, both independent face-match scores, Idswyft's
own result -- and asks for a short advisory summary, explicitly
prompted to never make or imply a verify/reject decision. Dispatched as
a Celery task (`run_identity_prescreen_task`) from `upload_video_view`
right when a verification reaches `AWAITING_NOTARY_REVIEW`, so the
summary is usually ready before a Notary even opens the record. Shown
in the review dashboard clearly labeled "AI pre-screen (advisory only
-- not a decision)" -- it never sets `status`; only a human still can.
A missing `ANTHROPIC_API_KEY` (nothing is configured yet -- this needs
a real key from the user's own Anthropic Console account, not
something that can be generated the way Idswyft's secrets were) or any
API error just leaves the summary blank, same "advisory extra, never a
pipeline blocker" pattern as the chip-vs-selfie face match.

**Real bug found and fixed verifying this for real**: dispatching the
new task failed with `SignedPickleError: HMAC verification failed`
against a genuinely different Celery worker process, not a bug in the
new code. Root cause: `paperless.signed_pickle` signs task messages
with `settings.SECRET_KEY`, but the long-running dev Django server was
originally started with an explicit `PAPERLESS_SECRET_KEY=devsecretkey`
override on its command line, inherited across every autoreload restart
since (Django's autoreload re-execs preserving the process's existing
environment, and python-dotenv's `load_dotenv()` never overrides an
already-set variable) -- while a freshly started Celery worker picked
up `paperless.conf`'s different on-disk value instead. Two processes,
two different signing keys, guaranteed mismatch on every task, not just
this one -- meaning any other `.delay()` call in this app (notice-served
notifications, the existing AI-review task, notarization dispatch) hit
in that window would have silently failed the same way. Fixed by
restarting Celery with the same environment overrides the Django server
already runs with; verified by watching the exact task succeed in the
worker's own log afterward. No shared startup script exists yet to keep
these two processes' environments in sync automatically -- worth adding
if this dev setup persists.

## "Scan QR to sign in" device pairing, and reworking the Notary review queue (2026-09-13)

Two requests handled the same day. First: the Notary review page
(`identity-admin.component.ts`) showed every verification record
regardless of status, which made the queue useless once more than a
handful of users had verified/failed already --
`admin_list_verifications_view` now defaults to
`AWAITING_NOTARY_REVIEW` only (`?status=all` still gets the full
history), the Notary can now edit a misread OCR/chip field right on
the page before confirming/rejecting instead of acting on a record she
can see is wrong with no way to fix it, and confirm/reject now emails
the property owner the outcome and shows a real "Verified" badge on
their own page.

Second: getting the property owner onto the native app without typing
a password on the phone. Real NFC chip reading has needed a native app
all along (no browser API for it anywhere), but the only way onto that
app was a manual username/password login. Added a QR-based pairing
handoff instead -- the same pattern WhatsApp Web and the GitHub CLI's
device flow use. `documents/rentshield_identity/pairing_views.py`
issues a short-lived (5 min), single-use, 192-bit
(`secrets.token_urlsafe(24)`) code and renders it as a QR using the
`qrcode` package (already a transitive dependency here -- allauth's
own MFA/TOTP setup uses it the same way, just for an `otpauth://` URL
instead of ours). The Android app scans it with Google Play Services'
`GmsBarcodeScanning` module (`com.google.android.gms:play-services-
code-scanner:16.1.0`, version confirmed directly against
`dl.google.com`'s Maven metadata, not guessed) -- no custom camera
permission or preview UI needed, just `.startScan()` and a callback.
Claiming the code is intentionally `AllowAny`: the phone has no
account yet at that point, that's the whole reason this exists, and
safety comes entirely from the code's entropy/single-use/expiry, not
from auth on that one call. A claimed code only ever mints the same
DRF token a password login already would -- no higher-privileged path.

The QR payload is a real URI (`rentshieldpair://pair?server=...&code=
...`), not a hand-split string, specifically so a server address that
itself contains a colon (`https://host:8000`) doesn't break parsing --
and because it's a real custom scheme, it can later double as an
actual Android App Link/iOS Universal Link for "tap to open the app"
when the property owner is already on their phone, not just a QR to
scan cross-device (not built yet, just left possible).

**Known gap, not filled with a fake link**: there's no Play Store
listing for this app, only a debug APK `build-android.yml` produces as
a CI artifact -- not something a property owner could click. The web
pairing page only shows a "Download RentShield" link once
`PAPERLESS_RENTSHIELD_ANDROID_APK_URL` is actually set to somewhere
real; until then it just says to ask a property manager for the app,
rather than linking to a Play Store badge that doesn't exist.

## Not done yet (named, not silently skipped)
