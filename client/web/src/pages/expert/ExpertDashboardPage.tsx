import { useEffect, useMemo, useState } from "react";

import { ExpertLayout, type ExpertTab } from "@/components/expert/ExpertLayout";
import { KpiCards } from "@/components/expert/KpiCards";
import { StatsCharts } from "@/components/expert/StatsCharts";
import { CaseFiltersBar } from "@/components/expert/CaseFiltersBar";
import { CaseTable } from "@/components/expert/CaseTable";
import { CaseDetailModal } from "@/components/expert/CaseDetailModal";
import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useExpertQueue } from "@/hooks/useExpert";
import { deriveExpertStats, getOnlineExperts } from "@/lib/expert-api";
import type { OnlineExpert } from "@/types/expert";

const POLL_INTERVAL_MS = 30_000; // lightweight "realtime"; TODO(backend): replace with WS/SSE

const MISSING_BACKEND_HINT =
  "Các endpoint /expert/* chưa được backend cài đặt (xem TODO trong lib/expert-api.ts). " +
  "Khi router expert sẵn sàng, dashboard sẽ tự hiển thị dữ liệu.";

const TAB_META: Record<ExpertTab, { title: string; subtitle: string }> = {
  overview: { title: "Tổng quan", subtitle: "Tình hình xử lý yêu cầu của chuyên gia" },
  queue: { title: "Hàng đợi xử lý", subtitle: "Danh sách ảnh người dùng gửi nhờ tư vấn" },
  stats: { title: "Thống kê", subtitle: "Phân tích yêu cầu theo thời gian, bệnh, loại cây" },
  experts: { title: "Chuyên gia", subtitle: "Trạng thái online và phân bổ ca" },
};

export default function ExpertDashboardPage() {
  const [tab, setTab] = useState<ExpertTab>("overview");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { cases, allCases, crops, loading, error, filters, setFilters, refetch } = useExpertQueue();

  const stats = useMemo(() => deriveExpertStats(allCases), [allCases]);

  // Lightweight polling for near-realtime queue updates.
  useEffect(() => {
    const t = setInterval(refetch, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [refetch]);

  const meta = TAB_META[tab];

  return (
    <ExpertLayout active={tab} onNavigate={setTab} pendingCount={stats.pending}>
      {/* Header */}
      <header className="flex items-center justify-between gap-4 border-b border-outline-variant px-5 h-16 bg-surface">
        <div>
          <h1 className="text-lg font-bold text-on-surface">{meta.title}</h1>
          <p className="text-xs text-on-surface-variant">{meta.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refetch}
            className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container-high transition-colors"
            aria-label="Làm mới"
            title="Làm mới"
          >
            <span className="material-symbols-outlined">refresh</span>
          </button>
          <div className="relative">
            <span className="material-symbols-outlined text-on-surface-variant">notifications</span>
            {stats.pending > 0 && (
              <span className="absolute -top-1 -right-1 rounded-full bg-error text-on-error text-[10px] px-1">
                {stats.pending}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-5 space-y-5">
        {loading && allCases.length === 0 && <LoadingState label="Đang tải hàng đợi..." />}
        {error && allCases.length === 0 && (
          <ErrorState message={error} onRetry={refetch} hint={MISSING_BACKEND_HINT} />
        )}

        {!error && !(loading && allCases.length === 0) && (
          <>
            {tab === "overview" && (
              <OverviewTab
                statsNode={<KpiCards stats={stats} />}
                chartsNode={<StatsCharts stats={stats} />}
                recent={cases.slice(0, 8)}
                empty={allCases.length === 0}
                onSelect={setSelectedId}
              />
            )}

            {tab === "queue" && (
              <Card className="border-outline-variant bg-surface-container-lowest">
                <CardHeader className="pb-3 space-y-3">
                  <CaseFiltersBar
                    filters={filters}
                    crops={crops}
                    onChange={setFilters}
                    resultCount={cases.length}
                  />
                </CardHeader>
                <CardContent>
                  {cases.length === 0 ? (
                    <EmptyState
                      icon="inbox"
                      title="Không có yêu cầu nào"
                      description={allCases.length === 0 ? MISSING_BACKEND_HINT : "Thử đổi bộ lọc tìm kiếm."}
                    />
                  ) : (
                    <CaseTable cases={cases} onSelect={setSelectedId} />
                  )}
                </CardContent>
              </Card>
            )}

            {tab === "stats" && (
              <div className="space-y-5">
                <KpiCards stats={stats} />
                <StatsCharts stats={stats} />
              </div>
            )}

            {tab === "experts" && <OnlineExpertsPanel />}
          </>
        )}
      </main>

      {selectedId && (
        <CaseDetailModal caseId={selectedId} onClose={() => setSelectedId(null)} onUpdated={refetch} />
      )}
    </ExpertLayout>
  );
}

// Overview tab

function OverviewTab({
  statsNode,
  chartsNode,
  recent,
  empty,
  onSelect,
}: {
  statsNode: React.ReactNode;
  chartsNode: React.ReactNode;
  recent: import("@/types/expert").ExpertCase[];
  empty: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      {statsNode}
      {chartsNode}
      <Card className="border-outline-variant bg-surface-container-lowest">
        <CardHeader className="pb-2">
          <CardTitle className="text-base text-on-surface">Yêu cầu mới nhất</CardTitle>
        </CardHeader>
        <CardContent>
          {empty ? (
            <EmptyState icon="inbox" title="Chưa có yêu cầu" description={MISSING_BACKEND_HINT} />
          ) : (
            <CaseTable cases={recent} onSelect={onSelect} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Online experts panel

function OnlineExpertsPanel() {
  const [experts, setExperts] = useState<OnlineExpert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getOnlineExperts()
      .then(setExperts)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách chuyên gia"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Đang tải danh sách chuyên gia..." />;
  if (error) return <ErrorState message={error} hint={MISSING_BACKEND_HINT} />;
  if (experts.length === 0)
    return <EmptyState icon="groups" title="Chưa có chuyên gia online" description={MISSING_BACKEND_HINT} />;

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-on-surface">Chuyên gia đang trực</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-outline-variant/60">
          {experts.map((ex) => (
            <li key={ex.id} className="flex items-center gap-3 py-2">
              <span className={`h-2.5 w-2.5 rounded-full ${ex.online ? "bg-green-500" : "bg-gray-300"}`} />
              <span className="text-sm text-on-surface font-medium">{ex.name}</span>
              <span className="ml-auto text-xs text-on-surface-variant">{ex.active_cases} ca đang phụ trách</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
