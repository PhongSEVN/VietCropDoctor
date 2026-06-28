import type {
  AlertItem,
  AnalyticsSummary,
  ChatResponse,
  Citation,
  CropDistributionItem,
  DiagnoseResult,
  FeedbackItem,
  FeedbackRequest,
  FeedbackResponse,
  HealthStatus,
  OrchestrationResponse,
  PredictResult,
  QueryResponse,
  Recommendation,
  RetrievedChunk,
  SeverityBreakdownItem,
  SourceLink,
  TrendResponse,
} from "@vcd/types";

import { DOMAIN } from "@/constants/domain";
import { getStoredToken } from "@/lib/auth";

function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export type {
  AlertItem,
  AnalyticsSummary,
  ChatResponse,
  Citation,
  CropDistributionItem,
  DiagnoseResult,
  FeedbackItem,
  FeedbackRequest,
  FeedbackResponse,
  HealthStatus,
  PredictResult,
  Recommendation,
  SeverityBreakdownItem,
  TrendResponse,
};
export type { PredictionItem, TrendPoint } from "@vcd/types";

const BASE_URL = DOMAIN;

// API calls

// Run the full multi-agent diagnosis pipeline through the Orchestrator
// (vision → RAG context → reasoning LLM → recommendation). The Orchestrator is
// the single entry point for diagnosis, matching the system architecture.
// The response is flattened into a PredictResult-compatible shape (so existing
// UI keeps working) and enriched with the generated recommendation.
export async function predictImage(file: File): Promise<DiagnoseResult> {
  const form = new FormData();
  form.append("image", file);
  const res = await fetch(`${BASE_URL}/orchestrate`, { method: "POST", headers: authHeaders(), body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Prediction failed");
  }
  const data: OrchestrationResponse = await res.json();
  return mapOrchestrationToResult(data);
}

function mapOrchestrationToResult(data: OrchestrationResponse): DiagnoseResult {
  const v = data.vision;
  return {
    disease: v.disease,
    confidence: v.confidence,
    top3: v.top3,
    explanation: v.explanation,
    severity: v.severity,
    severity_score: v.severity_score,
    severity_advice: v.severity_advice,
    agreement_score: v.agreement_score,
    ensemble_used: v.ensemble_used,
    model_count: v.model_count,
    uncertainty_score: v.uncertainty_score,
    image_url: v.image_url,
    is_in_distribution: v.is_in_distribution,
    ood_message: v.ood_message,
    ood_score: v.ood_score,
    recommendation: data.recommendation ?? null,
    reasoning_summary: data.reasoning_summary,
  };
}

export async function chatWithDisease(
  disease: string,
  question: string,
  sessionId: string,
  imageUrl?: string | null,
): Promise<ChatResponse> {
  const res = await fetch(`${BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      question,
      disease_filter: disease || undefined,
      session_id: sessionId,
      image_url: imageUrl ?? undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Query failed");
  }
  const data: QueryResponse = await res.json();
  const sources = buildCitations(data.chunks);
  return {
    // When we render structured citations, drop the LLM's duplicate inline
    // "Nguồn tham khảo:" block so sources are not shown twice.
    answer: sources.length > 0 ? stripTrailingSources(data.answer) : data.answer,
    sources,
  };
}

// Citations
// Turn retrieved chunks into grouped reference sources. The title comes from the
// disease folder metadata; each source is the curated `source_name` captured at
// ingest time — a clickable link when it is a URL, plain text otherwise.

const MAX_SOURCES_PER_CITATION = 4;

function isHttpUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function buildCitations(chunks: RetrievedChunk[]): Citation[] {
  const byTitle = new Map<string, { title: string; sources: string[] }>();

  for (const chunk of chunks) {
    const meta = chunk.metadata ?? {};
    const disease = meta.disease_name;
    const crop = meta.crop;

    // Prefer the curated source_name, fall back to any legacy source_urls.
    const names: string[] = [];
    if (typeof meta.source_name === "string" && meta.source_name.trim()) {
      names.push(meta.source_name.trim());
    }
    for (const url of meta.source_urls ?? []) {
      if (typeof url === "string" && url.trim()) names.push(url.trim());
    }
    if (!disease && names.length === 0) continue;

    const title = disease
      ? crop
        ? `${disease} (${crop})`
        : disease
      : "Tài liệu nông nghiệp";

    const entry = byTitle.get(title) ?? { title, sources: [] };
    for (const name of names) {
      if (!entry.sources.includes(name)) entry.sources.push(name);
    }
    byTitle.set(title, entry);
  }

  return Array.from(byTitle.values()).map((entry) => {
    const links: SourceLink[] = [];
    const seen = new Set<string>();
    for (const src of entry.sources) {
      const key = isHttpUrl(src) ? domainOf(src) : src;
      if (seen.has(key)) continue;
      seen.add(key);
      links.push(isHttpUrl(src) ? { label: domainOf(src), url: src } : { label: src });
      if (links.length >= MAX_SOURCES_PER_CITATION) break;
    }
    return { title: entry.title, links };
  });
}

// The recommendation LLM appends a trailing "Nguồn tham khảo:" line listing the
// source names it used. Cut everything from the last such marker to the end so
// the structured Citations widget is the single, clean source of truth.
function stripTrailingSources(answer: string): string {
  const re = /(?:\*\*|__)?\s*Nguồn tham khảo\s*:?/gi;
  let lastIdx = -1;
  let match: RegExpExecArray | null;
  while ((match = re.exec(answer)) !== null) lastIdx = match.index;
  if (lastIdx === -1) return answer;
  return answer.slice(0, lastIdx).trimEnd();
}

export async function getDiseases(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/diseases`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.diseases ?? [];
}

export async function getHealth(): Promise<HealthStatus> {
  const res = await fetch(`${BASE_URL}/health`);
  return res.json();
}

// Analytics

async function _analyticsGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Analytics request failed: ${res.status}`);
  return res.json();
}

export function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return _analyticsGet("/analytics/summary");
}

export function getDiseaseTrend(days = 30): Promise<TrendResponse> {
  return _analyticsGet(`/analytics/disease-trend?days=${days}`);
}

export function getCropDistribution(): Promise<CropDistributionItem[]> {
  return _analyticsGet("/analytics/crop-distribution");
}

export function getSeverityBreakdown(): Promise<SeverityBreakdownItem[]> {
  return _analyticsGet("/analytics/severity-breakdown");
}

export function getRecentAlerts(limit = 50): Promise<AlertItem[]> {
  return _analyticsGet(`/analytics/alerts?limit=${limit}`);
}

// History

export interface HistoryEntry {
  id: string;
  image_url?: string;
  created_at: string;
  disease_class: string;
  confidence: number;
  severity: string;
  crop?: string;
}

export async function getHistoryEntry(id: string): Promise<HistoryEntry | null> {
  try {
    const res = await fetch(`${BASE_URL}/analytics/history/${id}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getHistory(limit = 20): Promise<HistoryEntry[]> {
  try {
    const res = await fetch(`${BASE_URL}/analytics/history?limit=${limit}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.items ?? data ?? [];
  } catch {
    return [];
  }
}

// Profile

export interface UserProfile {
  id: string;
  username: string;
  email?: string;
  phone?: string;
  role: string;
  avatar_url?: string;
}

export async function getProfile(): Promise<UserProfile | null> {
  try {
    const res = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function uploadAvatar(file: File): Promise<UserProfile> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/auth/me/avatar`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Upload ảnh đại diện thất bại");
  }
  return res.json();
}

export async function updateProfile(data: { email?: string; phone?: string }): Promise<UserProfile> {
  const res = await fetch(`${BASE_URL}/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Cập nhật thất bại");
  }
  return res.json();
}

// Chat History

export interface ChatMessageItem {
  id: string;
  session_id: string;
  disease: string | null;
  question: string;
  answer: string;
  image_url?: string | null;
  created_at: string;
}

export async function getChatHistory(limit = 50): Promise<ChatMessageItem[]> {
  try {
    const res = await fetch(`${BASE_URL}/chat-history?limit=${limit}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages ?? [];
  } catch {
    return [];
  }
}

/** Marker question used by the backend for an expert reply injected into a farmer's
 * chat (see backend expert_routes.py). Such rows render as an "expert" bubble. */
export const EXPERT_REPLY_MARKER = "__EXPERT_REPLY__";

export interface ChatSession {
  session_id: string;
  disease: string | null;
  first_question: string;
  last_at: string;
  message_count: number;
  image_url?: string | null;
  has_expert_reply: boolean;
  expert_reply_at: string | null;
}

export async function getChatSessions(): Promise<ChatSession[]> {
  const messages = await getChatHistory(200);
  const map = new Map<string, ChatSession>();
  for (const m of [...messages].reverse()) {
    const isExpertReply = m.question === EXPERT_REPLY_MARKER;
    if (!map.has(m.session_id)) {
      map.set(m.session_id, {
        session_id: m.session_id,
        disease: m.disease,
        // An expert reply must never become the session's headline question.
        first_question: isExpertReply ? "" : m.question,
        last_at: m.created_at,
        message_count: 0,
        image_url: m.image_url ?? null,
        has_expert_reply: false,
        expert_reply_at: null,
      });
    }
    const s = map.get(m.session_id)!;
    s.message_count += 1;
    if (m.created_at > s.last_at) s.last_at = m.created_at;
    if (!s.first_question && !isExpertReply) s.first_question = m.question;
    if (isExpertReply) {
      s.has_expert_reply = true;
      if (!s.expert_reply_at || m.created_at > s.expert_reply_at) {
        s.expert_reply_at = m.created_at;
      }
    }
  }
  return [...map.values()].sort((a, b) => b.last_at.localeCompare(a.last_at));
}

export async function getSessionMessages(sessionId: string): Promise<ChatMessageItem[]> {
  try {
    const res = await fetch(`${BASE_URL}/chat-session/${sessionId}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages ?? [];
  } catch {
    return [];
  }
}

export async function initChatSession(
  sessionId: string,
  disease: string | null,
  imageUrl: string | null | undefined,
  diseaseDisplay: string,
): Promise<void> {
  try {
    await fetch(`${BASE_URL}/chat-session/init`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        session_id: sessionId,
        disease: disease || null,
        image_url: imageUrl ?? null,
        disease_display: diseaseDisplay,
      }),
    });
  } catch {
    // non-critical, ignore failures
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${BASE_URL}/chat-session/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

// Feedback

export async function submitFeedback(payload: FeedbackRequest): Promise<FeedbackResponse> {
  const res = await fetch(`${BASE_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Gửi góp ý thất bại");
  }
  return res.json();
}

export async function getFeedbackHistory(limit = 50): Promise<FeedbackItem[]> {
  try {
    const res = await fetch(`${BASE_URL}/feedback?limit=${limit}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

// Helpers

// Disease/crop display labels live in disease-labels.ts (mirrors backend CLASS_TO_VN).
// Re-exported here so existing imports from "@/lib/api" keep working.
export { formatDiseaseName, getDiseaseName, getCropName } from "./disease-labels";
