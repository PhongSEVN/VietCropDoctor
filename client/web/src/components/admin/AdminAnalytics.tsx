import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AdminKpiCards } from "./AdminKpiCards";
import { ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAdminKpis } from "@/hooks/useAdmin";
import { getConfidenceDistribution, getUserGrowth } from "@/lib/admin-api";
import { getCropDistribution } from "@/lib/api";
import type { CropDistributionItem } from "@vcd/types";
import type { ConfidenceBucket, UserGrowthPoint } from "@/types/admin";

const COLORS = ["#006b2c", "#00873a", "#62df7d", "#fe932c", "#a72d51", "#c74668"];

function Pending({ note }: { note: string }) {
  return <p className="text-xs text-on-surface-variant text-center py-12">{note}</p>;
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2"><CardTitle className="text-base text-on-surface">{title}</CardTitle></CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function AdminAnalytics() {
  const kpis = useAdminKpis();
  const [growth, setGrowth] = useState<UserGrowthPoint[] | null>(null);
  const [confidence, setConfidence] = useState<ConfidenceBucket[] | null>(null);
  const [crops, setCrops] = useState<CropDistributionItem[] | null>(null);

  useEffect(() => {
    getUserGrowth(30).then(setGrowth).catch(() => setGrowth(null));
    getConfidenceDistribution().then(setConfidence).catch(() => setConfidence(null));
    getCropDistribution().then(setCrops).catch(() => setCrops(null));
  }, []);

  return (
    <div className="space-y-5">
      {/* KPI */}
      {kpis.loading && !kpis.data && <LoadingState label="Đang tải KPI..." />}
      {kpis.error && !kpis.data && (
        <ErrorState message={kpis.error} onRetry={kpis.refetch} hint="Endpoint /admin/kpis chưa được backend cài đặt." />
      )}
      {kpis.data && <AdminKpiCards kpis={kpis.data} />}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Tăng trưởng người dùng (30 ngày)">
          {growth && growth.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={growth} margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                <Tooltip /><Legend />
                <Line type="monotone" dataKey="new_users" name="Mới" stroke="#006b2c" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="active_users" name="Active" stroke="#fe932c" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="returning_users" name="Quay lại" stroke="#a72d51" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <Pending note="TODO(backend): GET /admin/analytics/user-growth (DAU/WAU/returning từ ClickHouse)." />
          )}
        </ChartCard>

        <ChartCard title="Phân bố Confidence Score (AI)">
          {confidence && confidence.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={confidence} margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {confidence.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Pending note="TODO(backend): GET /admin/analytics/confidence-distribution." />
          )}
        </ChartCard>

        <ChartCard title="Phân bố cây trồng (ClickHouse)">
          {crops && crops.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={crops} dataKey="count" nameKey="crop" cx="50%" cy="50%" outerRadius={90} labelLine={false}
                  label={({ crop, percent }) => `${crop} ${((percent ?? 0) * 100).toFixed(0)}%`}>
                  {crops.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <Pending note="Chưa có dữ liệu cây trồng (service analytics :8004)." />
          )}
        </ChartCard>

        <ChartCard title="Ghi chú nguồn dữ liệu">
          <ul className="text-xs text-on-surface-variant space-y-1 list-disc pl-4 py-2">
            <li><b>REAL</b>: phân bố cây trồng dùng <code>/analytics/crop-distribution</code> (ClickHouse).</li>
            <li><b>TODO</b>: user-growth, confidence-distribution, KPI tổng hợp cần endpoint <code>/admin/*</code>.</li>
            <li>Khi backend sẵn sàng, các chart trên tự render — không cần sửa frontend.</li>
          </ul>
        </ChartCard>
      </div>
    </div>
  );
}
