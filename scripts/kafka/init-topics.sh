#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  kafka/init-topics.sh
#
#  Tạo 3 Kafka topic cần thiết cho VietCropDoctor.
#  An toàn khi chạy nhiều lần — dùng --if-not-exists.
#
#  Usage:
#    ./scripts/kafka/init-topics.sh
#    KAFKA_CONTAINER=my-kafka PARTITIONS=6 ./scripts/kafka/init-topics.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-vcd-kafka}"
BOOTSTRAP="${BOOTSTRAP:-kafka:29092}"
PARTITIONS="${PARTITIONS:-3}"
REPLICATION="${REPLICATION:-1}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }

TOPICS=(
  "disease.detected"    # Vision-AI publishes → Analytics consumes
  "chat.requested"      # RAG Engine publishes → Analytics consumes
  "retrain.requested"   # Airflow ETL publishes → MLOps pipeline consumes
)

echo ""
echo "=== Kafka Topic Initialisation ==="
echo "  Container  : $KAFKA_CONTAINER"
echo "  Bootstrap  : $BOOTSTRAP"
echo "  Partitions : $PARTITIONS | Replication: $REPLICATION"
echo ""

if ! docker inspect --format='{{.State.Status}}' "$KAFKA_CONTAINER" 2>/dev/null | grep -q running; then
  echo -e "${RED}ERROR:${NC} Container '$KAFKA_CONTAINER' is not running."
  echo "Run: docker compose up -d kafka"
  exit 1
fi

created=0; skipped=0; failed=0

for topic in "${TOPICS[@]}"; do
  existing=$(docker exec "$KAFKA_CONTAINER" \
    kafka-topics --bootstrap-server "$BOOTSTRAP" --list 2>/dev/null | grep -x "$topic" || true)

  if [ -n "$existing" ]; then
    warn "$topic already exists — skipping"
    skipped=$((skipped + 1))
    continue
  fi

  if docker exec "$KAFKA_CONTAINER" \
    kafka-topics \
      --bootstrap-server "$BOOTSTRAP" \
      --create \
      --if-not-exists \
      --topic "$topic" \
      --partitions "$PARTITIONS" \
      --replication-factor "$REPLICATION" \
    > /dev/null 2>&1; then
    ok "$topic (partitions=$PARTITIONS)"
    created=$((created + 1))
  else
    fail "$topic"
    failed=$((failed + 1))
  fi
done

echo ""
echo "=== Summary: created=$created  skipped=$skipped  failed=$failed ==="

if [ "$failed" -gt 0 ]; then
  exit 1
fi

echo ""
echo "=== Topics hiện tại ==="
docker exec "$KAFKA_CONTAINER" \
  kafka-topics --bootstrap-server "$BOOTSTRAP" --list \
  | grep -v "^__" \
  | sort \
  | sed 's/^/  /'
echo ""
