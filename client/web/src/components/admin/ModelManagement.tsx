import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getModelRuns, logAudit, reloadServingModel, triggerRetrain } from "@/lib/admin-api";
import type { ModelRun } from "@/types/admin";

const MODELS = ["", "efficientnet_b0", "mobilenetv3", "resnet50", "vit", "yolo"];

function fmtPct(v?: number | null): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(2)}%`;
}
function fmtTime(ms?: number | null): string {
  return ms ? new Date(ms).toISOString().slice(0, 16).replace("T", " ") : "—";
}

export function ModelManagement() {
  const [runs, setRuns] = useState<ModelRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [model, setModel] = useState("");
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null);
  const [retrainErr, setRetrainErr] = useState<string | null>(null);
  const [retraining, setRetraining] = useState(false);

  const [reloadMsg, setReloadMsg] = useState<string | null>(null);
  const [reloadErr, setReloadErr] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getModelRuns()
      .then((d) => setRuns(d.runs))
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được MLflow runs"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleRetrain() {
    setRetraining(true);
    setRetrainMsg(null);
    setRetrainErr(null);
    try {
      const res = await triggerRetrain(model || undefined);
      await logAudit("model.retrain_trigger", undefined, null, { model: model || "all" });
      setRetrainMsg(`Đã kích hoạt retrain (DAG run: ${res.dag_run_id ?? "?"}, trạng thái: ${res.state ?? "queued"}).`);
    } catch (e) {
      setRetrainErr(e instanceof Error ? e.message : "Kích hoạt retrain thất bại");
    } finally {
      setRetraining(false);
    }
  }

  async function handleReload() {
    setReloading(true);
    setReloadMsg(null);
    setReloadErr(null);
    try {
      const res = await reloadServingModel();
      await logAudit("model.reload", undefined, null, res);
      setReloadMsg("Đã đồng bộ & nạp model mới vào vision-ai (hot-swap).");
      load();
    } catch (e) {
      setReloadErr(e instanceof Error ? e.message : "Hot-swap thất bại");
    } finally {
      setReloading(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="border-outline-variant bg-surface-container-lowest">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-on-surface">Kích hoạt huấn luyện lại</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="h-9 rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface"
              >
                <option value="">Tất cả 5 model</option>
                {MODELS.filter(Boolean).map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <Button size="sm" onClick={handleRetrain} disabled={retraining}>
                <span className="material-symbols-outlined text-[18px]">model_training</span>
                {retraining ? "Đang gửi..." : "Kích hoạt retrain"}
              </Button>
            </div>
            {retrainMsg && <p className="text-xs text-green-600">{retrainMsg}</p>}
            {retrainErr && <p className="text-xs text-error">{retrainErr}</p>}
            <p className="text-[11px] text-on-surface-variant">
              Gọi DAG <code>retrain_classifier</code> trên Airflow. Quá trình train chạy nền; theo dõi chi
              tiết tại Airflow (:8090). Cần GPU + dataset cho bước train.
            </p>
          </CardContent>
        </Card>

        <Card className="border-outline-variant bg-surface-container-lowest">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-on-surface">Triển khai model mới (hot-swap)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button size="sm" variant="outline" onClick={handleReload} disabled={reloading}>
              <span className="material-symbols-outlined text-[18px]">sync</span>
              {reloading ? "Đang nạp..." : "Đồng bộ & nạp model mới"}
            </Button>
            {reloadMsg && <p className="text-xs text-green-600">{reloadMsg}</p>}
            {reloadErr && <p className="text-xs text-error">{reloadErr}</p>}
            <p className="text-[11px] text-on-surface-variant">
              Kéo trọng số mới nhất từ MLflow vào vision-ai và nạp lại — không cần restart. Tự cập nhật
              trọng số ensemble = macro-F1.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* MLflow runs */}
      <Card className="border-outline-variant bg-surface-container-lowest">
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base text-on-surface">Hiệu năng model (MLflow)</CardTitle>
          <button onClick={load} className="rounded-full p-1.5 text-on-surface-variant hover:bg-surface-container-high" title="Làm mới">
            <span className="material-symbols-outlined text-[20px]">refresh</span>
          </button>
        </CardHeader>
        <CardContent>
          {loading && runs.length === 0 && <LoadingState label="Đang tải MLflow runs..." />}
          {error && runs.length === 0 && (
            <ErrorState message={error} onRetry={load} hint="Đảm bảo MLflow (:5000) đang chạy và đã có lần train nào." />
          )}
          {!error && !(loading && runs.length === 0) && (
            runs.length === 0 ? (
              <EmptyState icon="experiment" title="Chưa có run nào" description="Chạy train (train4.bat / DAG) để có dữ liệu." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                      <th className="py-2 pr-3 font-medium">Model</th>
                      <th className="py-2 pr-3 font-medium">Test macro-F1</th>
                      <th className="py-2 pr-3 font-medium">Test acc</th>
                      <th className="py-2 pr-3 font-medium">Val acc</th>
                      <th className="py-2 pr-3 font-medium hidden md:table-cell">Lần train gần nhất</th>
                      <th className="py-2 font-medium hidden lg:table-cell">Run ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.model} className="border-b border-outline-variant/60">
                        <td className="py-2 pr-3 font-medium text-on-surface">{r.model}</td>
                        <td className="py-2 pr-3 font-semibold text-primary">{fmtPct(r.test_macro_f1)}</td>
                        <td className="py-2 pr-3 text-on-surface-variant">{fmtPct(r.test_acc)}</td>
                        <td className="py-2 pr-3 text-on-surface-variant">{fmtPct(r.val_acc)}</td>
                        <td className="py-2 pr-3 text-on-surface-variant hidden md:table-cell text-xs whitespace-nowrap">{fmtTime(r.start_time)}</td>
                        <td className="py-2 text-on-surface-variant hidden lg:table-cell text-xs font-mono">{r.run_id?.slice(0, 8) ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </CardContent>
      </Card>
    </div>
  );
}
