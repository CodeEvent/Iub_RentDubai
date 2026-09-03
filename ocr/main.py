"""RentShield OCR service.

A thin FastAPI wrapper around the PP-OCRv4 models from PaddleOCR
(https://github.com/PaddlePaddle/PaddleOCR), run via RapidOCR's ONNX
export (https://github.com/RapidAI/RapidOCR) instead of the PaddlePaddle
framework directly. Same underlying detection/recognition models and
weights — RapidOCR just repackages them as ONNX + bundles the model files
directly inside the pip wheel, so there is no first-use download from an
external model hoster (HuggingFace/ModelScope/BOS) at all, which makes
this dramatically more reliable to deploy behind a firewall or in any
environment with restricted outbound network access.

Turns an uploaded tenancy-contract addendum (image, PDF, or plain text
export) into extracted text for api/ to run compliance analysis against.
"""
import io
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="RentShield OCR")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt"}

MAX_PDF_PAGES = 10  # a tenancy addendum is a few pages, not a novel

_ocr_engine = None


def get_ocr_engine():
    """Lazily constructs and caches the RapidOCR engine.

    Deferred import: importing onnxruntime/rapidocr is itself not free,
    and there's no reason to pay that cost just because the service
    booted rather than because someone actually uploaded a document.
    """
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


class ExtractedLine(BaseModel):
    text: str
    confidence: float


class ExtractResponse(BaseModel):
    text: str
    lines: list[ExtractedLine]
    source: str  # "ocr" | "text"
    pages: int = 1


@app.get("/health")
def health():
    return {"status": "ok", "service": "rentshield-ocr", "model_loaded": _ocr_engine is not None}


def _run_ocr_on_image_bytes(engine, image_bytes: bytes) -> list[ExtractedLine]:
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    result, _elapse = engine(arr)
    lines: list[ExtractedLine] = []
    if result:
        for _box, text, score in result:
            if text.strip():
                lines.append(ExtractedLine(text=text, confidence=round(float(score), 4)))
    return lines


def _render_pdf_pages_to_png_bytes(pdf_bytes: bytes) -> list[bytes]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page_count = min(len(pdf), MAX_PDF_PAGES)
        rendered = []
        for i in range(page_count):
            page = pdf[i]
            bitmap = page.render(scale=2.0)
            pil_img = bitmap.to_pil()
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            rendered.append(buf.getvalue())
        return rendered
    finally:
        pdf.close()


@app.post("/extract", response_model=ExtractResponse)
async def extract(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    data = await file.read()

    if not data:
        raise HTTPException(400, "Empty file upload")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File too large (15MB limit)")

    # Plain-text exports (e.g. a WhatsApp chat export) need no OCR at all.
    if ext in TEXT_EXTENSIONS or file.content_type == "text/plain":
        text = data.decode("utf-8", errors="replace")
        lines = [ExtractedLine(text=ln, confidence=1.0) for ln in text.splitlines() if ln.strip()]
        return ExtractResponse(text=text, lines=lines, source="text", pages=1)

    if ext not in IMAGE_EXTENSIONS and ext not in PDF_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or 'unknown'}'. Upload an image (png/jpg), a PDF, or a .txt export.",
        )

    try:
        engine = get_ocr_engine()

        if ext in PDF_EXTENSIONS:
            page_images = _render_pdf_pages_to_png_bytes(data)
        else:
            page_images = [data]

        all_lines: list[ExtractedLine] = []
        for page_bytes in page_images:
            all_lines.extend(_run_ocr_on_image_bytes(engine, page_bytes))

        full_text = "\n".join(l.text for l in all_lines)
        return ExtractResponse(text=full_text, lines=all_lines, source="ocr", pages=len(page_images))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller, not swallowed
        raise HTTPException(502, f"OCR processing failed: {exc}") from exc
