// Resolved at build time from the VITE_API_URL env variable.
// In dev: set VITE_API_URL="" in .env.local → empty base URL → Vite proxy handles routing.
// In prod: set VITE_API_URL=https://your-domain.com
export const DOMAIN: string =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";
