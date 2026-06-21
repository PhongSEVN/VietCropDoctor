import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
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
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type AlertItem,
  type AnalyticsSummary,
  type CropDistributionItem,
  type TrendPoint,
  formatDiseaseName,
  getAnalyticsSummary,
  getCropDistribution,
  getDiseaseTrend,
  getRecentAlerts,
} from "@/lib/api";

// Colour palette
const CHART_COLORS = ["#16a34a", "#22c55e", "#4ade80", "#86efac", "#bbf7d0", "#f59e0b", "#ef4444"];

const SEVERITY_COLORS: Record<string, string> = {
  healthy: "bg-green-100 text-green-800",
  mild: "bg-yellow-100 text-yellow-800",
  moderate: "bg-orange-100 text-orange-800",
  severe: "bg-red-100 text-red-800",
  high: "bg-red-100 text-red-800",
  medium: "bg-orange-100 text-orange-800",
};

// Summary card
function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="pt-6 pb-4">
        <p className="text-xs text-[var(--muted)] mb-1">{label}</p>
        <p className="text-2xl font-bold text-[var(--primary-dark)]">{value}</p>
      </CardContent>
    </Card>
  );
}

// Disease trend chart
function TrendChart({ data }: { data: TrendPoint[] }) {
  // Group by disease to build recharts series
  const diseases = [...new Set(data.map((d) => d.disease))];
  const dateMap = new Map<string, Record<string, number>>();
  for (const d of data) {
    if (!dateMap.has(d.date)) dateMap.set(d.date, { date: d.date as unknown as number });
    dateMap.get(d.date)![d.disease] = d.count;
  }
  const chartData = [...dateMap.values()].sort((a, b) =>
    String(a.date).localeCompare(String(b.date))
  );

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10 }}
          tickFormatter={(v) => String(v).slice(5)}
        />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip formatter={(v, name) => [v, formatDiseaseName(String(name))]} />
        <Legend formatter={(v) => formatDiseaseName(String(v))} />
        {diseases.slice(0, 7).map((dis, i) => (
          <Line
            key={dis}
            type="monotone"
            dataKey={dis}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// Crop distribution pie
function CropPie({ data }: { data: CropDistributionItem[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="crop"
          cx="50%"
          cy="50%"
          outerRadius={90}
          label={({ crop, percent }) =>
            `${crop} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
          labelLine={false}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v, name) => [v, name]} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// Alerts table
function AlertsTable({ alerts }: { alerts: AlertItem[] }) {
  if (!alerts.length) {
    return <p className="text-sm text-[var(--muted)] py-4 text-center">Chưa có cảnh báo nào.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-[var(--muted)] text-xs">
            <th className="text-left py-2 pr-4 font-medium">Thời gian</th>
            <th className="text-left py-2 pr-4 font-medium">Bệnh</th>
            <th className="text-left py-2 pr-4 font-medium">Cây trồng</th>
            <th className="text-left py-2 pr-4 font-medium">Mức độ</th>
            <th className="text-right py-2 font-medium">Độ tin cậy</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.alert_id} className="border-b border-[var(--border)] hover:bg-[var(--primary-light)]">
              <td className="py-2 pr-4 text-[var(--muted)] whitespace-nowrap">
                {String(a.timestamp).slice(0, 16).replace("T", " ")}
              </td>
              <td className="py-2 pr-4 max-w-[180px] truncate">{formatDiseaseName(a.disease)}</td>
              <td className="py-2 pr-4">{a.crop || "—"}</td>
              <td className="py-2 pr-4">
                <Badge className={SEVERITY_COLORS[a.severity] ?? "bg-gray-100 text-gray-800"}>
                  {a.severity}
                </Badge>
              </td>
              <td className="py-2 text-right">{(a.confidence * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page
export default function AnalyticsPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [crops, setCrops] = useState<CropDistributionItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getAnalyticsSummary(),
      getDiseaseTrend(30),
      getCropDistribution(),
      getRecentAlerts(50),
    ])
      .then(([s, t, c, a]) => {
        setSummary(s);
        setTrend(t.data);
        setCrops(c);
        setAlerts(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Lỗi tải dữ liệu"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="min-h-screen py-10 px-4">
      {/* Header */}
      <div className="max-w-6xl mx-auto mb-8 flex items-center gap-4">
        <button
          onClick={() => navigate("/")}
          className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors"
        >
          ← Trang chủ
        </button>
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)]">Analytics Dashboard</h1>
          <p className="text-sm text-[var(--muted)]">Thống kê chẩn đoán và cảnh báo theo thời gian thực</p>
        </div>
      </div>

      {loading && (
        <div className="max-w-6xl mx-auto text-center text-[var(--muted)] animate-pulse py-20">
          Đang tải dữ liệu analytics...
        </div>
      )}

      {error && (
        <div className="max-w-6xl mx-auto text-center text-red-500 py-20">
          {error}
          <p className="text-sm text-[var(--muted)] mt-2">
            Đảm bảo service analytics (port 8004) đang chạy.
          </p>
        </div>
      )}

      {!loading && !error && (
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Summary cards */}
          {summary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Hôm nay" value={summary.today_count} />
              <StatCard label="Tuần này" value={summary.week_count} />
              <StatCard label="Tháng này" value={summary.month_count} />
              <StatCard
                label="Bệnh phổ biến nhất"
                value={
                  summary.top_diseases[0]
                    ? formatDiseaseName(summary.top_diseases[0].disease).split("—")[1]?.trim() ??
                    summary.top_diseases[0].disease
                    : "—"
                }
              />
            </div>
          )}

          {/* Disease trend + crop pie */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Xu hướng bệnh (30 ngày)</CardTitle>
              </CardHeader>
              <CardContent>
                {trend.length > 0 ? (
                  <TrendChart data={trend} />
                ) : (
                  <p className="text-sm text-[var(--muted)] text-center py-16">
                    Chưa có dữ liệu xu hướng.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Phân bố cây trồng</CardTitle>
              </CardHeader>
              <CardContent>
                {crops.length > 0 ? (
                  <CropPie data={crops} />
                ) : (
                  <p className="text-sm text-[var(--muted)] text-center py-16">
                    Chưa có dữ liệu.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Top diseases table */}
          {summary && summary.top_diseases.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Top bệnh phát hiện (30 ngày)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {summary.top_diseases.map((d, i) => {
                    const max = summary.top_diseases[0].count;
                    return (
                      <div key={d.disease} className="flex items-center gap-3">
                        <span className="text-xs text-[var(--muted)] w-4">{i + 1}</span>
                        <div className="flex-1">
                          <div className="flex justify-between text-xs mb-0.5">
                            <span className={i === 0 ? "font-medium" : "text-[var(--muted)]"}>
                              {formatDiseaseName(d.disease)}
                            </span>
                            <span className="text-[var(--muted)]">{d.count}</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-[var(--border)]">
                            <div
                              className={`h-1.5 rounded-full transition-all ${i === 0 ? "bg-[var(--primary)]" : "bg-gray-300"
                                }`}
                              style={{ width: `${(d.count / max) * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recent alerts */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Cảnh báo gần đây</CardTitle>
            </CardHeader>
            <CardContent>
              <AlertsTable alerts={alerts} />
            </CardContent>
          </Card>
        </div>
      )}
    </main>
  );
}
