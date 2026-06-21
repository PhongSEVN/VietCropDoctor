import { useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useExperts } from "@/hooks/useAdmin";
import { assignExpert, logAudit, removeExpert } from "@/lib/admin-api";
import type { ExpertProfile } from "@/types/admin";

const CROPS = ["Lúa", "Cà phê", "Hồ tiêu", "Sầu riêng", "Thanh long"];
const REGIONS = ["ĐBSCL", "Tây Nguyên", "Đông Nam Bộ", "Bắc Trung Bộ", "ĐB sông Hồng"];
const EMPTY_HINT =
  "Chưa có tài khoản role chuyên gia. Đổi vai trò một user thành 'agronomist' (tab Người dùng) để hiển thị ở đây.";

export function ExpertManagement() {
  const { data, loading, error, refetch } = useExperts();
  const [assigning, setAssigning] = useState<ExpertProfile | null>(null);

  async function handleRemove(ex: ExpertProfile) {
    if (!confirm(`Gỡ chuyên gia "${ex.name}"?`)) return;
    try {
      await removeExpert(ex.id);
      await logAudit("expert.remove", ex.id);
      refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Gỡ chuyên gia thất bại");
    }
  }

  if (loading && !data) return <LoadingState label="Đang tải chuyên gia..." />;
  if (error && !data) return <ErrorState message={error} onRetry={refetch} />;

  const experts = data ?? [];

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-on-surface">Quản lý chuyên gia</CardTitle>
      </CardHeader>
      <CardContent>
        {experts.length === 0 ? (
          <EmptyState icon="agriculture" title="Chưa có chuyên gia" description={EMPTY_HINT} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                  <th className="py-2 pr-3 font-medium">Chuyên gia</th>
                  <th className="py-2 pr-3 font-medium">Số ca</th>
                  <th className="py-2 pr-3 font-medium">Hoàn thành</th>
                  <th className="py-2 pr-3 font-medium">TG phản hồi</th>
                  <th className="py-2 pr-3 font-medium">Đánh giá</th>
                  <th className="py-2 pr-3 font-medium hidden lg:table-cell">Lĩnh vực</th>
                  <th className="py-2 font-medium text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {experts.map((ex) => (
                  <tr key={ex.id} className="border-b border-outline-variant/60 hover:bg-surface-container-low">
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-2">
                        <span className={`h-2.5 w-2.5 rounded-full ${ex.online ? "bg-green-500" : "bg-gray-300"}`} />
                        <span className="font-medium text-on-surface">{ex.name}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-3 text-on-surface-variant">{ex.handled_cases}</td>
                    <td className="py-2 pr-3 text-on-surface-variant">{(ex.completion_rate * 100).toFixed(0)}%</td>
                    <td className="py-2 pr-3 text-on-surface-variant">{ex.avg_response_minutes === null ? "—" : `${ex.avg_response_minutes}p`}</td>
                    <td className="py-2 pr-3 text-on-surface-variant">{ex.rating === null ? "—" : `★ ${ex.rating.toFixed(1)}`}</td>
                    <td className="py-2 pr-3 hidden lg:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {ex.crops.length === 0 ? <span className="text-xs text-on-surface-variant">—</span> :
                          ex.crops.map((c) => <span key={c} className="rounded-full bg-surface-container px-1.5 py-0.5 text-[10px]">{c}</span>)}
                      </div>
                    </td>
                    <td className="py-2">
                      <div className="flex justify-end gap-1">
                        <button title="Gán lĩnh vực" onClick={() => setAssigning(ex)} className="rounded-md p-1.5 text-on-surface-variant hover:bg-surface-container-high">
                          <span className="material-symbols-outlined text-[18px]">tune</span>
                        </button>
                        <button title="Gỡ chuyên gia" onClick={() => handleRemove(ex)} className="rounded-md p-1.5 text-error hover:bg-error-container/40">
                          <span className="material-symbols-outlined text-[18px]">person_remove</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {assigning && (
        <AssignModal
          expert={assigning}
          onClose={() => setAssigning(null)}
          onSaved={() => { setAssigning(null); refetch(); }}
        />
      )}
    </Card>
  );
}

function AssignModal({ expert, onClose, onSaved }: { expert: ExpertProfile; onClose: () => void; onSaved: () => void }) {
  const [crops, setCrops] = useState<string[]>(expert.crops);
  const [regions, setRegions] = useState<string[]>(expert.regions);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (list: string[], setList: (v: string[]) => void, value: string) =>
    setList(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

  async function save() {
    setSubmitting(true);
    setError(null);
    try {
      await assignExpert(expert.id, crops, regions);
      await logAudit("expert.assign", expert.id, { crops: expert.crops, regions: expert.regions }, { crops, regions });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gán thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" onClick={onClose} role="dialog" aria-modal="true">
      <div className="bg-surface w-full max-w-md rounded-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-outline-variant px-5 py-3">
          <h2 className="text-base font-semibold text-on-surface">Gán lĩnh vực — {expert.name}</h2>
          <button onClick={onClose} className="text-on-surface-variant hover:bg-surface-container-high rounded-full p-1.5">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>
        <div className="p-5 space-y-4">
          <Group title="Loại cây trồng" options={CROPS} selected={crops} onToggle={(v) => toggle(crops, setCrops, v)} />
          <Group title="Khu vực địa lý" options={REGIONS} selected={regions} onToggle={(v) => toggle(regions, setRegions, v)} />
          {error && <p className="text-xs text-error">{error}</p>}
        </div>
        <footer className="flex justify-end gap-2 border-t border-outline-variant px-5 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>Hủy</Button>
          <Button size="sm" onClick={save} disabled={submitting}>{submitting ? "Đang lưu..." : "Lưu"}</Button>
        </footer>
      </div>
    </div>
  );
}

function Group({ title, options, selected, onToggle }: { title: string; options: string[]; selected: string[]; onToggle: (v: string) => void }) {
  return (
    <div>
      <p className="text-xs text-on-surface-variant mb-1.5">{title}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => {
          const on = selected.includes(o);
          return (
            <button
              key={o}
              type="button"
              onClick={() => onToggle(o)}
              className={`rounded-full px-3 py-1 text-xs border transition-colors ${
                on ? "bg-primary-container text-on-primary-container border-transparent" : "border-outline-variant text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}
