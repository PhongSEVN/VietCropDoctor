import os

JWT_SECRET    = os.getenv("JWT_SECRET", "change-me-in-production-use-64-char-random")
JWT_ALGORITHM = "HS256"

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST",     "clickhouse")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB",       "vietcropdoctor")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER",     "admin")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "secret")

BATCH_MAX_ROWS     = int(os.getenv("BATCH_MAX_ROWS",    "100"))
BATCH_FLUSH_SECS   = float(os.getenv("BATCH_FLUSH_SECS", "5"))

# Retrain loop: after this many new feedback events, publish retrain.requested.
# A dedicated consumer then triggers the Airflow DAG (documented Kafka → Airflow flow).
RETRAIN_FEEDBACK_THRESHOLD = int(os.getenv("RETRAIN_FEEDBACK_THRESHOLD", "50"))
AIRFLOW_URL       = os.getenv("AIRFLOW_URL",      "http://airflow:8080")
AIRFLOW_USERNAME  = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD  = os.getenv("AIRFLOW_PASSWORD", "")
RETRAIN_DAG       = os.getenv("RETRAIN_DAG",      "retrain_classifier")

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
