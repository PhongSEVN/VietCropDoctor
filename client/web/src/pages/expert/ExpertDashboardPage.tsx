import { useEffect, useMemo, useState } from "react";

import { ExpertLayout, type ExpertTab } from "@/components/expert/ExpertLayout";
import { KpiCards } from "@/components/expert/KpiCards";
import { StatsCharts } from "@/components/expert/StatsCharts";
import { CaseFiltersBar } from "@/components/expert/CaseFiltersBar";
import { CaseTable } from "@/components/expert/CaseTable";
import { DiagnosesTable } from "@/components/expert/DiagnosesTable";
import { CaseDetailModal } from "@/components/expert/CaseDetailModal";
import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAllDiagnoses, useExpertQueue } from "@/hooks/useExpert";
import { deriveExpertStats, getOnlineExperts, promoteDiagnosis } from "@/lib/expert-api";
import type { DiagnosisItem, OnlineExpert } from "@/types/expert";

const POLL_INTERVAL_MS = 30_000; // lightweight "realtime"; TODO(backend): replace with WS/SSE

const MISSING_BACKEND_HINT =
  "Các endpoint /expert/* chưa được backend cài đặt (xem TODO trong lib/expert-api.ts). " +
  "Khi router expert sẵn sàng, dashboard sẽ tự hiển thị dữ liệu.";

const TAB_META: Record<ExpertTab, { title: string; subtitle: string }> = {
  overview: { title: "Tổng quan", subtitle: "Tình hình xử lý yêu cầu của chuyên gia" },
  queue: { title: "Hàng đợi xử lý", subtitle: "Danh sách ảnh người dùng gửi nhờ tư vấn" },
  diagnoses: { title: "Tất cả ảnh chẩn đoán", subtitle: "Mọi ảnh đã chẩn đoán, kể cả khi người dùng chưa phản hồi" },
  stats: { title: "Thống kê", subtitle: "Phân tích yêu cầu theo thời gian, bệnh, loại cây" },
  experts: { title: "Chuyên gia", subtitle: "Trạng thái online và phân bổ ca" },
};

export default function ExpertDashboardPage() {
  const [tab, setTab] = useState<ExpertTab>("overview");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Bumped whenever a case modal closes, so the "Tất cả ảnh" tab refetches statuses.
  const [diagRefresh, setDiagRefresh] = useState(0);
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

            {tab === "diagnoses" && (
              <DiagnosesTab refreshKey={diagRefresh} onOpenCase={setSelectedId} />
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
        <CaseDetailModal
          caseId={selectedId}
          onClose={() => {
            setSelectedId(null);
            setDiagRefresh((n) => n + 1);
          }}
          onUpdated={refetch}
        />
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

// All diagnoses tab — every image (incl. those without user feedback).

function DiagnosesTab({
  refreshKey,
  onOpenCase,
}: {
  refreshKey: number;
  onOpenCase: (caseId: string) => void;
}) {
  const { diagnoses, loading, error, pendingOnly, setPendingOnly, refetch } = useAllDiagnoses();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  // Refetch when a case modal closes (status may have changed).
  useEffect(() => {
    if (refreshKey > 0) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function handleSelect(item: DiagnosisItem) {
    setPromoteError(null);
    // Already has a case → open it directly.
    if (item.feedback_id) {
      onOpenCase(item.feedback_id);
      return;
    }
    // No feedback yet → create a case from this diagnosis, then open it.
    setBusyId(item.chat_id);
    try {
      const created = await promoteDiagnosis(item.chat_id);
      onOpenCase(created.id);
    } catch (e) {
      setPromoteError(e instanceof Error ? e.message : "Không mở được ảnh để phản hồi");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && diagnoses.length === 0) return <LoadingState label="Đang tải tất cả ảnh chẩn đoán..." />;
  if (error && diagnoses.length === 0)
    return <ErrorState message={error} onRetry={refetch} hint={MISSING_BACKEND_HINT} />;

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base text-on-surface">
            Tất cả ảnh ({diagnoses.length})
          </CardTitle>
          <label className="flex items-center gap-2 text-sm text-on-surface-variant cursor-pointer select-none">
            <input
              type="checkbox"
              checked={pendingOnly}
              onChange={(e) => setPendingOnly(e.target.checked)}
              className="accent-primary"
            />
            Chỉ ảnh chưa phản hồi
          </label>
        </div>
        {promoteError && <p className="text-xs text-error mt-2">{promoteError}</p>}
      </CardHeader>
      <CardContent>
        {diagnoses.length === 0 ? (
          <EmptyState
            icon="photo_library"
            title="Chưa có ảnh chẩn đoán nào"
            description="Khi người dùng chẩn đoán ảnh, chúng sẽ xuất hiện ở đây kể cả khi chưa gửi phản hồi."
          />
        ) : (
          <>
            <p className="text-xs text-on-surface-variant mb-2">
              Bấm vào một ảnh để phản hồi. Ảnh "Chưa phản hồi" sẽ tự tạo ca xử lý khi bạn mở; khi
              bạn xác nhận chẩn đoán, ảnh được đưa vào tập dữ liệu vàng để retrain.
            </p>
            <DiagnosesTable items={diagnoses} busyId={busyId} onSelect={handleSelect} />
          </>
        )}
      </CardContent>
    </Card>
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
