# Dubai Rent Shield

A bilingual (English / Legal Arabic) statutory tenancy-notice platform for
Dubai landlords, property managers, and agents — generates RERA-compliant
12-month eviction notices (Law No. 33 of 2008, Article 25(2)) and 30-day
lease-breach notices (Article 25(1)).

## History and current foundation

This platform went through three architectures:

1. A single-file HTML/CSS/JS prototype (`legacy/`).
2. A Node monorepo — Vue 3 + Express + `node:sqlite` + a real MCP server +
   a Python OCR microservice, with real DocuSeal/OpenSign e-signature
   integration, an `mcp/skills/` legal-guidance library, and an
   OpenContracts-inspired citation graph (`legacy-v1/`).
3. **The current foundation**: rebased onto
   [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)
   (vendored at upstream commit `a3851c157a4591cd0e213296f632432f05daa7c8`,
   `main` branch) — a Django 5.2 + DRF + Celery/Redis + Angular document
   management system. This was an explicit choice to discard the Node
   stack and use paperless-ngx's actual codebase as the base, not just a
   bolt-on service or an architecture reference (both were offered and
   declined). Neither prior architecture is deleted — both are kept
   intact under `legacy/` and `legacy-v1/` for reference.

**This repository is GPL-3.0-licensed** (`LICENSE`, paperless-ngx's own
license) as a direct consequence of that choice. This is a real, material
change from the previously-unlicensed root — read `LICENSE` before treating
any part of `src/` or `src-ui/` as usable under different terms.

```
src/            Django 5.2 + DRF backend, vendored from paperless-ngx —
                document management, OCR ingestion, tagging, full-text
                search (tantivy), Celery task queue.

src/rentshield/ The tenancy-notice domain logic, added as a first-party
                Django app alongside paperless-ngx's own `documents` and
                `paperless_mail` apps. Ported 1:1 (same statutory
                citations, same wording) from legacy-v1/shared/ — see
                "What's in rentshield/" below.

src-ui/         Angular frontend, vendored from paperless-ngx. Currently
                unmodified — the wizard/preview/chat-drawer/dashboard UI
                rebuild on top of it is not done yet (see "Not done yet").

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

## What's in `rentshield/`

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
- `models.py` — a `Notice` model (same fields as legacy-v1's `notices`
  SQLite table) with a `document` FK to paperless-ngx's own
  `documents.Document`.
- `services.py` — `generate_and_consume()` renders the PDF and hands it to
  paperless-ngx's own `documents.tasks.consume_file` task (the same one
  its own upload API uses), so every generated notice becomes a real,
  OCR'd, full-text-searchable `Document` — **this is the actual payoff of
  the rebase**, not a bolted-on file store.
- `service_methods.py` — the recognized/unrecognized notice-service
  methods under Article 25(3) (Notary Public, registered mail, court
  bailiff vs. WhatsApp, plain email, verbal, unwitnessed hand delivery),
  ported from `legacy-v1/shared/serviceMethods.js`.
- `citation_graph.py` — `build_citation_graph()`, an
  OpenContracts-inspired graph linking each notice-period clause and
  service-method mention found in a document to the specific Article 25
  provision it satisfies or violates, ported from
  `legacy-v1/shared/citationGraph.js`. Run automatically on every
  `POST /api/rentshield/documents/analyze/` call, against whichever
  engine (Docling/DeepSeek-OCR) extracted the text.
- `skills/*.md` + `skills.py` — the three-skill legal-guidance library
  (RDSC filing, security deposit disputes, valid notice service methods)
  ported from `legacy-v1/mcp/skills/` — same files, copied verbatim
  (plain Markdown + YAML frontmatter, no JS-specific content), reparsed
  with PyYAML instead of gray-matter. Exposed at
  `/api/rentshield/legal-skills/` (+ `/<id>/`) and
  `/api/rentshield/check-service-method/`, matching what the MCP server
  (`list_legal_skills`/`get_legal_skill`/
  `check_notice_service_method_validity`) exposed in `legacy-v1/`.
- `views.py` / `serializers.py` — a DRF `ViewSet` at
  `/api/rentshield/notices/`, plus `/api/rentshield/reasons/`,
  `/api/rentshield/pricing/`, `/api/rentshield/documents/analyze/`,
  `/api/rentshield/legal-skills/`, and
  `/api/rentshield/check-service-method/` — matching legacy-v1's
  equivalent routes.

**Verified**: `citation_graph.py` reproduces the exact same
violating/compliant/empty-document test cases used to verify the
original JS version; the legal-skills endpoints and citation-graph were
exercised through a real HTTP round trip (Django → docling-service →
`citation_graph.py` → back), not just unit-level.

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

Both are wired into `rentshield/document_analysis.py` and reachable via
`POST /api/rentshield/documents/analyze/`.

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
`POST /api/rentshield/notices/` renders a real PDF, hands it to
paperless-ngx's real consumption pipeline, produces a real OCR'd
`documents.Document` row, and that document is found by paperless-ngx's
own full-text search (`GET /api/documents/?query=...`) — both the
365-day statutory path and the 30-day breach path were tested this way,
including confirming the correct expiry-date math landed in the OCR'd
text.

`uv sync` deliberately excludes `torch`/`sentence-transformers`/
`llama-index-*` (paperless-ngx's `paperless_ai` semantic-search feature,
not wired into `INSTALLED_APPS` by default) — this project's sandbox
cannot reach `download.pytorch.org`'s wheel host. Re-add them from
upstream paperless-ngx's `pyproject.toml` for a deployment that wants
that feature.

## Not done yet (named, not silently skipped)

- **Auth wiring**: `NoticeViewSet` is `AllowAny` for now. paperless-ngx's
  own auth (django-allauth, DRF token auth, django-guardian object
  permissions) is fully present and unmodified — wiring `rentshield`
  into it is next, not forgotten.
- **E-signature**: `legacy-v1/api/src/services/esign/`'s DocuSeal + OpenSign
  integration (the real notarization workflow behind the "Notarization
  Service" add-on) has not yet been ported onto this foundation. Its
  Python port would live in `rentshield/` alongside what's here, backed
  by the same `Notice` → `Document` relation. (Legal-skills and the
  citation-graph analyzer — the other two items previously listed here —
  are now ported; see "What's in `rentshield/`" above.)
- **Frontend**: `src-ui/` is paperless-ngx's own Angular app, unmodified.
  The wizard, live bilingual preview, chat drawer, and dashboard from
  `legacy-v1/vue/` have not been rebuilt as Angular components — this is
  the largest remaining piece of the rebase and needs its own scoped pass
  rather than being rushed alongside the backend work above.
