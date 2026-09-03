"""FastAPI wrapper around Docling (github.com/docling-project/docling) —
structured document conversion (layout, reading order, table structure)
for uploaded tenancy contracts, called by
rentshield/services.py::analyze_document(). Model construction is lazy
(only happens on the first real /convert call), same pattern as
legacy-v1/ocr/main.py, so /health responds instantly even before any
model weights are loaded.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="docling-service")

_converter = None


def get_converter():
    """Lazily builds the DocumentConverter, pinned to Tesseract for OCR
    (already installed system-wide for paperless-ngx's own consumption
    pipeline — see the root README) rather than docling's default OCR
    engine, which otherwise tries to fetch PP-OCRv6 weights from
    ModelScope at runtime — a host this project's sandbox cannot reach,
    same class of block as everywhere else ML weights come from a
    non-PyPI host in this project. Tesseract avoids that specific
    failure; it does NOT avoid docling's own layout/table-structure
    models, which are only on HuggingFace and have no pip-bundled
    alternative — see the root README's Docling section for exactly
    what is and isn't verified in this environment.
    """
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = TesseractCliOcrOptions()

        _converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
    return _converter


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _converter is not None}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload").suffix or ".pdf"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            converter = get_converter()
            result = converter.convert(tmp.name)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
            raise HTTPException(status_code=422, detail=f"Docling conversion failed: {exc}") from exc

    doc = result.document
    tables = [
        {
            "caption": table.caption_text(doc) if hasattr(table, "caption_text") else None,
            "num_rows": table.data.num_rows if table.data else None,
            "num_cols": table.data.num_cols if table.data else None,
        }
        for table in doc.tables
    ]

    return {
        "source": "docling",
        "markdown": doc.export_to_markdown(),
        "text": doc.export_to_text(),
        "num_pages": len(doc.pages) if doc.pages else None,
        "tables": tables,
    }
