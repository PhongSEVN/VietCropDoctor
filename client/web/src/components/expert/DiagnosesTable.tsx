import { IrrelevantBadge, StatusBadge } from "./badges";
import { getCropName, getDiseaseName } from "@/lib/api";
import type { DiagnosisItem } from "@/types/expert";

interface Props {
  items: DiagnosisItem[];
  /** Chat id currently being promoted (shows a spinner on that row). */
  busyId?: string | null;
  onSelect: (item: DiagnosisItem) => void;
}

function formatTime(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

function Thumb({ url }: { url?: string | null }) {
  if (!url) {
    return (
      <div className="h-12 w-12 rounded-md bg-surface-container flex items-center justify-center text-on-surface-variant">
        <span className="material-symbols-outlined text-[20px]">image</span>
      </div>
    );
  }
  return (
    <img
      src={url}
      alt="Ảnh cây trồng"
      loading="lazy"
      className="h-12 w-12 rounded-md object-cover border border-outline-variant"
    />
  );
}

/** "Chưa có phản hồi" badge for diagnoses with no feedback/case row yet. */
function NewBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-600">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      Chưa phản hồi
    </span>
  );
}

export function DiagnosesTable({ items, busyId, onSelect }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
            <th className="py-2 pr-3 font-medium">Ảnh</th>
            <th className="py-2 pr-3 font-medium">Người gửi</th>
            <th className="py-2 pr-3 font-medium">Loại cây</th>
            <th className="py-2 pr-3 font-medium">AI chẩn đoán</th>
            <th className="py-2 pr-3 font-medium">Tình trạng</th>
            <th className="py-2 font-medium whitespace-nowrap">Thời gian</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const disease = it.disease || "";
            const crop = getCropName(disease);
            const isBusy = busyId === it.chat_id;
            return (
              <tr
                key={it.chat_id}
                onClick={() => !isBusy && onSelect(it)}
                className={`border-b border-outline-variant/60 transition-colors ${
                  isBusy ? "opacity-60 cursor-wait" : "hover:bg-surface-container-low cursor-pointer"
                }`}
              >
                <td className="py-2 pr-3"><Thumb url={it.image_url} /></td>
                <td className="py-2 pr-3 font-medium text-on-surface whitespace-nowrap">
                  {it.user_name || it.user_id.slice(0, 8)}
                </td>
                <td className="py-2 pr-3 text-on-surface-variant whitespace-nowrap">{crop || "—"}</td>
                <td className="py-2 pr-3 max-w-[200px] truncate" title={getDiseaseName(disease)}>
                  {disease ? getDiseaseName(disease) : "—"}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex flex-col gap-1">
                    {it.status === "new" ? <NewBadge /> : <StatusBadge status={it.status} />}
                    {it.is_irrelevant && <IrrelevantBadge />}
                    {isBusy && (
                      <span className="text-[11px] text-on-surface-variant">Đang mở…</span>
                    )}
                  </div>
                </td>
                <td className="py-2 text-on-surface-variant whitespace-nowrap text-xs">
                  {formatTime(it.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
