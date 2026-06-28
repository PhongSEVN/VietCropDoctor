// Resolved at build time from the VITE_API_URL env variable.
// In dev: set VITE_API_URL="" in .env.local → empty base URL → Vite proxy handles routing.
// In prod: set VITE_API_URL=https://your-domain.com
export const DOMAIN: string =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Grafana base URL for embedded observability dashboards (separate origin :3001).
// Anonymous Viewer access is enabled in docker-compose, so iframes need no login.
export const GRAFANA_URL: string =
  import.meta.env.VITE_GRAFANA_URL ?? "http://localhost:3001";

// Training observability UIs (opened in a new tab from the admin Model & Retrain tab).
// Airflow = live pipeline progress + per-task logs; MLflow = training metrics per run.
export const AIRFLOW_URL: string =
  import.meta.env.VITE_AIRFLOW_URL ?? "http://localhost:8090";
export const MLFLOW_URL: string =
  import.meta.env.VITE_MLFLOW_URL ?? "http://localhost:5000";
