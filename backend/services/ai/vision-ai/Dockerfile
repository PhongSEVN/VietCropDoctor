# Build context: backend/
# docker build -t vcd-vision-ai -f services/ai/vision-ai/Dockerfile .
FROM python:3.11-slim

WORKDIR /service

# Be resilient to slow/unstable networks (large ML wheels time out otherwise).
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1

# Install shared package first (cached layer)
COPY shared/ /shared/
RUN pip install -e /shared

# Install CPU-only PyTorch FIRST. The default PyPI torch bundles ~1 GB of CUDA
# wheels (triton, nvidia_cuda_*) that time out on slow links; serving runs fine on
# CPU. Installing it here means the requirements step finds torch already satisfied
# and never pulls the CUDA build. Swap to the cu124 index for GPU inference.
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install the remaining service dependencies
COPY services/ai/vision-ai/requirements.txt ./requirements.txt
RUN grep -v "^-e " requirements.txt | pip install -r /dev/stdin

# Copy service source
COPY services/ai/vision-ai/ .

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
