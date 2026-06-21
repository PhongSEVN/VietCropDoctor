import type { ExpertStats } from "@/types/expert";

interface KpiCardProps {
  icon: string;
  label: string;
  value: string | number;
  accent?: string; // tailwind text color for the icon
}

function KpiCard({ icon, label, value, accent = "text-primary" }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4 flex items-center gap-3">
      <div className={`rounded-lg bg-surface-container p-2 ${accent}`}>
        <span className="material-symbols-outlined">{icon}</span>
      </div>
      <div className="min-w-0">
        <p className="text-xs text-on-surface-variant truncate">{label}</p>
        <p className="text-xl font-bold text-on-surface">{value}</p>
      </div>
    </div>
  );
}

export function KpiCards({ stats }: { stats: ExpertStats }) {
  const avg =
    stats.avg_response_minutes === null
      ? "—"
      : stats.avg_response_minutes >= 60
        ? `${(stats.avg_response_minutes / 60).toFixed(1)} giờ`
        : `${stats.avg_response_minutes} phút`;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
      <KpiCard icon="inbox" label="Tổng yêu cầu" value={stats.total} />
      <KpiCard icon="pending" label="Chưa xử lý" value={stats.pending} accent="text-amber-600" />
      <KpiCard icon="autorenew" label="Đang xử lý" value={stats.in_progress} accent="text-blue-600" />
      <KpiCard icon="task_alt" label="Đã hoàn thành" value={stats.answered} accent="text-green-600" />
      <KpiCard icon="schedule" label="TG phản hồi TB" value={avg} accent="text-tertiary" />
      <KpiCard icon="calendar_month" label="Xử lý 7 ngày" value={stats.resolved_last7days} accent="text-secondary" />
    </div>
  );
}
