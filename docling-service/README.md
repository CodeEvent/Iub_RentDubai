# docling-service

A small FastAPI wrapper around [Docling](https://github.com/docling-project/docling)
(IBM / LF AI & Data Foundation, MIT license) — structured document
parsing (layout, reading order, table structure) for uploaded tenancy
contracts, as an isolated Python service so its torch/transformers
dependency tree doesn't bloat the main paperless-ngx venv (same reason
`ocr/` was its own service in `legacy-v1/`).

See `../src/rentshield/README.md` (or the root README) for how this
plugs into rentshield.
