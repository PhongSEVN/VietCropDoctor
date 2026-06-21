//  Expert dashboard service layer.
//
//  Talks to the gateway (DOMAIN → Nginx :8000). The expert endpoints below do
//  NOT exist on the backend yet — they define the contract the backend must
//  implement. Each is annotated with TODO(backend) describing the route + shape.
//  No mock data is fabricated here: when an endpoint is missing the request
//  fails and the calling hook renders an explicit error/empty state.
//
//  Backend mapping (table `feedback` in rag-engine):
//    - Add columns: status, priority, assignee_id, sla_due_at, updated_at.
//    - Add tables : expert_responses, internal_notes (FK feedback.id).
//    - Add routes : an expert-scoped, role=agronomist|admin router that lists ALL
//                   users' feedback (the current GET /feedback is per-user only).

import type {
  ExpertCase,
  ExpertCaseFilters,
  ExpertResponseInput,
  ExpertStats,
  OnlineExpert,
} from "@/types/expert";

import { DOMAIN } from "@/constants/domain";
import { getStoredToken } from "@/lib/auth";
import { getCropName, getDiseaseName } from "@/lib/api";

const BASE_URL = DOMAIN;

function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Parse a JSON response defensively. A missing backend route makes the dev server
 * return index.html (text/html), which would crash JSON.parse with
 * "Unexpected token '<'". Convert that into a clear message instead.
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

async function expertGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  return parseJson<T>(res, "Yêu cầu");
}

async function expertSend<T>(path: string, method: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  return parseJson<T>(res, "Thao tác");
}

// Queue / list

/**
 * List all feedback cases for the expert queue.
 *
 * TODO(backend): GET /api/expert/cases?status=&crop=&search=&sort=&limit=
 *   role: agronomist | admin. Returns ExpertCase[] aggregated from `feedback`
 *   joined with expert_responses + internal_notes. Filtering MAY be done server
 *   side; this client also filters/sorts defensively (see useExpertQueue).
 */
export function getExpertQueue(limit = 200): Promise<ExpertCase[]> {
  return expertGet<ExpertCase[]>(`/api/expert/cases?limit=${limit}`);
}

/**
 * Full detail for one case (large image, related images, conversation, AI, history).
 *
 * TODO(backend): GET /api/expert/cases/{id} → ExpertCase (with responses[], notes[],
 *   conversation[], related_image_urls[]).
 */
export function getExpertCase(id: string): Promise<ExpertCase> {
  return expertGet<ExpertCase>(`/api/expert/cases/${id}`);
}

// Mutations

/**
 * Submit an expert response. When mark_completed=true the case status becomes
 * "answered" and, if `diagnosis` differs from the AI label, the verified image is
 * copied into the gold dataset (the R2 build_training_set.py loop picks it up).
 *
 * TODO(backend): POST /api/expert/cases/{id}/responses
 *   body: ExpertResponseInput → returns the updated ExpertCase.
 *   Side effects: insert expert_responses row; if mark_completed → set
 *   feedback.status='answered'; if diagnosis set → reuse feedback_minio
 *   copy_to_verified(image_url, diagnosis) so the gold label reaches vcd-verified.
 */
export function submitExpertResponse(id: string, input: ExpertResponseInput): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}/responses`, "POST", input);
}

/** TODO(backend): PATCH /api/expert/cases/{id} { status } → ExpertCase. */
export function updateCaseStatus(id: string, status: ExpertCase["status"]): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}`, "PATCH", { status });
}

/** TODO(backend): PATCH /api/expert/cases/{id} { priority } → ExpertCase. */
export function updateCasePriority(id: string, priority: ExpertCase["priority"]): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}`, "PATCH", { priority });
}

/** TODO(backend): POST /api/expert/cases/{id}/notes { note } → InternalNote (expert-only). */
export function addInternalNote(id: string, note: string): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}/notes`, "POST", { note });
}

