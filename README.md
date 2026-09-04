# Dubai Rent Shield

A bilingual (English / Legal Arabic) statutory tenancy-notice platform for
Dubai landlords, property managers, and agents — generates RERA-compliant
12-month eviction notices (Law No. 33 of 2008, Article 25(2)) and 30-day
lease-breach notices (Article 25(1)).

## History and current foundation

This platform went through four architectures:

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
4. **The current foundation**: `rentshield` as a Django app — with its own
   database table — was removed entirely. Every notice is now a real
   paperless-ngx `Document`, and every notice field (landlord, tenant,
   reason, e-sign status, ...) is a paperless-ngx `CustomField` value on
   that Document — see "What's in `documents/rentshield/`" below. This was
   an explicit choice, again offered and confirmed rather than assumed:
   paperless-ngx itself is now the sole system of record for RentShield
   data, and `src-ui/`'s `rentshield/` UI area talks only to paperless-ngx's
   own stock REST API (`/api/documents/`, `/api/tags/`,
   `/api/custom_fields/`, `/api/tasks/`) plus a handful of plain functions
   mounted directly inside the `documents` app (bilingual PDF rendering,
   pricing/notice-period math, e-signature orchestration — the pieces
   paperless-ngx has no native equivalent for). There is no
   `rentshield.apps.RentshieldConfig` in `INSTALLED_APPS` any more.

None of the three prior architectures are deleted — `legacy/` and
`legacy-v1/` are kept intact for reference, and the Phase-3 `rentshield`
Django app's history is preserved in git even though the app itself is
gone from the working tree.

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
                paperless-ngx's own document-management UI is unmodified;
                a new `src-ui/src/app/rentshield/` area adds the
                notice-wizard/dashboard/legal-skills UI as standalone
                Angular components styled after MintHCM's dashboard layout
                (dark sidebar + topbar + cards) — see "The Angular
                frontend" below. It talks only to paperless-ngx's own
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

`src-ui/src/app/rentshield/` is a MintHCM-styled UI built directly on top
of paperless-ngx's Angular 22 app (standalone components, zoneless change
detection, Bootstrap 5 / ng-bootstrap — no separate framework introduced).
It talks **only to paperless-ngx's own stock REST API** — `/api/documents/`,
`/api/tags/`, `/api/custom_fields/`, `/api/tasks/` — plus the thin
`documents/notice/*` endpoints described above; there is no rentshield-
specific data API to keep in sync with a separate backend contract. This
was a deliberate, scoped choice over the alternatives considered (a full
rebase onto MintHCM's actual PHP/SuiteCRM + Vue codebase; running MintHCM
as a second parallel backend; keeping a separate rentshield DRF API
backed by its own database table) — it keeps the paperless-ngx/Django
foundation and every ported service (citation graph, legal skills,
e-signature) completely intact and makes paperless-ngx itself, not a
sibling app, the one thing both the notice-generation logic and the
frontend depend on.

```
rentshield-frame/       Dark sidebar + topbar shell (MintHCM-style navy
                        #0f172a / emerald #10b981 palette), collapsible,
                        mobile-responsive, wraps every rentshield route.
dashboard/              Stat cards (total/statutory/breach/AI-reviewed
                        notices) + recent-notices panel.
notice-wizard/          4-step wizard (Parties → Property → Notice &
                        Reason → Review) with a live bilingual (EN/AR)
                        document preview, computed via
                        POST /api/documents/notice/preview/ — blurred/
                        watermarked until saved. Save renders a real PDF
                        and dispatches it into paperless-ngx's async
                        consumption pipeline (POST .../notice/create/
                        returns a Celery task id), then polls
                        paperless-ngx's own GET /api/tasks/?task_id=...
                        until it resolves into the created Document's id.
notices-list/           Table of every saved notice, listed via
                        paperless-ngx's own
                        GET /api/documents/?tags__id__in=<tag_id> and
                        mapped from each Document's custom_fields array
                        — not a RentShield-specific list endpoint.
legal-skills/           Master-detail browser over the ported
                        legacy-v1/mcp/skills/ Markdown library.
rentshield-settings/    API health check, pricing table, about section.
services/rentshield-api.service.ts   Typed HTTP client wrapping
                        paperless-ngx's stock documents/tags/custom_fields/
                        tasks endpoints plus the documents/notice/*
                        endpoints — including the CustomField id ↔ short-
                        key mapping and the Document → Notice-shaped
                        client-side view model every component reads.
```

**Verified end-to-end in a real browser** (Playwright against a live
`ng serve` + `manage.py runserver` + `celery worker`, not just "should
work"), specifically re-verified after the move onto paperless-ngx's own
CustomFields (this wasn't just carried over from the pre-refactor
verification): filled out the full wizard for both a statutory (Personal
Use/Recovery) and a 30-day breach (Non-payment of Rent) notice and
confirmed the live preview renders correct bilingual content; clicked
Save and confirmed the button correctly waits through the real async
create → Celery consume → poll-until-resolved sequence before showing
"Saved"; confirmed the resulting paperless-ngx `Document` carries every
field as a real `CustomField` value plus the `RentShield Notice` tag, via
a direct `GET /api/documents/<id>/` call; confirmed the e-signature
orchestrator correctly reads those fields back off the Document (not a
separate row) and degrades gracefully with no DocuSeal/OpenSign running;
and confirmed the Dashboard and Saved Notices pages both render real data
sourced entirely from paperless-ngx's stock document-list and tag-filter
endpoints, with matching screenshots.

Non-obvious bugs hit and fixed during verification (kept here since
they're easy to reintroduce):
- A `computed(() => this.form.valid)` never re-evaluates because
  `FormGroup.valid` is a plain getter, not a tracked Signal — the
  wizard's Save button uses a real `signal()` kept in sync via
  `form.statusChanges`/`valueChanges` instead.
- An uncaught error thrown inside a `toSignal()`'d `router.events`
  subscription (from walking a freshly-injected `ActivatedRoute` before
  its tree was populated) silently broke the Router's own child-route
  activation, leaving nested `<router-outlet>` content blank — fixed by
  reading `router.routerState.snapshot.root` instead.
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

## Not done yet (named, not silently skipped)

- **Auth wiring**: every `documents/rentshield_views.py` endpoint is
  `AllowAny` for now. paperless-ngx's own auth (django-allauth, DRF token
  auth, django-guardian object permissions) is fully present and
  unmodified — wiring these endpoints into it is next, not forgotten.
- **Notice detail route in the RentShield UI**: the Angular `rentshield/`
  area has a Saved Notices *list* but no per-notice detail page of its
  own; the wizard's post-save "View it" link goes to that list rather
  than a dead-end URL. paperless-ngx's own `/documents/<id>` detail view
  already works for any RentShield notice (it's a real Document with the
  RentShield custom fields visible there) — a RentShield-styled detail
  page is a nice-to-have on top of that, not a missing capability.
