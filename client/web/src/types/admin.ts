//  Admin area domain types + DTOs.
//
//  Product role model (as requested) vs the backend auth model:
//    UserRole.USER        ↔ "farmer"
//    UserRole.EXPERT      ↔ "agronomist"
//    UserRole.ADMIN       ↔ "admin"
//    UserRole.SUPER_ADMIN ↔ (no backend equivalent yet — TODO(backend): add role)
//
//  The backend `users` table (auth service) only stores farmer/agronomist/admin
//  today and exposes NO admin CRUD. The DTOs below define the contract the admin
//  router must implement (see lib/admin-api.ts TODO(backend) notes).

export enum UserRole {
  USER = "USER",
  EXPERT = "EXPERT",
  ADMIN = "ADMIN",
  SUPER_ADMIN = "SUPER_ADMIN",
}

/** Backend auth role strings actually stored in PostgreSQL. */
export type BackendRole = "farmer" | "agronomist" | "admin";

export type UserStatus = "active" | "locked" | "deleted";

export interface AdminUser {
  id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  role: BackendRole;
  status: UserStatus;
  created_at: string;
  last_login_at?: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;       // 1-based
  page_size: number;
}

export type UserSort = "newest" | "oldest" | "name" | "last_login";

export interface UserFilters {
  search: string;
  role: BackendRole | "all";
  status: UserStatus | "all";
  sort: UserSort;
  page: number;
  page_size: number;
}

/** DTO for creating a user. */
export interface CreateUserDto {
  username: string;
  password: string;
  email?: string | null;
  phone?: string | null;
  full_name?: string | null;
  role: BackendRole;
}

/** DTO for editing a user (partial). */
export interface UpdateUserDto {
  email?: string | null;
  phone?: string | null;
  full_name?: string | null;
  role?: BackendRole;
}

//  Expert management

export interface ExpertProfile {
  id: string;
  name: string;
  online: boolean;
  handled_cases: number;
  completion_rate: number;        // 0..1
  avg_response_minutes: number | null;
  rating: number | null;          // 0..5
  crops: string[];                // assigned crop specialties
  regions: string[];              // assigned geographic regions
}

//  Analytics / KPIs

export interface AdminKpis {
  total_users: number;
  new_today: number;
  new_week: number;
  new_month: number;
  dau: number;
  wau: number;
  mau: number;
  retention_rate: number | null;  // 0..1
  churn_rate: number | null;      // 0..1
  total_feedback: number;
  total_images: number;
  total_ai_analyses: number;
  total_expert_responses: number;
}

export interface UserGrowthPoint {
  date: string;
  new_users: number;
  active_users: number;
  returning_users: number;
}

export interface ConfidenceBucket {
  bucket: string;   // e.g. "0.9-1.0"
  count: number;
}

export interface RegionCount {
  region: string;
  count: number;
}

//  System monitoring

export interface ServiceHealth {
  name: string;
  status: "up" | "down" | "degraded" | "unknown";
  elapsed_ms?: number | null;
  detail?: string | null;
}

export interface SystemMetrics {
  api_requests_total?: number | null;
  avg_response_ms?: number | null;
  error_rate?: number | null;      // 0..1
  queue_jobs?: number | null;
  storage_used_bytes?: number | null;
  storage_total_bytes?: number | null;
  services: ServiceHealth[];
}

//  Audit

export interface AuditLog {
  id: string;
  actor_id: string;
  actor_name?: string | null;
  action: string;             // e.g. "user.lock", "user.role_change"
  target?: string | null;     // affected entity id
  timestamp: string;
  ip?: string | null;
  user_agent?: string | null;
  before?: unknown;
  after?: unknown;
}

export interface AuditFilters {
  search: string;
  action: string | "all";
  page: number;
  page_size: number;
}

//  Notifications

export type NotificationAudience = "all" | "experts" | "group";

export interface NotificationDraft {
  title: string;
  body: string;
  audience: NotificationAudience;
  /** role/group key when audience === "group" (e.g. a BackendRole). */
  group?: string | null;
}

//  Reports

export interface ModelRun {
  model: string;
  run_id?: string | null;
  start_time?: number | null;   // epoch ms
  test_macro_f1?: number | null;
  test_acc?: number | null;
  val_acc?: number | null;
}

export interface RetrainResult {
  dag_run_id?: string | null;
  state?: string | null;
}

export type ReportType =
  | "user"
  | "expert"
  | "feedback"
  | "disease_trend"
  | "ai_performance";

export type ReportFormat = "csv" | "excel" | "pdf";
