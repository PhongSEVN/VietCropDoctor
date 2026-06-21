import { useEffect, useState } from "react";

import { IrrelevantBadge, PriorityBadge, StatusBadge } from "./badges";
import { ErrorState, LoadingState } from "./states";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { getCropName, getDiseaseName, getDiseases } from "@/lib/api";
import { addInternalNote, markCaseIrrelevant, submitExpertResponse } from "@/lib/expert-api";
import { useExpertCase } from "@/hooks/useExpert";
import type { ExpertCase, ExpertResponseInput } from "@/types/expert";

interface Props {
  caseId: string;
  onClose: () => void;
  /** Called after any mutation so the parent queue/stats refresh. */
  onUpdated: () => void;
}

function fmt(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

export function CaseDetailModal({ caseId, onClose, onUpdated }: Props) {
  const { detail, loading, error, refetch } = useExpertCase(caseId);

  // Close on ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-2 sm:p-6 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Chi tiết ca chẩn đoán"
    >
      <div
        className="bg-surface w-full max-w-5xl rounded-xl shadow-2xl my-2"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-outline-variant px-5 py-3 sticky top-0 bg-surface rounded-t-xl">
          <h2 className="text-lg font-semibold text-on-surface">Chi tiết ca chẩn đoán</h2>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:bg-surface-container-high rounded-full p-1.5 transition-colors"
            aria-label="Đóng"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="p-5">
          {loading && <LoadingState label="Đang tải chi tiết ca..." />}
          {error && (
            <ErrorState
              message={error}
              onRetry={refetch}
              hint="Endpoint GET /expert/cases/{id} chưa được backend cài đặt (xem TODO trong lib/expert-api.ts)."
            />
          )}
          {detail && (
            <CaseDetailBody
              detail={detail}
              onMutated={() => {
                refetch();
                onUpdated();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// Body

function CaseDetailBody({ detail, onMutated }: { detail: ExpertCase; onMutated: () => void }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left: image + sender + AI */}
      <div className="space-y-4">
        <ImageBlock detail={detail} />
        <MarkIrrelevantBar detail={detail} onMutated={onMutated} />
        <SenderBlock detail={detail} />
        <AiBlock detail={detail} />
        <ConversationBlock detail={detail} />
      </div>

      {/* Right: responses + expert form + internal notes */}
      <div className="space-y-4">
        <ResponseHistory detail={detail} />
        <ExpertResponseForm caseId={detail.id} onMutated={onMutated} />
        <InternalNotes caseId={detail.id} detail={detail} onMutated={onMutated} />
      </div>
    </div>
  );
}

function MarkIrrelevantBar({ detail, onMutated }: { detail: ExpertCase; onMutated: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const marked = detail.is_irrelevant === true;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await markCaseIrrelevant(detail.id, !marked);
      onMutated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Thao tác thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`rounded-lg border p-3 ${marked ? "border-rose-300 bg-rose-50" : "border-outline-variant"}`}>
      {marked ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <IrrelevantBadge />
            <span className="text-xs text-on-surface-variant">Ca này đã được đánh dấu ảnh không liên quan.</span>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={toggle} disabled={busy}>
            {busy ? "Đang lưu..." : "Bỏ đánh dấu"}
          </Button>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-sm text-on-surface">Ảnh này không phải lá cây trồng?</span>
          <Button type="button" variant="destructive" size="sm" onClick={toggle} disabled={busy}>
            <span className="material-symbols-outlined text-[18px]">block</span>
            {busy ? "Đang lưu..." : "Đánh dấu ảnh không liên quan"}
          </Button>
        </div>
      )}
      {error && <p className="text-xs text-error mt-1">{error}</p>}
    </div>
  );
}

function ImageBlock({ detail }: { detail: ExpertCase }) {
  const related = detail.related_image_urls ?? [];
  return (
    <div>
      {detail.image_url ? (
        <img
          src={detail.image_url}
          alt="Ảnh cây trồng gốc"
          className="w-full max-h-80 object-contain rounded-lg border border-outline-variant bg-surface-container-lowest"
        />
      ) : (
        <div className="w-full h-64 rounded-lg bg-surface-container flex items-center justify-center text-on-surface-variant">
          <span className="material-symbols-outlined text-4xl">image_not_supported</span>
        </div>
      )}
      {related.length > 0 && (
        <div className="flex gap-2 mt-2 overflow-x-auto">
          {related.map((u) => (
            <img key={u} src={u} alt="Ảnh liên quan" className="h-16 w-16 rounded-md object-cover border border-outline-variant" />
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <span className="text-xs text-on-surface-variant">{label}</span>
      <p className="text-sm text-on-surface">{value}</p>
    </div>
  );
}

function SenderBlock({ detail }: { detail: ExpertCase }) {
  return (
    <div className="rounded-lg border border-outline-variant p-3 grid grid-cols-2 gap-3">
      <Field label="Người gửi" value={detail.user_name || detail.user_id.slice(0, 8)} />
      <Field label="Thời gian gửi" value={fmt(detail.created_at)} />
      <Field label="Loại cây" value={detail.crop || getCropName(detail.ai.predicted_disease) || "—"} />
      <div className="flex items-end gap-2">
        <StatusBadge status={detail.status} />
        <PriorityBadge priority={detail.priority} />
      </div>
      <div className="col-span-2">
        <Field label="Mô tả vấn đề" value={detail.problem_description || "—"} />
      </div>
    </div>
  );
}

function AiBlock({ detail }: { detail: ExpertCase }) {
  const { ai } = detail;
  return (
    <div className="rounded-lg border border-outline-variant p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-primary text-[20px]">smart_toy</span>
        <h3 className="text-sm font-semibold text-on-surface">Kết quả AI phân tích</h3>
      </div>
      <Field
        label="Chẩn đoán hiện tại"
        value={
          <span className="font-medium">
            {getDiseaseName(detail.current_diagnosis || ai.predicted_disease)}{" "}
            <span className="text-on-surface-variant">({(ai.predicted_confidence * 100).toFixed(1)}% tin cậy)</span>
          </span>
        }
      />
      {ai.top3 && ai.top3.length > 0 && (
        <div className="mt-2 space-y-1">
          <span className="text-xs text-on-surface-variant">Nguyên nhân có thể</span>
          {ai.top3.map((t) => (
            <div key={t.class_name} className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-surface-container">
                <div className="h-1.5 rounded-full bg-primary" style={{ width: `${t.confidence * 100}%` }} />
              </div>
              <span className="text-xs text-on-surface-variant w-40 truncate">{getDiseaseName(t.class_name)}</span>
              <span className="text-xs text-on-surface-variant w-10 text-right">{(t.confidence * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}
      {typeof ai.agreement_score === "number" && (
        <p className="text-xs text-on-surface-variant mt-2">
          Đồng thuận ensemble: {(ai.agreement_score * 100).toFixed(0)}%
          {ai.model_count ? ` · ${ai.model_count} mô hình` : ""}
        </p>
      )}
    </div>
  );
}

function ConversationBlock({ detail }: { detail: ExpertCase }) {
  const msgs = detail.conversation ?? [];
  if (msgs.length === 0) return null;
  return (
    <div className="rounded-lg border border-outline-variant p-3">
      <h3 className="text-sm font-semibold text-on-surface mb-2">Lịch sử trao đổi</h3>
      <div className="space-y-2 max-h-56 overflow-y-auto chat-scroll">
        {msgs.map((m) => (
          <div key={m.id} className={m.role === "expert" ? "text-right" : ""}>
            <div
              className={`inline-block rounded-lg px-3 py-1.5 text-sm max-w-[85%] ${m.role === "expert"
                ? "bg-primary-container text-on-primary-container"
                : m.role === "ai"
                  ? "bg-surface-container text-on-surface-variant"
                  : "bg-surface-container-high text-on-surface"
                }`}
            >
              {m.text}
            </div>
            <p className="text-[10px] text-on-surface-variant mt-0.5">{fmt(m.created_at)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResponseHistory({ detail }: { detail: ExpertCase }) {
  return (
    <div className="rounded-lg border border-outline-variant p-3">
      <h3 className="text-sm font-semibold text-on-surface mb-2">Lịch sử phản hồi chuyên gia</h3>
      {detail.responses.length === 0 ? (
        <p className="text-xs text-on-surface-variant">Chưa có phản hồi nào.</p>
      ) : (
        <ul className="space-y-3">
          {detail.responses.map((r) => (
            <li key={r.id} className="border-l-2 border-primary pl-3">
              <div className="flex justify-between text-xs text-on-surface-variant">
                <span className="font-medium text-on-surface">{r.expert_name || "Chuyên gia"}</span>
                <span>{fmt(r.created_at)}</span>
              </div>
              {r.diagnosis && (
                <p className="text-xs mt-0.5">Chẩn đoán: <span className="font-medium">{getDiseaseName(r.diagnosis)}</span></p>
              )}
              <p className="text-sm text-on-surface mt-0.5 whitespace-pre-wrap">{r.comment}</p>
              {r.treatment && <p className="text-sm text-on-surface-variant mt-1">Xử lý: {r.treatment}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Expert response form

function ExpertResponseForm({ caseId, onMutated }: { caseId: string; onMutated: () => void }) {
  const [comment, setComment] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [treatment, setTreatment] = useState("");
  const [attachments, setAttachments] = useState("");
  const [markCompleted, setMarkCompleted] = useState(true);
  const [diseaseOptions, setDiseaseOptions] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiseases().then(setDiseaseOptions).catch(() => setDiseaseOptions([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) {
      setError("Vui lòng nhập nhận xét.");
      return;
    }
    setSubmitting(true);
    setError(null);
    const payload: ExpertResponseInput = {
      comment: comment.trim(),
      diagnosis: diagnosis.trim() || null,
      treatment: treatment.trim() || null,
      attachment_urls: attachments
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      mark_completed: markCompleted,
    };
    try {
      await submitExpertResponse(caseId, payload);
      setComment("");
      setDiagnosis("");
      setTreatment("");
      setAttachments("");
      onMutated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi phản hồi thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-outline-variant p-3 space-y-2">
      <h3 className="text-sm font-semibold text-on-surface">Phản hồi của chuyên gia</h3>

      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Nhận xét, đánh giá tình trạng cây..."
        className="min-h-[72px] border-outline-variant bg-surface-container-lowest"
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-on-surface-variant">Chẩn đoán bệnh</label>
          <input
            list="expert-disease-options"
            value={diagnosis}
            onChange={(e) => setDiagnosis(e.target.value)}
            placeholder="Chọn / nhập mã bệnh"
            className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <datalist id="expert-disease-options">
            {diseaseOptions.map((d) => (
              <option key={d} value={d}>{getDiseaseName(d)}</option>
            ))}
          </datalist>
        </div>
        <div>
          <label className="text-xs text-on-surface-variant">Thuốc / phương pháp xử lý</label>
          <input
            value={treatment}
            onChange={(e) => setTreatment(e.target.value)}
            placeholder="Ví dụ: phun thuốc gốc đồng..."
            className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>

      <div>
        <label className="text-xs text-on-surface-variant">Ảnh minh họa (URL, cách nhau bởi dấu phẩy)</label>
        <input
          value={attachments}
          onChange={(e) => setAttachments(e.target.value)}
          placeholder="https://...jpg, https://...png"
          className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-on-surface">
        <input type="checkbox" checked={markCompleted} onChange={(e) => setMarkCompleted(e.target.checked)} />
        Đánh dấu hoàn thành (đưa nhãn vào tập huấn luyện)
      </label>

      {error && <p className="text-xs text-error">{error}</p>}

      <Button type="submit" disabled={submitting} className="w-full">
        {submitting ? "Đang gửi..." : "Gửi phản hồi"}
      </Button>
    </form>
  );
}

// Internal notes

function InternalNotes({ caseId, detail, onMutated }: { caseId: string; detail: ExpertCase; onMutated: () => void }) {
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!note.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await addInternalNote(caseId, note.trim());
      setNote("");
      onMutated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu ghi chú thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-outline-variant p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-on-surface-variant text-[18px]">lock</span>
        <h3 className="text-sm font-semibold text-on-surface">Ghi chú nội bộ</h3>
        <span className="text-[10px] text-on-surface-variant">(người dùng không nhìn thấy)</span>
      </div>
      {detail.notes.length > 0 && (
        <ul className="space-y-1.5 mb-2">
          {detail.notes.map((n) => (
            <li key={n.id} className="text-xs text-on-surface-variant">
              <span className="font-medium text-on-surface">{n.expert_name || "Chuyên gia"}:</span> {n.note}
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Thêm ghi chú riêng..."
          className="h-9 flex-1 rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
        <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={submitting}>
          Lưu
        </Button>
      </div>
      {error && <p className="text-xs text-error mt-1">{error}</p>}
    </div>
  );
}
