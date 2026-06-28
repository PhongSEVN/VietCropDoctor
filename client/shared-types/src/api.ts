// ─────────────────────────────────────────────────────────────────────────────
//  @vcd/types — shared API contracts for VietCropDoctor clients
//
//  These interfaces mirror the Pydantic schemas in:
//    vietcropdoctor-services/services/shared/vcd_shared/schemas.py
//
//  Import in any package:
//    import type { PredictResult, ChatResponse } from "@vcd/types";
// ─────────────────────────────────────────────────────────────────────────────

// Vision-AI

export interface PredictionItem {
  class_name: string;
  confidence: number;
}

export interface PredictResult {
  disease: string;
  confidence: number;
  top3: PredictionItem[];
  /** Human-readable confidence explanation in Vietnamese. */
  explanation: string;
  /** Rule-based severity level derived from confidence + GradCAM activation area. */
  severity: "healthy" | "mild" | "moderate" | "severe";
  severity_score: number;   // 0.0 – 1.0
  severity_advice: string;
  /** Fraction of ensemble models that agreed on the top-1 class (1.0 = full agreement or single model). */
  agreement_score: number;
  ensemble_used: boolean;
  model_count: number;
  uncertainty_score?: number | null;
  image_url?: string | null;
  /** OOD gate: false when the image is judged not to be a crop leaf. */
  is_in_distribution?: boolean;
  /** Vietnamese guidance shown when is_in_distribution is false. */
  ood_message?: string | null;
  /** P(in-distribution), 0..1. */
  ood_score?: number | null;
}

// RAG / Chat

export interface RetrievedChunk {
  content: string;
  source: string;
  score: number;
  disease?: string;
  metadata?: {
    crop?: string;
    disease_name?: string;
    /** Curated source label from sources.json — often a URL, sometimes a plain title. */
    source_name?: string;
    /** Legacy/optional list of source URLs. */
    source_urls?: string[];
    [key: string]: unknown;
  };
}

// A single reference source. When `url` is present it renders as a clickable
// link (label = domain); otherwise `label` renders as plain text.
export interface SourceLink {
  label: string;
  url?: string;
}

// A grouped citation: a disease title plus its original source links.
export interface Citation {
  title: string;
  links: SourceLink[];
}

export interface ChatRequest {
  disease: string;
  question: string;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  sources: Citation[];
}

export interface QueryRequest {
  question: string;
  disease_filter?: string;
  top_k?: number;
  score_threshold?: number;
  session_id?: string;
  stream?: boolean;
  image_url?: string | null;
}

export interface QueryResponse {
  answer: string;
  chunks: RetrievedChunk[];
  latencies: {
    embed_ms: number;
    retrieve_ms: number;
    rerank_ms: number;
    llm_ms: number;
    total_ms: number;
  };
  session_id?: string;
}

// Orchestrator (multi-agent diagnosis pipeline)

export interface VisionResult {
  disease: string;
  confidence: number;
  severity: "healthy" | "mild" | "moderate" | "severe";
  severity_score: number;
  severity_advice: string;
  top3: PredictionItem[];
  uncertainty_score?: number | null;
  ensemble_used: boolean;
  explanation: string;
  agreement_score: number;
  model_count: number;
  image_url?: string | null;
  is_in_distribution: boolean;
  ood_message?: string | null;
  ood_score?: number | null;
}

export interface RetrievalResult {
  answer: string;
  sources: string[];
  chunks_used: number;
}

export interface Recommendation {
  immediate_actions: string[];
  preventive_measures: string[];
  treatment_options: string[];
  monitoring_advice: string;
  urgency: "low" | "medium" | "high" | "critical";
}

export interface OrchestrationResponse {
  session_id?: string | null;
  vision: VisionResult;
  knowledge?: RetrievalResult | null;
  recommendation?: Recommendation | null;
  reasoning_summary: string;
  latency_ms: Record<string, number>;
}

// A diagnosis result enriched with the orchestrator's recommendation.
// Shape-compatible with PredictResult so existing UI keeps working.
export interface DiagnoseResult extends PredictResult {
  recommendation?: Recommendation | null;
  reasoning_summary?: string;
}

// Feedback

export interface FeedbackRequest {
  session_id?: string | null;
  image_url?: string | null;
  predicted_disease: string;
  predicted_confidence?: number;
  is_correct: boolean;
  corrected_disease?: string | null;
  comment?: string | null;
}

export interface FeedbackResponse {
  id: string;
  confirmed_label: string;
  verified_image_path?: string | null;
  message: string;
}

export interface FeedbackItem {
  id: string;
  session_id?: string | null;
  image_url?: string | null;
  predicted_disease: string;
  predicted_confidence: number;
  is_correct: boolean;
  corrected_disease?: string | null;
  confirmed_label: string;
  comment?: string | null;
  verified_image_path?: string | null;
  created_at: string;
}

// Health

export interface HealthStatus {
  status: string;
  model_loaded?: boolean;
  vectordb_connected?: boolean;
  llm_reachable?: boolean;
  vectors_count?: number;
}

export interface ServiceEntry {
  status: "up" | "down";
  elapsed_ms?: number;
  error?: string;
  detail?: HealthStatus;
}

export interface ServicesHealth {
  status: "ok" | "degraded";
  gateway: "up" | "down";
  services: Record<string, ServiceEntry>;
  checked_at: string;
  total_ms: number;
}

// Ingestion

export interface IngestResponse {
  chunks_created: number;
  documents_processed: number;
  collection: string;
  elapsed_seconds: number;
}

export interface CollectionStats {
  collection: string;
  vectors_count: number;
  status: string;
}

// Analytics

export interface AnalyticsSummary {
  today_count: number;
  week_count: number;
  month_count: number;
  total_count: number;
  top_diseases: { disease: string; count: number }[];
  avg_confidence_per_crop: { crop: string; avg_confidence: number }[];
}

export interface TrendPoint {
  date: string;
  disease: string;
  count: number;
}

export interface TrendResponse {
  days: number;
  data: TrendPoint[];
}

export interface CropDistributionItem {
  crop: string;
  count: number;
}

export interface SeverityBreakdownItem {
  crop: string;
  severity: string;
  count: number;
}

export interface AlertItem {
  alert_id: string;
  timestamp: string;
  disease: string;
  severity: string;
  confidence: number;
  crop: string;
}
