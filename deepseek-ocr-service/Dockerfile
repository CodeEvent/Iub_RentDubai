# Requires a CUDA-capable host and the NVIDIA Container Toolkit — see
# README.md. nvidia/cuda's runtime image (not devel) is enough since
# DeepSeek-OCR ships prebuilt wheels for its dependencies.
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    transformers==4.46.3 tokenizers==0.20.3 torch~=2.6.0 \
    pymupdf img2pdf einops easydict addict pillow numpy \
    fastapi~=0.115.6 "uvicorn[standard]~=0.34.0" python-multipart~=0.0.20

COPY main.py ./

EXPOSE 8011
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011"]
