import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { downloadReport, logAudit } from "@/lib/admin-api";
import type { ReportFormat, ReportType } from "@/types/admin";

const REPORTS: { type: ReportType; label: string; icon: string; desc: string }[] = [
  { type: "user", label: "Báo cáo người dùng", icon: "group", desc: "Danh sách, vai trò, trạng thái, hoạt động." },
  { type: "expert", label: "Báo cáo chuyên gia", icon: "agriculture", desc: "Hiệu suất, số ca, lĩnh vực phụ trách." },
  { type: "feedback", label: "Báo cáo feedback", icon: "rate_review", desc: "Feedback theo bệnh, đúng/sai, trạng thái." },
  { type: "disease_trend", label: "Xu hướng bệnh", icon: "coronavirus", desc: "Bệnh phổ biến 7/30 ngày." },
  { type: "ai_performance", label: "Hiệu năng AI", icon: "smart_toy", desc: "Số lượt, độ chính xác, confidence theo bệnh." },
];

// Backend streams CSV (UTF-8 BOM) for both — Excel opens the CSV natively.
const FORMATS: { value: ReportFormat; label: string; icon: string }[] = [
  { value: "csv", label: "CSV", icon: "description" },
  { value: "excel", label: "Excel", icon: "table_view" },
];

export function Reports() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload(type: ReportType, format: ReportFormat) {
    setError(null);
    setBusy(`${type}-${format}`);
    try {
      await downloadReport(type, format);
      logAudit("report.export", type, null, { format });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được báo cáo");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-error/40 bg-error-container/30 px-3 py-2 text-sm text-error">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {REPORTS.map((r) => (
          <Card key={r.type} className="border-outline-variant bg-surface-container-lowest">
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-on-surface flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">{r.icon}</span>
                {r.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-on-surface-variant mb-3">{r.desc}</p>
              <div className="flex gap-2">
                {FORMATS.map((f) => {
                  const isBusy = busy === `${r.type}-${f.value}`;
                  return (
                    <button
                      key={f.value}
                      onClick={() => handleDownload(r.type, f.value)}
                      disabled={isBusy}
                      className="flex items-center gap-1 rounded-md border border-outline-variant px-2.5 py-1 text-xs text-on-surface hover:bg-surface-container-high transition-colors disabled:opacity-50 disabled:cursor-wait"
                    >
                      <span className="material-symbols-outlined text-[16px]">
                        {isBusy ? "progress_activity" : f.icon}
                      </span>
                      {isBusy ? "Đang tải…" : f.label}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-[11px] text-on-surface-variant">
        File CSV dùng UTF-8 BOM nên mở trực tiếp bằng Excel vẫn đúng tiếng Việt. Dữ liệu lấy trực tiếp
        từ cơ sở dữ liệu (người dùng, feedback, chuyên gia).
      </p>
    </div>
  );
}
