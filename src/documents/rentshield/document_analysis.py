# Calls the two optional document-parsing services — docling-service/
# (structured layout/table parsing, github.com/docling-project/docling)
# and deepseek-ocr-service/ (GPU-only high-accuracy OCR for hard scans,
# github.com/deepseek-ai/DeepSeek-OCR) — for the "AI Compliance Review"
# add-on's document upload. Docling is primary: it's CPU-friendly and
# handles most uploads (text-native PDFs, DOCX, images with clean text).
# DeepSeek-OCR is opt-in, not an automatic fallback — it needs a real GPU
# deployment, so silently retrying every failure against it would hang
# or fail again on CPU-only infrastructure. See the root README for
# exactly what's verified vs. GPU/network-constrained in this sandbox.
from __future__ import annotations

import os

import requests

DOCLING_SERVICE_URL = os.environ.get("DOCLING_SERVICE_URL", "http://localhost:8010")
DEEPSEEK_OCR_SERVICE_URL = os.environ.get("DEEPSEEK_OCR_SERVICE_URL", "http://localhost:8011")
DEEPSEEK_OCR_ENABLED = os.environ.get("DEEPSEEK_OCR_ENABLED", "false").lower() == "true"


class DocumentAnalysisError(Exception):
    pass


def _call_service(base_url: str, path: str, service_name: str, filename: str, content: bytes, content_type: str, timeout: int) -> dict:
    try:
        res = requests.post(
            f"{base_url}{path}",
            files={"file": (filename, content, content_type)},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise DocumentAnalysisError(f"{service_name} unavailable: {exc}") from exc

    if not res.ok:
        detail = res.json().get("detail", res.text) if res.headers.get("content-type", "").startswith("application/json") else res.text
        raise DocumentAnalysisError(f"{service_name} returned {res.status_code}: {detail}")
    return res.json()


def analyze_document(filename: str, content: bytes, content_type: str, use_deepseek_ocr: bool = False) -> dict:
    """Returns {"engine": "docling"|"deepseek-ocr", "text": str, ...engine-specific fields}.

    use_deepseek_ocr=True routes to DeepSeek-OCR instead of Docling —
    the caller's choice (e.g. a "this scan is too poor quality" retry
    button), not an automatic fallback; see module docstring for why.
    """
    if use_deepseek_ocr:
        if not DEEPSEEK_OCR_ENABLED:
            raise DocumentAnalysisError(
                "DeepSeek-OCR is disabled (DEEPSEEK_OCR_ENABLED is not set) — it requires a "
                "CUDA GPU deployment of deepseek-ocr-service/, not available by default."
            )
        return _call_service(DEEPSEEK_OCR_SERVICE_URL, "/extract", "deepseek-ocr-service", filename, content, content_type, timeout=300)
    return _call_service(DOCLING_SERVICE_URL, "/convert", "docling-service", filename, content, content_type, timeout=120)
