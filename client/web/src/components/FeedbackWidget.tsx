import { useState } from "react";
import { getDiseases, submitFeedback, formatDiseaseName } from "@/lib/api";

interface FeedbackWidgetProps {
  predictedDisease: string;
  predictedConfidence: number;
  imageUrl?: string | null;
  sessionId?: string;
}

type Phase =
  | { type: "idle" }
  | { type: "correcting" }
  | { type: "submitting" }
  | { type: "done"; correct: boolean }
  | { type: "error"; message: string };

export default function FeedbackWidget({
  predictedDisease,
  predictedConfidence,
  imageUrl,
  sessionId,
}: FeedbackWidgetProps) {
  const [phase, setPhase] = useState<Phase>({ type: "idle" });
  const [diseases, setDiseases] = useState<string[]>([]);
  const [correctedDisease, setCorrectedDisease] = useState("");
  const [comment, setComment] = useState("");

  async function send(isCorrect: boolean, corrected?: string) {
    setPhase({ type: "submitting" });
    try {
      await submitFeedback({
        session_id: sessionId ?? null,
        image_url: imageUrl ?? null,
        predicted_disease: predictedDisease,
        predicted_confidence: predictedConfidence,
        is_correct: isCorrect,
        corrected_disease: corrected ?? null,
        comment: comment.trim() || null,
      });
      setPhase({ type: "done", correct: isCorrect });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Gửi góp ý thất bại";
      setPhase({ type: "error", message });
    }
  }

  async function handleWrongClick() {
    setPhase({ type: "correcting" });
    if (diseases.length === 0) {
      const list = await getDiseases();
      setDiseases(list.filter((d) => d && d !== predictedDisease));
    }
  }

  if (phase.type === "done") {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-lg bg-[#dcfce3] px-3 py-2 text-sm text-[#166534]">
        <span className="material-symbols-outlined text-base icon-fill">verified</span>
        {phase.correct
          ? "Cảm ơn! Đã ghi nhận chẩn đoán chính xác."
          : "Cảm ơn! Phản hồi của bạn đã được ghi nhận để cải thiện hệ thống."}
      </div>
    );
  }

  return (
    <div className="mt-4 border-t border-outline-variant/50 pt-3">
      {phase.type !== "correcting" && (
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-on-surface-variant">Chẩn đoán này có đúng không?</span>
          <button
            type="button"
            disabled={phase.type === "submitting"}
            onClick={() => send(true)}
            className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-base">thumb_up</span>
            Đúng
          </button>
          <button
            type="button"
            disabled={phase.type === "submitting"}
            onClick={handleWrongClick}
            className="inline-flex items-center gap-1.5 rounded-full border border-outline-variant px-3 py-1.5 text-sm font-medium text-on-surface-variant hover:bg-surface-container transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-base">thumb_down</span>
            Sai
          </button>
        </div>
      )}

      {phase.type === "correcting" && (
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">
              Bệnh đúng là gì? <span className="font-normal text-on-surface-variant">(không bắt buộc)</span>
            </label>
            <select
              value={correctedDisease}
              onChange={(e) => setCorrectedDisease(e.target.value)}
              className="w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="">— Không rõ / để chuyên gia xác định —</option>
              {diseases.map((d) => (
                <option key={d} value={d}>
                  {formatDiseaseName(d)}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Ghi chú thêm (không bắt buộc)…"
            rows={2}
            maxLength={1000}
            className="w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => send(false, correctedDisease || undefined)}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-sm font-medium text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-base">send</span>
              Gửi góp ý
            </button>
            <button
              type="button"
              onClick={() => setPhase({ type: "idle" })}
              className="text-sm text-on-surface-variant hover:text-on-surface px-2 py-1.5"
            >
              Hủy
            </button>
          </div>
        </div>
      )}

      {phase.type === "submitting" && (
        <p className="mt-2 text-sm text-on-surface-variant">Đang gửi…</p>
      )}

      {phase.type === "error" && (
        <div className="mt-2 flex items-center gap-2 text-sm text-on-error-container">
          <span className="material-symbols-outlined text-base">error</span>
          {phase.message}
          <button
            type="button"
            onClick={() => setPhase({ type: "idle" })}
            className="underline hover:no-underline"
          >
            Thử lại
          </button>
        </div>
      )}
    </div>
  );
}
