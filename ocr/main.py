"""RentShield OCR service.

A thin FastAPI wrapper around PaddleOCR (https://github.com/PaddlePaddle/PaddleOCR)
that turns an uploaded tenancy-contract addendum (image, PDF, or plain text
export) into extracted text for api/ to run compliance analysis against.

The OCR model is loaded lazily on first request, not at process start, so
`/health` responds immediately and the (~sizeable) model download only
happens when the endpoint is actually used. Models are cached under
PADDLE_OCR_HOME (or PaddleOCR's own default, ~/.paddlex) after the first
successful request.
"""
import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="RentShield OCR")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt"}

_ocr_engine = None


def get_ocr_engine():
    """Lazily constructs and caches the PaddleOCR pipeline.

    Deferred import + construction: importing paddleocr/paddlepaddle is
    itself not free, and constructing PaddleOCR() triggers the model
    download on first use — neither should happen just because the
    service booted.
    """
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang="en",
        )
    return _ocr_engine


class ExtractedLine(BaseModel):
    text: str
    confidence: float


class ExtractResponse(BaseModel):
    text: str
    lines: list[ExtractedLine]
    source: str  # "ocr" | "text"


@app.get("/health")
def health():
    return {"status": "ok", "service": "rentshield-ocr", "model_loaded": _ocr_engine is not None}


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
        return ExtractResponse(text=text, lines=lines, source="text")

    if ext not in IMAGE_EXTENSIONS and ext not in PDF_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or 'unknown'}'. Upload an image (png/jpg), a PDF, or a .txt export.",
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext or ".png", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        ocr = get_ocr_engine()
        results = ocr.predict(tmp_path)

        lines: list[ExtractedLine] = []
        for page in results:
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            for text, score in zip(texts, scores):
                if text.strip():
                    lines.append(ExtractedLine(text=text, confidence=round(float(score), 4)))

        full_text = "\n".join(l.text for l in lines)
        return ExtractResponse(text=full_text, lines=lines, source="ocr")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller, not swallowed
        raise HTTPException(502, f"OCR processing failed: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
