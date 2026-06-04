FROM python:3.11-slim

WORKDIR /app

# System deps for PyMuPDF and OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HF_ENDPOINT=https://hf-mirror.com
ENV FASTEMBED_CACHE_PATH=/app/data/fastembed_cache

RUN mkdir -p /app/data/uploads /app/data/fastembed_cache /app/data/qdrant

EXPOSE 9090

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9090"]
