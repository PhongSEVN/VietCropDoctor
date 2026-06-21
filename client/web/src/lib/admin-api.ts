//  Admin service layer.
//
//  Talks to the gateway (DOMAIN → Nginx :8000). The gateway already enforces RBAC
//  for admin routes via `auth_request /auth-validate-admin` (see
//  backend/services/gateway/conf.d/routes.conf). The frontend RoleRoute gates the
//  UI; the gateway+auth service enforce it server-side.
//
//  REAL endpoints reused here:
//    - GET /api/services           → health aggregator (System Monitoring)
//    - GET /analytics/*            → ClickHouse analytics (agronomist+admin)
//  Everything under /api/admin/* is a CONTRACT the backend must implement; each is
//  annotated TODO(backend). No mock data is returned — missing endpoints surface
//  as explicit error/empty states in the UI.
import type {
  AdminKpis,
  AdminUser,
  AuditFilters,
  AuditLog,
  BackendRole,
  ConfidenceBucket,
  CreateUserDto,
  ExpertProfile,
  ModelRun,
  NotificationDraft,
  RetrainResult,
  Paginated,
  RegionCount,
  ReportFormat,
  ReportType,
  ServiceHealth,
  SystemMetrics,
  UpdateUserDto,
  UserFilters,
  UserGrowthPoint,
} from "@/types/admin";
import { UserRole } from "@/types/admin";

import { DOMAIN } from "@/constants/domain";
import { getStoredToken } from "@/lib/auth";

const BASE_URL = DOMAIN;

function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Parse a JSON response defensively. When the backend route does not exist the
 * dev server / SPA fallback returns index.html (Content-Type text/html), which
 * would otherwise blow up as "Unexpected token '<'". Surface a clear message
 * instead so the UI can explain the endpoint is not implemented yet.
 */
async function parseJson<T>(res: Response, verb: string): Promise<T> {
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      res.status === 404 || res.ok
        ? "Backend chưa cài endpoint này (server trả HTML thay vì JSON)."
        : `${verb} thất bại (${res.status})`,
    );
  }
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `${verb} thất bại (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  return parseJson<T>(res, "Yêu cầu");
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parseJson<T>(res, "Thao tác");
}

// Role mapping (product - backend)

const PRODUCT_TO_BACKEND: Record<UserRole, BackendRole | null> = {
  [UserRole.USER]: "farmer",
  [UserRole.EXPERT]: "agronomist",
  [UserRole.ADMIN]: "admin",
  [UserRole.SUPER_ADMIN]: null, // TODO(backend): add a super_admin role to auth
};

const BACKEND_TO_PRODUCT: Record<BackendRole, UserRole> = {
  farmer: UserRole.USER,
  agronomist: UserRole.EXPERT,
  admin: UserRole.ADMIN,
};

export function toBackendRole(role: UserRole): BackendRole | null {
  return PRODUCT_TO_BACKEND[role];
}

export function toProductRole(role: BackendRole): UserRole {
  return BACKEND_TO_PRODUCT[role];
}

export const ROLE_LABELS: Record<BackendRole, string> = {
  farmer: "Người dùng",
  agronomist: "Chuyên gia",
  admin: "Quản trị viên",
};

// User management

function buildUserQuery(f: UserFilters): string {
  const p = new URLSearchParams({
    page: String(f.page),
    page_size: String(f.page_size),
    sort: f.sort,
  });
  if (f.search.trim()) p.set("search", f.search.trim());
  if (f.role !== "all") p.set("role", f.role);
  if (f.status !== "all") p.set("status", f.status);
  return p.toString();
}

/**
 * TODO(backend): GET /api/admin/users?search=&role=&status=&sort=&page=&page_size=
 *   role: admin. Returns Paginated<AdminUser> from the `users` table. Add columns
 *   status (active|locked|deleted), last_login_at, full_name to the table.
 */
export function listUsers(filters: UserFilters): Promise<Paginated<AdminUser>> {
  return get<Paginated<AdminUser>>(`/api/admin/users?${buildUserQuery(filters)}`);
}

/** TODO(backend): POST /api/admin/users (CreateUserDto) → AdminUser. Audited. */
export function createUser(dto: CreateUserDto): Promise<AdminUser> {
  return send<AdminUser>("/api/admin/users", "POST", dto);
}

/** TODO(backend): PATCH /api/admin/users/{id} (UpdateUserDto) → AdminUser. Audited. */
export function updateUser(id: string, dto: UpdateUserDto): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}`, "PATCH", dto);
}

