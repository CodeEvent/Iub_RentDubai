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
or license carry over here. Everything in `api/`, `vue/`, `mcp/`, and
`shared/` is original to this project.

```
shared/     Single source of truth for the legal logic: statutory reasons,
            RERA date math (365-day / 30-day), and the bilingual notice
            templates. Imported by api/, vue/, and mcp/ as a workspace
            package (@rentshield/shared) so the legal text and date rules
            can never drift between the three.

api/        Express + Node's built-in SQLite (node:sqlite — no external
            database to install). CRUD for saved notices, re-renders the
            bilingual document from shared/ on every read.

vue/        Vue 3 + Vite + Pinia + Tailwind v4. The wizard + live bilingual
            preview, ported from the original single-file prototype
            (legacy/index.html) onto this real frontend.

mcp/        A real MCP (Model Context Protocol) server — calculate_notice_
            expiry, draft_eviction_notice, list_statutory_reasons — the
            actual integration point the prototype's chat panel only
            simulated locally. Any MCP client (Claude Desktop, Claude Code)
            can attach to it over stdio.

docker/     Dockerfiles + compose for the api and vue services.

install/    seed.js — seeds the local SQLite database with example notices.

legacy/     The original single-file HTML/CSS/JS prototype this platform
            was rebuilt from. Kept for reference; not part of the build.
```

## Running it locally

```bash
npm install                 # installs all workspaces (shared/api/vue/mcp)
npm run seed                # optional: seed example notices
npm run dev:api              # http://localhost:4000
npm run dev:vue              # http://localhost:5173 (proxies /api -> :4000)
```

To run the MCP server standalone (e.g. to attach it to Claude Desktop):

```bash
npm run dev:mcp
```

Or with Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## What's ported from the prototype vs. not yet

**Ported to the new architecture:** the 4-step wizard, the full bilingual
(EN/AR) document for both notice types, the 365-day/30-day date engine, the
reason-specific compliance warnings, the pre-payment blur, and real
persistence via the API (replacing the single-file version's in-browser-only
state).

**Not yet ported** — the prototype (`legacy/index.html`) still has these,
and they're the natural next slice of work: the RentShield AI chat drawer
(text intake + drag-and-drop document upload), the simulated Stripe paywall
modal, and the mobile/PWA polish (safe-area insets, install manifest,
favicon). The `mcp/` server is a real head start on the chat panel's actual
brains — it exposes the same notice-drafting logic as callable tools instead
of the prototype's local simulation.

**Known limitation:** the production Docker build serves `vue/` as a static
bundle, which doesn't proxy `/api/*` the way the Vite dev server does — a
production deployment needs a reverse proxy or a configurable API base URL
before `docker compose up` is a real one-command deploy.
