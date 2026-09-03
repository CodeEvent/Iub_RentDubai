"""FastAPI wrapper around DeepSeek-OCR
(github.com/deepseek-ai/DeepSeek-OCR, DeepSeek-OCR-hf/run_dpsk_ocr.py —
the transformers backend, not the higher-throughput vLLM one, to keep
this service simple to deploy) — offered as an optional high-accuracy
OCR backend for scans docling-service's layout parsing struggles with.

Model construction is lazy (only on the first real /extract call), same
pattern as docling-service and legacy-v1/ocr/main.py, so /health responds
instantly. Unlike those two, there is genuinely no CPU/no-GPU fallback
here — DeepSeek-OCR's own reference script calls `.cuda()`
unconditionally — so /extract fails clearly and immediately on a host
without CUDA, rather than hanging or silently degrading.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import torch
from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="deepseek-ocr-service")

MODEL_NAME = "deepseek-ai/DeepSeek-OCR"
# Base preset per DeepSeek-OCR's own documented presets (Tiny/Small/Base/
# Large/Gundam) — Base is their suggested default for general documents.
BASE_SIZE = 1024
IMAGE_SIZE = 1024
CROP_MODE = False

_model = None
_tokenizer = None


def get_model():
    global _model, _tokenizer
    if _model is None:
        if not torch.cuda.is_available():
            raise RuntimeError(
                "DeepSeek-OCR requires a CUDA GPU (model.eval().cuda() in "
                "its own reference implementation has no CPU fallback). "
                "No CUDA device is available in this environment."
            )
        from transformers import AutoModel, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        _model = AutoModel.from_pretrained(
            MODEL_NAME,
            _attn_implementation="flash_attention_2",
            trust_remote_code=True,
            use_safetensors=True,
        )
        _model = _model.eval().cuda().to(torch.bfloat16)
    return _model, _tokenizer


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "cuda_available": torch.cuda.is_available(),
    }


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    suffix = Path(file.filename or "upload").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        tmp_in.write(data)
        tmp_in.flush()
        try:
            model, tokenizer = get_model()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            # DeepSeek-OCR's own <|grounding|> prompt asks for a structured
            # markdown conversion with bounding-box grounding, matching
            # what run_dpsk_ocr.py's own example uses for documents.
            prompt = "<image>\n<|grounding|>Convert the document to markdown. "
            result_text = model.infer(
                tokenizer,
                prompt=prompt,
                image_file=tmp_in.name,
                output_path=tmp_out,
                base_size=BASE_SIZE,
                image_size=IMAGE_SIZE,
                crop_mode=CROP_MODE,
                save_results=False,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
            raise HTTPException(status_code=422, detail=f"DeepSeek-OCR inference failed: {exc}") from exc

    return {"source": "deepseek-ocr", "text": result_text}
