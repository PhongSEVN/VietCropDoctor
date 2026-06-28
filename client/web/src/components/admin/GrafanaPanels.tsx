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
] as const;

type DashboardUid = (typeof DASHBOARDS)[number]["uid"];
type RangeValue = (typeof RANGES)[number]["value"];

export function GrafanaPanels() {
  const [uid, setUid] = useState<DashboardUid>("vcd-overview");
  const [range, setRange] = useState<RangeValue>("now-6h");

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
                onClick={() => setUid(d.uid)}
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
      </CardContent>
    </Card>
  );
}
