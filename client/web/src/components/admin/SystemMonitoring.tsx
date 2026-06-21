import { ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemHealth } from "@/hooks/useAdmin";
import type { ServiceHealth } from "@/types/admin";

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
    </div>
  );
}
