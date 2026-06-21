import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getRegionDistribution } from "@/lib/admin-api";
import { formatDiseaseName, getAnalyticsSummary, getCropDistribution } from "@/lib/api";
import type { RegionCount } from "@/types/admin";
import type { AnalyticsSummary, CropDistributionItem } from "@vcd/types";

const COLORS = ["#006b2c", "#00873a", "#62df7d", "#fe932c", "#a72d51", "#c74668"];

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2"><CardTitle className="text-base text-on-surface">{title}</CardTitle></CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Pending({ note }: { note: string }) {
  return <p className="text-xs text-on-surface-variant text-center py-12">{note}</p>;
}

export function TrendAnalysis() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [crops, setCrops] = useState<CropDistributionItem[] | null>(null);
  const [regions, setRegions] = useState<RegionCount[] | null>(null);

  useEffect(() => {
    getAnalyticsSummary().then(setSummary).catch(() => setSummary(null));
    getCropDistribution().then(setCrops).catch(() => setCrops(null));
    getRegionDistribution().then(setRegions).catch(() => setRegions(null));
  }, []);

  const diseaseData = (summary?.top_diseases ?? []).map((d) => ({ name: formatDiseaseName(d.disease), count: d.count }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ChartCard title="Top cây trồng gửi nhiều nhất">
        {crops && crops.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={crops} layout="vertical" margin={{ top: 4, right: 16, left: 20, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="crop" tick={{ fontSize: 11 }} width={70} />
              <Tooltip />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {crops.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <Pending note="Chưa có dữ liệu (service analytics :8004)." />}
      </ChartCard>

      <ChartCard title="Top bệnh phổ biến">
        {diseaseData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={diseaseData} layout="vertical" margin={{ top: 4, right: 16, left: 20, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 9 }} width={120} />
              <Tooltip />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {diseaseData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <Pending note="Chưa có dữ liệu xu hướng bệnh." />}
      </ChartCard>

      <ChartCard title="Xu hướng theo khu vực">
        {regions && regions.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={regions} margin={{ top: 8, right: 16, left: -10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#bdcaba" />
              <XAxis dataKey="region" tick={{ fontSize: 10 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {regions.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Pending note="TODO(backend): GET /admin/analytics/regions + thu thập tỉnh/thành khi upload. Bản đồ heatmap cần thư viện map (vd react-leaflet) — chưa cài." />
        )}
      </ChartCard>

      <ChartCard title="Dự báo (forecast)">
        <Pending note="TODO(backend): dự báo bệnh theo mùa vụ / số lượng yêu cầu / tải chuyên gia — cần mô hình time-series (Prophet/ARIMA) trên ClickHouse khi dữ liệu đủ lớn." />
      </ChartCard>
    </div>
  );
}
