FROM python:3.11-slim
WORKDIR /app

# Docling's fallback OCR path (TesseractCliOcrOptions, see main.py) shells
# out to the tesseract binary.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir docling~=2.0 fastapi~=0.115.6 "uvicorn[standard]~=0.34.0" python-multipart~=0.0.20

COPY main.py ./

EXPOSE 8010
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
