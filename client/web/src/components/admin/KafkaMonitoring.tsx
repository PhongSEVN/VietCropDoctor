import { useCallback, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getKafkaOverview } from "@/lib/admin-api";
import type { KafkaOverview } from "@/types/admin";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" }) {
  const valueClass =
    tone === "ok" ? "text-green-600" : tone === "bad" ? "text-error" : "text-on-surface";
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <p className="text-xs text-on-surface-variant">{label}</p>
      <p className={`text-lg font-bold ${valueClass}`}>{value}</p>
    </div>
  );
}

function lagTone(lag: number): string {
  if (lag === 0) return "text-green-600";
  if (lag < 1000) return "text-amber-600";
  return "text-error font-semibold";
}

export function KafkaMonitoring() {
  const [data, setData] = useState<KafkaOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getKafkaOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được dữ liệu Kafka"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refetch();
    const t = setInterval(refetch, 15_000); // near-realtime
    return () => clearInterval(t);
  }, [refetch]);

  if (loading && !data) return <LoadingState label="Đang truy vấn Kafka (qua Prometheus)..." />;
  if (error && !data)
    return (
      <ErrorState
        message={error}
        onRetry={refetch}
        hint="Cần kafka-exporter (:9308) + Prometheus đang chạy. Kiểm tra job 'kafka' trong Prometheus."
      />
    );
  if (!data) return null;

  const totalLag = data.consumer_groups.reduce((sum, g) => sum + g.lag, 0);

  return (
    <div className="space-y-5">
      {/* Top stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Exporter"
          value={data.exporter_up ? "UP" : "DOWN"}
          tone={data.exporter_up ? "ok" : "bad"}
        />
        <Stat label="Brokers" value={String(data.brokers)} tone={data.brokers > 0 ? "ok" : "bad"} />
        <Stat label="Số topic" value={String(data.topics.length)} />
        <Stat
          label="Tổng lag"
          value={totalLag.toLocaleString("vi-VN")}
          tone={totalLag === 0 ? "ok" : totalLag > 1000 ? "bad" : undefined}
        />
      </div>

      {/* Topics */}
      <Card className="border-outline-variant bg-surface-container-lowest">
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base text-on-surface">Topics</CardTitle>
          <a
            href={data.kafka_ui_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <span className="material-symbols-outlined text-[16px]">open_in_new</span>
            Mở Kafka UI
          </a>
        </CardHeader>
        <CardContent>
          {data.topics.length === 0 ? (
            <p className="text-sm text-on-surface-variant">Chưa có topic nào (hoặc exporter chưa sẵn sàng).</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                    <th className="py-2 pr-3 font-medium">Topic</th>
                    <th className="py-2 pr-3 font-medium">Partitions</th>
                    <th className="py-2 font-medium">Tổng messages</th>
                  </tr>
                </thead>
                <tbody>
                  {data.topics.map((t) => (
                    <tr key={t.topic} className="border-b border-outline-variant/60">
                      <td className="py-2 pr-3 font-medium text-on-surface">{t.topic}</td>
                      <td className="py-2 pr-3 text-on-surface-variant">{t.partitions}</td>
                      <td className="py-2 text-on-surface-variant">{t.messages.toLocaleString("vi-VN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Consumer groups */}
      <Card className="border-outline-variant bg-surface-container-lowest">
        <CardHeader className="pb-2">
          <CardTitle className="text-base text-on-surface">Consumer groups &amp; lag</CardTitle>
        </CardHeader>
        <CardContent>
          {data.consumer_groups.length === 0 ? (
            <p className="text-sm text-on-surface-variant">
              Chưa có consumer group nào hoạt động. Lag chỉ xuất hiện khi đã có dịch vụ consume (rag-engine, analytics).
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                    <th className="py-2 pr-3 font-medium">Consumer group</th>
                    <th className="py-2 pr-3 font-medium">Topic</th>
                    <th className="py-2 pr-3 font-medium">Đã đọc (offset)</th>
                    <th className="py-2 font-medium">Lag</th>
                  </tr>
                </thead>
                <tbody>
                  {data.consumer_groups.map((g) => (
                    <tr key={`${g.group}-${g.topic}`} className="border-b border-outline-variant/60">
                      <td className="py-2 pr-3 font-medium text-on-surface">{g.group}</td>
                      <td className="py-2 pr-3 text-on-surface-variant">{g.topic}</td>
                      <td className="py-2 pr-3 text-on-surface-variant">
                        {g.committed_offset.toLocaleString("vi-VN")}
                      </td>
                      <td className={`py-2 ${lagTone(g.lag)}`}>{g.lag.toLocaleString("vi-VN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[11px] text-on-surface-variant mt-3">
            Lag = số message đã vào topic nhưng consumer chưa xử lý. Lag tăng liên tục ⇒ consumer
            chậm/chết. Dữ liệu lấy từ kafka-exporter qua Prometheus, làm mới mỗi 15s.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
