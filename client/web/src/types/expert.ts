//  Expert (agronomist) dashboard domain types.
//
//  These model the expert review workflow on top of the existing `feedback`
//  records (backend/services/ai/rag-engine — table `feedback`). The base feedback
//  row already carries: image_url, predicted_disease, predicted_confidence,
//  is_correct, corrected_disease, confirmed_label, comment, verified_image_path,
//  created_at, user_id.
//
//  Fields NOT yet in the backend (status, priority, expert responses, internal
//  notes, assignment, SLA) are documented as TODO(backend) in lib/expert-api.ts;
//  the expert endpoints must add the corresponding columns/tables.

/** Workflow state of a case. Maps to a new `feedback.status` column. */
export type ExpertCaseStatus = "pending" | "in_progress" | "answered";

/** Triage priority. Maps to a new `feedback.priority` column. */
export type CasePriority = "low" | "normal" | "high" | "urgent";

/** AI ensemble analysis attached to a case (from the original prediction). */
export interface AiAnalysis {
  predicted_disease: string;
  predicted_confidence: number; // 0..1
  top3?: { class_name: string; confidence: number }[];
  agreement_score?: number;
  model_count?: number;
}

/** One expert reply in a case's response history. */
export interface ExpertResponseEntry {
  id: string;
  expert_id: string;
  expert_name?: string;
  comment: string;
  /** Confirmed disease class chosen by the expert (feeds the verified dataset). */
  diagnosis?: string | null;
  /** Recommended treatment / pesticide / method. */
  treatment?: string | null;
  attachment_urls?: string[];
  created_at: string;
}

/** Expert-only note, never shown to the end user. */
export interface InternalNote {
  id: string;
  expert_id: string;
  expert_name?: string;
  note: string;
  created_at: string;
}

/** A message in the user ↔ expert ↔ AI conversation thread. */
export interface ConversationMessage {
  id: string;
  role: "user" | "expert" | "ai";
  text: string;
  created_at: string;
}

/** A feedback case enriched with the expert-review workflow. */
export interface ExpertCase {
  id: string;
  user_id: string;
  user_name?: string;
  image_url?: string | null;
  related_image_urls?: string[];
  crop?: string | null;
  problem_description?: string | null;
  status: ExpertCaseStatus;
  priority: CasePriority;
  /** Expert flagged the image as not a crop leaf (irrelevant / OOD). */
  is_irrelevant?: boolean;
  created_at: string;
  updated_at?: string | null;
  ai: AiAnalysis;
  /** Current best label (feedback.confirmed_label). */
  current_diagnosis?: string | null;
  responses: ExpertResponseEntry[];
  notes: InternalNote[];
  conversation?: ConversationMessage[];
  /** SLA deadline; cases past this are flagged overdue. */
  sla_due_at?: string | null;
}

export type CaseSort = "newest" | "oldest" | "priority";

export interface ExpertCaseFilters {
  search: string;
  status: ExpertCaseStatus | "all";
  crop: string | "all";
  sort: CaseSort;
}

/** KPI + chart aggregates for the dashboard overview. */
export interface ExpertStats {
  total: number;
  pending: number;
  in_progress: number;
  answered: number;
  /** Mean minutes from case creation to first expert response; null if unknown. */
  avg_response_minutes: number | null;
  resolved_last7days: number;
  by_day: { date: string; count: number }[];
  top_diseases: { disease: string; count: number }[];
  top_crops: { crop: string; count: number }[];
}

/** Payload submitted when an expert answers a case. */
export interface ExpertResponseInput {
  comment: string;
  diagnosis?: string | null;
  treatment?: string | null;
  attachment_urls?: string[];
  mark_completed?: boolean;
}

/** Presence/load info for the expert-management panel. */
export interface OnlineExpert {
  id: string;
  name: string;
  active_cases: number;
  online: boolean;
}

/**
 * A single image diagnosis from chat history — includes diagnoses the user never
 * gave feedback on. `feedback_id` is set only once a case row exists; otherwise the
 * expert must "promote" it (creating the case) before responding.
 */
export interface DiagnosisItem {
  chat_id: string;
  user_id: string;
  user_name?: string | null;
  image_url?: string | null;
  disease?: string | null; // AI-predicted
  created_at: string;
  has_feedback: boolean;
  feedback_id?: string | null;
  status: ExpertCaseStatus | "new";
  is_irrelevant: boolean;
}
