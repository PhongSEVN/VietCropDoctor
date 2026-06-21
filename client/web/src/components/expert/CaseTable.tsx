import { IrrelevantBadge, PriorityBadge, StatusBadge } from "./badges";
import { getCropName, getDiseaseName } from "@/lib/api";
import type { ExpertCase } from "@/types/expert";

interface Props {
  cases: ExpertCase[];
  onSelect: (id: string) => void;
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

export function CaseTable({ cases, onSelect }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
            <th className="py-2 pr-3 font-medium">Ảnh</th>
            <th className="py-2 pr-3 font-medium">Người gửi</th>
            <th className="py-2 pr-3 font-medium">Loại cây</th>
            <th className="py-2 pr-3 font-medium">AI chẩn đoán</th>
            <th className="py-2 pr-3 font-medium hidden md:table-cell">Mô tả</th>
            <th className="py-2 pr-3 font-medium">Trạng thái</th>
            <th className="py-2 pr-3 font-medium">Ưu tiên</th>
            <th className="py-2 font-medium whitespace-nowrap">Thời gian</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const crop = c.crop || getCropName(c.ai.predicted_disease);
            return (
              <tr
                key={c.id}
                onClick={() => onSelect(c.id)}
                className="border-b border-outline-variant/60 hover:bg-surface-container-low cursor-pointer transition-colors"
              >
                <td className="py-2 pr-3"><Thumb url={c.image_url} /></td>
                <td className="py-2 pr-3 font-medium text-on-surface whitespace-nowrap">
                  {c.user_name || c.user_id.slice(0, 8)}
                </td>
                <td className="py-2 pr-3 text-on-surface-variant whitespace-nowrap">{crop || "—"}</td>
                <td className="py-2 pr-3 max-w-[180px] truncate" title={getDiseaseName(c.ai.predicted_disease)}>
                  {getDiseaseName(c.ai.predicted_disease)}
                  <span className="text-on-surface-variant"> · {(c.ai.predicted_confidence * 100).toFixed(0)}%</span>
                </td>
                <td className="py-2 pr-3 max-w-[220px] truncate hidden md:table-cell text-on-surface-variant">
                  {c.problem_description || "—"}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex flex-col gap-1">
                    <StatusBadge status={c.status} />
                    {c.is_irrelevant && <IrrelevantBadge />}
                  </div>
                </td>
                <td className="py-2 pr-3"><PriorityBadge priority={c.priority} /></td>
                <td className="py-2 text-on-surface-variant whitespace-nowrap text-xs">
                  {formatTime(c.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