/** TODO(backend): PATCH /api/admin/users/{id} { role } → AdminUser. Audited (role_change). */
export function changeUserRole(id: string, role: BackendRole): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}`, "PATCH", { role });
}

/** TODO(backend): POST /api/admin/users/{id}/lock → AdminUser. Audited. */
export function lockUser(id: string): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}/lock`, "POST");
}

/** TODO(backend): POST /api/admin/users/{id}/unlock → AdminUser. Audited. */
export function unlockUser(id: string): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}/unlock`, "POST");
}

/** TODO(backend): DELETE /api/admin/users/{id} → soft delete (status='deleted'). Audited. */
export function softDeleteUser(id: string): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}`, "DELETE");
}

/** TODO(backend): POST /api/admin/users/{id}/restore → AdminUser (status='active'). Audited. */
export function restoreUser(id: string): Promise<AdminUser> {
  return send<AdminUser>(`/api/admin/users/${id}/restore`, "POST");
}

// Expert management

/** TODO(backend): GET /api/admin/experts → ExpertProfile[] (join feedback/expert_responses). */
export function listExperts(): Promise<ExpertProfile[]> {
  return get<ExpertProfile[]>("/api/admin/experts");
}

/** TODO(backend): POST /api/admin/experts/{id}/assign { crops, regions } → ExpertProfile. Audited. */
export function assignExpert(id: string, crops: string[], regions: string[]): Promise<ExpertProfile> {
  return send<ExpertProfile>(`/api/admin/experts/${id}/assign`, "POST", { crops, regions });
}

/** TODO(backend): POST /api/admin/experts { user_id } → promote a user to agronomist. Audited. */
export function addExpert(userId: string): Promise<ExpertProfile> {
  return send<ExpertProfile>("/api/admin/experts", "POST", { user_id: userId });
}

/** TODO(backend): DELETE /api/admin/experts/{id} → demote agronomist → farmer. Audited. */
export function removeExpert(id: string): Promise<{ ok: boolean }> {
  return send<{ ok: boolean }>(`/api/admin/experts/${id}`, "DELETE");
}

// Analytics / KPIs

/**
 * TODO(backend): GET /api/admin/kpis → AdminKpis. Aggregates PostgreSQL (user counts)
 * + ClickHouse (DAU/WAU/MAU, feedback, images, ai analyses, expert responses).
 */
export function getAdminKpis(): Promise<AdminKpis> {
  return get<AdminKpis>("/api/admin/kpis");
}

/** TODO(backend): GET /api/admin/analytics/user-growth?days= → UserGrowthPoint[] (ClickHouse). */
export function getUserGrowth(days = 30): Promise<UserGrowthPoint[]> {
  return get<UserGrowthPoint[]>(`/api/admin/analytics/user-growth?days=${days}`);
}

/** TODO(backend): GET /api/admin/analytics/confidence-distribution → ConfidenceBucket[]. */
export function getConfidenceDistribution(): Promise<ConfidenceBucket[]> {
  return get<ConfidenceBucket[]>("/api/admin/analytics/confidence-distribution");
}

/** TODO(backend): GET /api/admin/analytics/regions → RegionCount[] (needs region capture at upload). */
export function getRegionDistribution(): Promise<RegionCount[]> {
  return get<RegionCount[]>("/api/admin/analytics/regions");
}

// Model / Retrain

/** Latest MLflow run per model with metrics. REAL: GET /api/admin/models/runs. */
export function getModelRuns(): Promise<{ runs: ModelRun[] }> {
  return get<{ runs: ModelRun[] }>("/api/admin/models/runs");
}

/** Hot-swap: pull promoted weights into vision-ai and reload. POST /api/admin/models/reload. */
export function reloadServingModel(): Promise<Record<string, unknown>> {
  return send<Record<string, unknown>>("/api/admin/models/reload", "POST");
}

