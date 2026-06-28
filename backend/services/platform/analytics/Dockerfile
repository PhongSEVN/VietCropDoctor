# Build context: backend/
# docker build -t vcd-analytics -f services/platform/analytics/Dockerfile .
FROM python:3.11-slim

WORKDIR /service

COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared

COPY services/platform/analytics/requirements.txt ./requirements.txt
RUN grep -v "^-e " requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY services/platform/analytics/ .

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
