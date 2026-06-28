# Build context: backend/
# docker build -t vcd-orchestrator -f services/ai/orchestrator/Dockerfile .
FROM python:3.11-slim

WORKDIR /service

COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared

COPY services/ai/orchestrator/requirements.txt ./requirements.txt
RUN grep -v "^-e " requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY services/ai/orchestrator/ .

EXPOSE 8006

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
