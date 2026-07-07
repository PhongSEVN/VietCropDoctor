import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GRAFANA_URL } from "@/constants/domain";

/** Dashboards provisioned in infra/monitoring/grafana/dashboards (uid = top-level uid). */
const DASHBOARDS = [
  { uid: "vcd-overview", label: "Tổng quan", icon: "dashboard" },
  { uid: "system", label: "Hệ thống", icon: "memory" },
  { uid: "ai-performance", label: "AI Performance", icon: "neurology" },
  { uid: "rag-llm", label: "RAG / LLM", icon: "smart_toy" },
  { uid: "business", label: "Nghiệp vụ", icon: "insights" },
] as const;

const RANGES = [
  { value: "now-1h", label: "1 giờ" },
  { value: "now-6h", label: "6 giờ" },
  { value: "now-24h", label: "24 giờ" },
  { value: "now-7d", label: "7 ngày" },
  { value: "now-30d", label: "30 ngày" },
] as const;

type DashboardUid = (typeof DASHBOARDS)[number]["uid"];
type RangeValue = (typeof RANGES)[number]["value"];

// Live/latency dashboards read from Prometheus (short in-memory history, most
// useful zoomed in); "Nghiệp vụ" reads cumulative business KPIs from
// ClickHouse, which only makes sense viewed over days/weeks. Forcing the same
// 6h default on every tab made the business dashboard look broken — e.g. an
// average-confidence stat computed over only the last few requests instead of
// the real multi-week trend. Each dashboard now opens at the range its data
// actually reads meaningfully at; the range buttons still let you override.
const DEFAULT_RANGE_BY_UID: Record<DashboardUid, RangeValue> = {
  "vcd-overview":   "now-6h",
  "system":         "now-6h",
  "ai-performance": "now-6h",
  "rag-llm":        "now-6h",
  "business":       "now-30d",
};

type GlossaryEntry = { en: string; vi: string; meaning: string };

// Grafana panel titles stay in English (that's what's baked into the
// provisioned dashboard JSON), so admins who don't read English get a plain
// English chart title with no idea what it measures. This glossary translates
// each panel name and explains what it actually shows, shown under the iframe
// for the dashboard currently open.
const PANEL_GLOSSARY: Partial<Record<DashboardUid, GlossaryEntry[]>> = {
  "ai-performance": [
    {
      en: "Prediction Latency",
      vi: "Độ trễ chẩn đoán",
      meaning: "Thời gian xử lý một lượt /predict (P50 = trung vị, P95 = 95% request nhanh hơn mức này).",
    },
    {
      en: "Vision-AI Request Rate by Status",
      vi: "Tần suất request theo mã trạng thái",
      meaning: "Số request /predict mỗi giây, tách theo mã HTTP trả về (2xx thành công, 4xx/5xx lỗi).",
    },
    {
      en: "Ensemble Model Prediction Rate",
      vi: "Tần suất dự đoán từng model trong ensemble",
      meaning: "Số lượt dự đoán mỗi giây của từng model thành phần (EfficientNet, MobileNetV3, ResNet50, YOLOv11, ViT).",
    },
  ],
  "rag-llm": [
    {
      en: "Qdrant Query Latency",
      vi: "Độ trễ truy vấn Qdrant (vector DB)",
      meaning:
        "Thời gian tìm kiếm ngữ nghĩa trong Qdrant khi trả lời câu hỏi (P50/P95). Chỉ số này chỉ ghi nhận cho lượt " +
        "\"Hỏi thêm\" gọi trực tiếp /query — KHÔNG bao gồm bước truy hồi ngữ cảnh mà Orchestrator gọi cho mỗi lần " +
        "chẩn đoán ảnh (đường retrieve-only), nên số liệu thường rất ít so với lượng truy vấn Qdrant thực tế.",
    },
    {
      en: "Ollama Generation Latency",
      vi: "Độ trễ sinh câu trả lời của Ollama",
      meaning:
        "Thời gian LLM (Qwen 2.5 qua Ollama) sinh câu trả lời cho lượt \"Hỏi thêm\" trong RAG Engine. Không bao gồm " +
        "lệnh gọi Ollama riêng của Orchestrator để sinh khuyến nghị điều trị sau mỗi lần chẩn đoán — lệnh gọi đó " +
        "hiện chưa được đo bằng Prometheus.",
    },
    {
      en: "Avg Context Documents Retrieved",
      vi: "Số tài liệu ngữ cảnh trung bình được truy hồi",
      meaning: "Số đoạn tài liệu (chunk) trung bình mà hệ thống truy hồi từ Qdrant làm ngữ cảnh cho mỗi câu hỏi, sau khi rerank.",
    },
    {
      en: "RAG Query Rate (theo cây trồng)",
      vi: "Tần suất câu hỏi RAG theo cây trồng",
      meaning: "Số câu hỏi RAG mỗi giây, chia theo loại cây trồng đang được hỏi (lúa, cà phê, mía, ngô).",
    },
  ],
};