/** Trigger the Airflow retrain DAG. POST /api/admin/retrain { model? }. */
export function triggerRetrain(model?: string): Promise<RetrainResult> {
  return send<RetrainResult>("/api/admin/retrain", "POST", { model: model ?? null });
}

// System monitoring

interface RawServiceEntry {
  status?: string;
  elapsed_ms?: number;
  error?: string;
}
interface RawServicesHealth {
  status?: string;
  gateway?: string;
  services?: Record<string, RawServiceEntry>;
  checked_at?: string;
  total_ms?: number;
}

/**
 * REAL: GET /api/services (gateway → health_aggregator sidecar). Adapted into the
 * SystemMetrics shape. Per-host CPU/RAM/storage are not exposed by the aggregator
 * yet — TODO(backend): extend /api/services (or add /api/admin/metrics) with
 * api_requests_total, error_rate, queue_jobs, storage usage from Prometheus.
 */
export async function getSystemMetrics(): Promise<SystemMetrics> {
  const raw = await get<RawServicesHealth>("/api/services");
  const services: ServiceHealth[] = [];

  if (raw.gateway) {
    services.push({ name: "gateway", status: raw.gateway === "up" ? "up" : "down" });
  }
  for (const [name, entry] of Object.entries(raw.services ?? {})) {
    services.push({
      name,
      status: entry.status === "up" ? "up" : entry.status === "down" ? "down" : "unknown",
      elapsed_ms: entry.elapsed_ms ?? null,
      detail: entry.error ?? null,
    });
  }

  return {
    api_requests_total: null,
    avg_response_ms: raw.total_ms ?? null,
    error_rate: null,
    queue_jobs: null,
    storage_used_bytes: null,
    storage_total_bytes: null,
    services,
  };
}

// Audit logs

function buildAuditQuery(f: AuditFilters): string {
  const p = new URLSearchParams({ page: String(f.page), page_size: String(f.page_size) });
  if (f.search.trim()) p.set("search", f.search.trim());
  if (f.action !== "all") p.set("action", f.action);
  return p.toString();
}

/** TODO(backend): GET /api/admin/audit?search=&action=&page=&page_size= → Paginated<AuditLog>. */
export function listAuditLogs(filters: AuditFilters): Promise<Paginated<AuditLog>> {
  return get<Paginated<AuditLog>>(`/api/admin/audit?${buildAuditQuery(filters)}`);
}

/**
 * Record an admin action in the audit trail. Best-effort: a logging failure must
 * never block the action it describes.
 *
 * TODO(backend): POST /api/admin/audit { action, target?, before?, after? }. The
 * server stamps actor_id (from JWT), timestamp, ip, user_agent. EVERY mutating
 * admin endpoint should also write its own server-side audit row as the source
 * of truth; this client call covers UI-initiated context.
 */
export async function logAudit(action: string, target?: string, before?: unknown, after?: unknown): Promise<void> {
  try {
    await send("/api/admin/audit", "POST", { action, target, before, after });
  } catch {
    // swallow — auditing must not break the user action
  }
}

// Notifications

/** TODO(backend): POST /api/admin/notifications (NotificationDraft) → { sent: number }. Audited. */
export function sendNotification(draft: NotificationDraft): Promise<{ sent: number }> {
  return send<{ sent: number }>("/api/admin/notifications", "POST", draft);
}

// Reports

/**
 * TODO(backend): GET /api/admin/reports/{type}?format=csv|excel|pdf → file stream.
 * Returns the download URL the browser can open. Until implemented, the client can
 * still export CSV locally from already-loaded table data via downloadCsv().
 */
export function reportDownloadUrl(type: ReportType, format: ReportFormat): string {
  return `${BASE_URL}/api/admin/reports/${type}?format=${format}`;
}

// CSV export (client-side, no backend needed)

/** Serialise rows of records to a CSV string. */
export function toCsv(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.join(",")];
  for (const row of rows) lines.push(headers.map((h) => escape(row[h])).join(","));
  return lines.join("\n");
}

/** Trigger a browser download of a CSV built from rows. */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  const blob = new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
