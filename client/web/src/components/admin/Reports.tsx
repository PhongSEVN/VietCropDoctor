import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { logAudit, reportDownloadUrl } from "@/lib/admin-api";
import type { ReportFormat, ReportType } from "@/types/admin";

const REPORTS: { type: ReportType; label: string; icon: string; desc: string }[] = [
  { type: "user", label: "Báo cáo người dùng", icon: "group", desc: "Danh sách, vai trò, trạng thái, hoạt động." },
  { type: "expert", label: "Báo cáo chuyên gia", icon: "agriculture", desc: "Hiệu suất, số ca, thời gian phản hồi." },
  { type: "feedback", label: "Báo cáo feedback", icon: "rate_review", desc: "Feedback theo cây, bệnh, khu vực." },
  { type: "disease_trend", label: "Xu hướng bệnh", icon: "coronavirus", desc: "Bệnh phổ biến, tốc độ tăng giảm." },
  { type: "ai_performance", label: "Hiệu năng AI", icon: "smart_toy", desc: "Số lượt phân tích, độ chính xác, confidence." },
];

const FORMATS: { value: ReportFormat; label: string; icon: string }[] = [
  { value: "csv", label: "CSV", icon: "description" },
  { value: "excel", label: "Excel", icon: "table_view" },
  { value: "pdf", label: "PDF", icon: "picture_as_pdf" },
];

export function Reports() {
  function handleDownload(type: ReportType, format: ReportFormat) {
    logAudit("report.export", type, null, { format });
    // Opens the gateway report stream; TODO(backend) must implement it.
    window.open(reportDownloadUrl(type, format), "_blank", "noopener,noreferrer");
  }

  return (
    <div className="space-y-3">
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
                {FORMATS.map((f) => (
                  <button
                    key={f.value}
                    onClick={() => handleDownload(r.type, f.value)}
                    className="flex items-center gap-1 rounded-md border border-outline-variant px-2.5 py-1 text-xs text-on-surface hover:bg-surface-container-high transition-colors"
                  >
                    <span className="material-symbols-outlined text-[16px]">{f.icon}</span>
                    {f.label}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="text-[11px] text-on-surface-variant">
        TODO(backend): GET /admin/reports/&#123;type&#125;?format=csv|excel|pdf trả file stream. CSV của bảng
        đang hiển thị có thể export ngay tại từng module (nút “CSV”), không cần backend.
      </p>
    </div>
  );
}