export function GrafanaPanels() {
  const [uid, setUid] = useState<DashboardUid>("vcd-overview");
  const [range, setRange] = useState<RangeValue>(DEFAULT_RANGE_BY_UID["vcd-overview"]);

  const handleSelectDashboard = (nextUid: DashboardUid) => {
    setUid(nextUid);
    setRange(DEFAULT_RANGE_BY_UID[nextUid]);
  };

  // kiosk = hide Grafana chrome; anonymous Viewer means no login prompt inside the iframe.
  const embedUrl = useMemo(() => {
    const params = new URLSearchParams({
      orgId: "1",
      kiosk: "",
      theme: "light",
      from: range,
      to: "now",
      refresh: "30s",
    });
    return `${GRAFANA_URL}/d/${uid}?${params.toString()}`;
  }, [uid, range]);

  const openUrl = `${GRAFANA_URL}/d/${uid}?orgId=1&from=${range}&to=now`;
  const glossary = PANEL_GLOSSARY[uid];

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px] text-primary">monitoring</span>
            Grafana — biểu đồ thời gian thực
          </CardTitle>
          <a
            href={openUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <span className="material-symbols-outlined text-[16px]">open_in_new</span>
            Mở trong Grafana
          </a>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Dashboard selector */}
        <div className="flex flex-wrap gap-1.5">
          {DASHBOARDS.map((d) => {
            const isActive = d.uid === uid;
            return (
              <button
                key={d.uid}
                onClick={() => handleSelectDashboard(d.uid)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  isActive
                    ? "bg-primary-container text-on-primary-container font-medium"
                    : "text-on-surface-variant hover:bg-surface-container-high"
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">{d.icon}</span>
                {d.label}
              </button>
            );
          })}
        </div>

        {/* Time range selector */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-on-surface-variant mr-1">Khoảng:</span>
          {RANGES.map((r) => {
            const isActive = r.value === range;
            return (
              <button
                key={r.value}
                onClick={() => setRange(r.value)}
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  isActive
                    ? "bg-secondary-container text-on-secondary-container font-medium"
                    : "text-on-surface-variant hover:bg-surface-container-high"
                }`}
              >
                {r.label}
              </button>
            );
          })}
        </div>

        {/* Embedded dashboard */}
        <div className="overflow-hidden rounded-xl border border-outline-variant bg-white">
          <iframe
            key={`${uid}-${range}`}
            title={`Grafana ${uid}`}
            src={embedUrl}
            className="w-full"
            style={{ height: 720, border: "none" }}
            loading="lazy"
          />
        </div>

        <p className="text-[11px] text-on-surface-variant">
          Nếu khung hiển thị trống: kiểm tra Grafana đang chạy ở <code>{GRAFANA_URL}</code> và đã bật
          embedding (<code>GF_SECURITY_ALLOW_EMBEDDING=true</code> + anonymous Viewer trong
          docker-compose).
        </p>

        {/* Vietnamese glossary for the English Grafana panel titles */}
        {glossary && (
          <div className="rounded-lg border border-outline-variant bg-surface-container-low p-3 space-y-2">
            <p className="text-xs font-medium text-on-surface">Giải thích các biểu đồ trong tab này:</p>
            <dl className="space-y-1.5">
              {glossary.map((g) => (
                <div key={g.en} className="text-xs leading-relaxed">
                  <dt className="inline font-medium text-on-surface">
                    {g.en} <span className="text-on-surface-variant font-normal">— {g.vi}:</span>
                  </dt>{" "}
                  <dd className="inline text-on-surface-variant">{g.meaning}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
