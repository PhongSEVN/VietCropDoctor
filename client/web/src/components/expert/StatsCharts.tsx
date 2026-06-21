import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDiseaseName } from "@/lib/api";
import type { ExpertStats } from "@/types/expert";

const COLORS = ["#006b2c", "#00873a", "#62df7d", "#fe932c", "#a72d51", "#c74668"];

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-on-surface">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function StatsCharts({ stats }: { stats: ExpertStats }) {
  const diseaseData = stats.top_diseases.map((d) => ({
    name: formatDiseaseName(d.disease),
    value: d.count,
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Requests by day */}
      <ChartCard title="Yêu cầu theo ngày (7 ngày)">
        {stats.by_day.some((d) => d.count > 0) ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={stats.by_day} margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#006b2c" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-on-surface-variant text-center py-16">Chưa có dữ liệu.</p>
        )}
      </ChartCard>

      {/* Disease distribution */}
      <ChartCard title="Phân loại bệnh phổ biến">
        {diseaseData.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={diseaseData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} labelLine={false}>
                {diseaseData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-on-surface-variant text-center py-16">Chưa có dữ liệu.</p>
        )}
      </ChartCard>

      {/* Top crops */}
      <ChartCard title="Top loại cây gửi nhiều">
        {stats.top_crops.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stats.top_crops} margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
              <XAxis dataKey="crop" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {stats.top_crops.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-on-surface-variant text-center py-16">Chưa có dữ liệu.</p>
        )}
      </ChartCard>
    </div>
  );
}
