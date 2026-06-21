import type { AdminKpis } from "@/types/admin";

function KpiCard({ icon, label, value, accent = "text-primary" }: {
  icon: string;
  label: string;
  value: string | number;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className={`material-symbols-outlined text-[20px] ${accent}`}>{icon}</span>
        <p className="text-xs text-on-surface-variant truncate">{label}</p>
      </div>
      <p className="text-xl font-bold text-on-surface">{value}</p>
    </div>
  );
}

const fmtNum = (n: number) => n.toLocaleString("vi-VN");
const fmtPct = (n: number | null) => (n === null ? "—" : `${(n * 100).toFixed(1)}%`);

export function AdminKpiCards({ kpis }: { kpis: AdminKpis }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
      <KpiCard icon="group" label="Tổng người dùng" value={fmtNum(kpis.total_users)} />
      <KpiCard icon="person_add" label="User mới hôm nay" value={fmtNum(kpis.new_today)} accent="text-green-600" />
      <KpiCard icon="date_range" label="User mới tuần" value={fmtNum(kpis.new_week)} accent="text-green-600" />
      <KpiCard icon="calendar_month" label="User mới tháng" value={fmtNum(kpis.new_month)} accent="text-green-600" />
      <KpiCard icon="bolt" label="DAU" value={fmtNum(kpis.dau)} accent="text-amber-600" />
      <KpiCard icon="view_week" label="WAU" value={fmtNum(kpis.wau)} accent="text-amber-600" />
      <KpiCard icon="insights" label="MAU" value={fmtNum(kpis.mau)} accent="text-amber-600" />
      <KpiCard icon="autorenew" label="Retention" value={fmtPct(kpis.retention_rate)} accent="text-blue-600" />
      <KpiCard icon="trending_down" label="Churn" value={fmtPct(kpis.churn_rate)} accent="text-red-600" />
      <KpiCard icon="rate_review" label="Tổng feedback" value={fmtNum(kpis.total_feedback)} accent="text-tertiary" />
      <KpiCard icon="image" label="Ảnh đã upload" value={fmtNum(kpis.total_images)} accent="text-tertiary" />
      <KpiCard icon="smart_toy" label="Lượt phân tích AI" value={fmtNum(kpis.total_ai_analyses)} accent="text-primary" />
      <KpiCard icon="forum" label="Phản hồi chuyên gia" value={fmtNum(kpis.total_expert_responses)} accent="text-secondary" />
    </div>
  );
}
