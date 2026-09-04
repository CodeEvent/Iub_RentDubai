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

## Not done yet (named, not silently skipped)

- **Auth wiring**: every `documents/rentshield_views.py` endpoint is
  `AllowAny` for now. paperless-ngx's own auth (django-allauth, DRF token
  auth, django-guardian object permissions) is fully present and
  unmodified — wiring these endpoints into it is next, not forgotten.
