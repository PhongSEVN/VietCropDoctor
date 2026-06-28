# Build context: backend/
# docker build -t vcd-rag-engine -f services/ai/rag-engine/Dockerfile .
FROM python:3.11-slim

WORKDIR /service

# Install shared package first (cached layer)
COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared

# Install service dependencies
COPY services/ai/rag-engine/requirements.txt ./requirements.txt
RUN grep -v "^-e " requirements.txt | pip install --no-cache-dir -r /dev/stdin

# Copy service source
COPY services/ai/rag-engine/ .

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
