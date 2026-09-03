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

docker/         paperless-ngx's own Docker Compose files (sqlite/postgres/
                mariadb variants, with/without Tika).

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
- `views.py` / `serializers.py` — a DRF `ViewSet` at
  `/api/rentshield/notices/`, plus `/api/rentshield/reasons/` and
  `/api/rentshield/pricing/`, matching legacy-v1's `/api/notices` /
  `/api/reasons` / `/api/pricing` behavior.

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
- **E-signature, legal-skills, citation-graph**: `legacy-v1/`'s DocuSeal +
  OpenSign integration, `mcp/skills/` library, and citation-graph
  analyzer are real, working, previously-verified features that have not
  yet been ported onto this foundation. Their Python ports would live in
  `rentshield/` alongside what's here, backed by the same `Notice` →
  `Document` relation.
- **Frontend**: `src-ui/` is paperless-ngx's own Angular app, unmodified.
  The wizard, live bilingual preview, chat drawer, and dashboard from
  `legacy-v1/vue/` have not been rebuilt as Angular components — this is
  the largest remaining piece of the rebase and needs its own scoped pass
  rather than being rushed alongside the backend work above.