/** TODO(backend): POST /api/expert/cases/{id}/assign { expert_id } → ExpertCase (handover). */
export function assignCase(id: string, expertId: string): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}/assign`, "POST", { expert_id: expertId });
}

/** Flag/unflag a case whose image is not a crop leaf (irrelevant / OOD). */
export function markCaseIrrelevant(id: string, irrelevant: boolean): Promise<ExpertCase> {
  return expertSend<ExpertCase>(`/api/expert/cases/${id}/irrelevant`, "POST", { irrelevant });
}

// Stats / presence

/**
 * Server-side aggregated KPIs. Optional: when absent the dashboard derives the
 * same shape client-side from the queue via deriveExpertStats().
 *
 * TODO(backend): GET /api/expert/stats → ExpertStats.
 */
export function getExpertStats(): Promise<ExpertStats> {
  return expertGet<ExpertStats>("/api/expert/stats");
}

/** TODO(backend): GET /api/expert/online → OnlineExpert[] (presence + active load). */
export function getOnlineExperts(): Promise<OnlineExpert[]> {
  return expertGet<OnlineExpert[]>("/api/expert/online");
}

// Client-side derivation

const DAY_MS = 24 * 60 * 60 * 1000;

/** Build the KPI/chart aggregate from the queue when /api/expert/stats is unavailable. */
export function deriveExpertStats(cases: ExpertCase[]): ExpertStats {
  const now = Date.now();
  const counts = { pending: 0, in_progress: 0, answered: 0 };
  const responseDeltas: number[] = [];
  let resolvedLast7 = 0;

  const byDay = new Map<string, number>();
  for (let i = 6; i >= 0; i--) {
    byDay.set(new Date(now - i * DAY_MS).toISOString().slice(0, 10), 0);
  }

  const diseaseCount = new Map<string, number>();
  const cropCount = new Map<string, number>();

  for (const c of cases) {
    counts[c.status] += 1;

    const day = c.created_at.slice(0, 10);
    if (byDay.has(day)) byDay.set(day, (byDay.get(day) ?? 0) + 1);

    const disease = c.current_diagnosis || c.ai.predicted_disease;
    if (disease) diseaseCount.set(disease, (diseaseCount.get(disease) ?? 0) + 1);
    const crop = c.crop || getCropName(disease);
    if (crop) cropCount.set(crop, (cropCount.get(crop) ?? 0) + 1);

    const firstReply = c.responses[0];
    if (firstReply) {
      const delta = new Date(firstReply.created_at).getTime() - new Date(c.created_at).getTime();
      if (delta >= 0) responseDeltas.push(delta);
      if (c.status === "answered" && now - new Date(firstReply.created_at).getTime() <= 7 * DAY_MS) {
        resolvedLast7 += 1;
      }
    }
  }

  const avgMs = responseDeltas.length
    ? responseDeltas.reduce((a, b) => a + b, 0) / responseDeltas.length
    : null;

  const top_diseases = [...diseaseCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([disease, count]) => ({ disease, count }));

  const top_crops = [...cropCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([crop, count]) => ({ crop, count }));

  return {
    total: cases.length,
    pending: counts.pending,
    in_progress: counts.in_progress,
    answered: counts.answered,
    avg_response_minutes: avgMs === null ? null : Math.round(avgMs / 60000),
    resolved_last7days: resolvedLast7,
    by_day: [...byDay.entries()].map(([date, count]) => ({ date, count })),
    top_diseases,
    top_crops,
  };
}

/** Apply search / status / crop filters and sort, client-side. */
export function applyCaseFilters(cases: ExpertCase[], f: ExpertCaseFilters): ExpertCase[] {
  const PRIORITY_RANK: Record<ExpertCase["priority"], number> = {
    urgent: 0, high: 1, normal: 2, low: 3,
  };
  const q = f.search.trim().toLowerCase();

  const filtered = cases.filter((c) => {
    if (f.status !== "all" && c.status !== f.status) return false;
    if (f.crop !== "all" && (c.crop || getCropName(c.ai.predicted_disease)) !== f.crop) return false;
    if (!q) return true;
    const hay = [
      c.user_name,
      c.problem_description,
      getDiseaseName(c.ai.predicted_disease),
      c.current_diagnosis,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });

  return filtered.sort((a, b) => {
    if (f.sort === "priority") {
      const d = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
      if (d !== 0) return d;
      return b.created_at.localeCompare(a.created_at);
    }
    return f.sort === "oldest"
      ? a.created_at.localeCompare(b.created_at)
      : b.created_at.localeCompare(a.created_at);
  });
}
