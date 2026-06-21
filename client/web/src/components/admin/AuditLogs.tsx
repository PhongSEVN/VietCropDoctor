import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useAuditLogs } from "@/hooks/useAdmin";
import { downloadCsv } from "@/lib/admin-api";

const MISSING_HINT = "Endpoint /admin/audit chưa được backend cài đặt (xem TODO trong lib/admin-api.ts).";

function fmt(iso: string): string {
  return iso.slice(0, 19).replace("T", " ");
}

export function AuditLogs() {
  const { data, loading, error, filters, setFilters, refetch } = useAuditLogs();

  function exportCsv() {
    const rows = (data?.items ?? []).map((l) => ({
      timestamp: l.timestamp,
      actor: l.actor_name ?? l.actor_id,
      action: l.action,
      target: l.target ?? "",
      ip: l.ip ?? "",
      user_agent: l.user_agent ?? "",
    }));
    downloadCsv("audit-logs.csv", rows);
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">search</span>
            <input
              type="search"
              value={filters.search}
              onChange={(e) => setFilters({ search: e.target.value })}
              placeholder="Tìm theo người thực hiện, hành động, target..."
              className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest pl-8 pr-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <input
            value={filters.action === "all" ? "" : filters.action}
            onChange={(e) => setFilters({ action: e.target.value.trim() || "all" })}
            placeholder="Lọc action (vd: user.lock)"
            className="h-9 rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface"
          />
          <Button size="sm" variant="outline" onClick={exportCsv}>
            <span className="material-symbols-outlined text-[18px]">download</span> Export CSV
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {loading && !data && <LoadingState label="Đang tải audit logs..." />}
        {error && !data && <ErrorState message={error} onRetry={refetch} hint={MISSING_HINT} />}

        {data && (data.items.length === 0 ? (
          <EmptyState icon="history" title="Chưa có nhật ký" description={data.total === 0 ? MISSING_HINT : "Thử đổi bộ lọc."} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                    <th className="py-2 pr-3 font-medium">Thời gian</th>
                    <th className="py-2 pr-3 font-medium">Người thực hiện</th>
                    <th className="py-2 pr-3 font-medium">Hành động</th>
                    <th className="py-2 pr-3 font-medium">Target</th>
                    <th className="py-2 pr-3 font-medium hidden lg:table-cell">IP</th>
                    <th className="py-2 font-medium hidden xl:table-cell">Thay đổi</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((l) => (
                    <tr key={l.id} className="border-b border-outline-variant/60 hover:bg-surface-container-low align-top">
                      <td className="py-2 pr-3 text-on-surface-variant whitespace-nowrap text-xs">{fmt(l.timestamp)}</td>
                      <td className="py-2 pr-3 text-on-surface">{l.actor_name ?? l.actor_id.slice(0, 8)}</td>
                      <td className="py-2 pr-3"><code className="text-xs bg-surface-container px-1.5 py-0.5 rounded">{l.action}</code></td>
                      <td className="py-2 pr-3 text-on-surface-variant text-xs">{l.target ?? "—"}</td>
                      <td className="py-2 pr-3 text-on-surface-variant hidden lg:table-cell text-xs">{l.ip ?? "—"}</td>
                      <td className="py-2 hidden xl:table-cell max-w-[260px]">
                        {(l.before || l.after) ? (
                          <details>
                            <summary className="text-xs text-primary cursor-pointer">xem</summary>
                            <pre className="text-[10px] text-on-surface-variant whitespace-pre-wrap break-all mt-1">
                              {JSON.stringify({ before: l.before, after: l.after }, null, 2)}
                            </pre>
                          </details>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between mt-3 text-sm">
              <span className="text-xs text-on-surface-variant">{data.total.toLocaleString("vi-VN")} bản ghi · trang {data.page}/{totalPages}</span>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={data.page <= 1} onClick={() => setFilters({ page: data.page - 1 })}>Trước</Button>
                <Button size="sm" variant="outline" disabled={data.page >= totalPages} onClick={() => setFilters({ page: data.page + 1 })}>Sau</Button>
              </div>
            </div>
          </>
        ))}
      </CardContent>
    </Card>
  );
}
