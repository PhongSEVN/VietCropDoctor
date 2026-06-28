import { useCallback, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemHealth } from "@/hooks/useAdmin";
import { getGpuOverview } from "@/lib/admin-api";
import type { GpuOverview, ServiceHealth } from "@/types/admin";

const STATUS_DOT: Record<ServiceHealth["status"], string> = {
  up: "bg-green-500",
  down: "bg-red-500",
  degraded: "bg-amber-500",
  unknown: "bg-gray-400",
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <p className="text-xs text-on-surface-variant">{label}</p>
      <p className="text-lg font-bold text-on-surface">{value}</p>
    </div>
  );
}

export function SystemMonitoring() {
  const { data, loading, error, refetch } = useSystemHealth();

  if (loading && !data) return <LoadingState label="Đang kiểm tra hệ thống..." />;
  if (error && !data) return <ErrorState message={error} onRetry={refetch} hint="Gateway /api/services không phản hồi." />;
  if (!data) return null;

  const ms = (n?: number | null) => (n === null || n === undefined ? "—" : `${n} ms`);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="API requests" value={data.api_requests_total?.toLocaleString("vi-VN") ?? "—"} />
        <Metric label="Response time" value={ms(data.avg_response_ms)} />
        <Metric label="Error rate" value={data.error_rate === null || data.error_rate === undefined ? "—" : `${(data.error_rate * 100).toFixed(2)}%`} />
        <Metric label="Queue jobs" value={data.queue_jobs?.toString() ?? "—"} />
      </div>

      <Card className="border-outline-variant bg-surface-container-lowest">
        <CardHeader className="pb-2">
          <CardTitle className="text-base text-on-surface">Trạng thái dịch vụ</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {data.services.map((s) => (
              <div key={s.name} className="flex items-center gap-2 rounded-lg border border-outline-variant px-3 py-2">
                <span className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[s.status]}`} />
                <span className="text-sm font-medium text-on-surface flex-1 truncate">{s.name}</span>
                <span className="text-xs text-on-surface-variant">
                  {s.status === "up" ? ms(s.elapsed_ms) : s.status}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-on-surface-variant mt-3">
            CPU/RAM/Storage, error rate và queue jobs cần Prometheus — TODO(backend): mở rộng
            /api/services hoặc thêm /admin/metrics. (Redis/ClickHouse/PostgreSQL trạng thái đã có
            qua health aggregator.)
          </p>
        </CardContent>
      </Card>

      <GpuCard />
    </div>
  );
}

function gb(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function tempTone(c: number): string {
  if (c >= 85) return "text-error";
  if (c >= 70) return "text-amber-600";
  return "text-green-600";
}

/** GPU stats from nvidia_gpu_exporter (via /api/admin/gpu → Prometheus). */
function GpuCard() {
  const [data, setData] = useState<GpuOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    getGpuOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được GPU"));
  }, []);

  useEffect(() => {
    refetch();
    const t = setInterval(refetch, 15_000);
    return () => clearInterval(t);
  }, [refetch]);

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-on-surface flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px] text-primary">memory_alt</span>
          GPU
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && !data && (
          <p className="text-sm text-error">{error}</p>
        )}
        {data && !data.available && (
          <p className="text-sm text-on-surface-variant">
            Không có dữ liệu GPU. Cần chạy <code>gpu-exporter</code> (cấu hình GPU passthrough) — xem
            ghi chú bên dưới.
          </p>
        )}
        {data && data.available && (
          <div className="space-y-4">
            {data.gpus.map((g) => {
              const memPct = g.mem_total_bytes
                ? (g.mem_used_bytes / g.mem_total_bytes) * 100
                : 0;
              return (
                <div key={g.uuid} className="space-y-2">
                  <p className="text-sm font-medium text-on-surface">{g.name}</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-3">
                      <p className="text-xs text-on-surface-variant">Tải GPU</p>
                      <p className="text-lg font-bold text-on-surface">{g.util_pct}%</p>
                    </div>
                    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-3">
                      <p className="text-xs text-on-surface-variant">VRAM</p>
                      <p className="text-lg font-bold text-on-surface">
                        {gb(g.mem_used_bytes)}
                        <span className="text-xs font-normal text-on-surface-variant"> / {gb(g.mem_total_bytes)}</span>
                      </p>
                    </div>
                    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-3">
                      <p className="text-xs text-on-surface-variant">Nhiệt độ</p>
                      <p className={`text-lg font-bold ${tempTone(g.temp_c)}`}>{g.temp_c}°C</p>
                    </div>
                    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-3">
                      <p className="text-xs text-on-surface-variant">Công suất</p>
                      <p className="text-lg font-bold text-on-surface">{g.power_w} W</p>
                    </div>
                  </div>
                  {/* VRAM usage bar */}
                  <div className="h-1.5 w-full rounded-full bg-surface-container-high overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.min(memPct, 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
            <p className="text-[11px] text-on-surface-variant">
              Cập nhật mỗi 15s từ nvidia_gpu_exporter qua Prometheus. Biểu đồ theo thời gian xem ở
              Grafana → dashboard "Hệ thống".
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
