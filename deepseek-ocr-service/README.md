# deepseek-ocr-service

A FastAPI wrapper around [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR)
(DeepSeek AI, MIT license) — a vision-language OCR model, offered as an
optional high-accuracy alternative to `docling-service/` for low-quality
scans (handwriting, poor lighting, skewed photos of a physical tenancy
contract) where layout-only parsing struggles.

**Requires a CUDA GPU.** DeepSeek-OCR's own reference script
(`model.eval().cuda()`) has no CPU fallback, and its weights
(`deepseek-ai/DeepSeek-OCR` on Hugging Face, several GB) must be
downloaded from Hugging Face on first use. Neither is available in this
project's dev sandbox (no GPU, Hugging Face blocked by network policy)
— see the root README for exactly what is and isn't verified here.
Deploy this service only on GPU-equipped infrastructure.
