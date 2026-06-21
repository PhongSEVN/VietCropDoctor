import type { CasePriority, ExpertCaseStatus } from "@/types/expert";

const STATUS_META: Record<ExpertCaseStatus, { label: string; className: string; dot: string }> = {
  pending:     { label: "Chưa xử lý", className: "bg-amber-100 text-amber-800",   dot: "bg-amber-500" },
  in_progress: { label: "Đang xử lý", className: "bg-blue-100 text-blue-800",     dot: "bg-blue-500" },
  answered:    { label: "Đã phản hồi", className: "bg-green-100 text-green-800",   dot: "bg-green-500" },
};

const PRIORITY_META: Record<CasePriority, { label: string; className: string }> = {
  urgent: { label: "Khẩn cấp",     className: "bg-red-100 text-red-800" },
  high:   { label: "Cao",          className: "bg-orange-100 text-orange-800" },
  normal: { label: "Bình thường",  className: "bg-gray-100 text-gray-700" },
  low:    { label: "Thấp",         className: "bg-slate-100 text-slate-600" },
};

export const STATUS_OPTIONS: { value: ExpertCaseStatus; label: string }[] = (
  Object.keys(STATUS_META) as ExpertCaseStatus[]
).map((value) => ({ value, label: STATUS_META[value].label }));

export function StatusBadge({ status }: { status: ExpertCaseStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: CasePriority }) {
  const meta = PRIORITY_META[priority];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${meta.className}`}>
      {meta.label}
    </span>
  );
}

export function statusLabel(status: ExpertCaseStatus): string {
  return STATUS_META[status].label;
}

export function IrrelevantBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-rose-100 text-rose-700">
      <span className="material-symbols-outlined text-[14px]">block</span>
      Ảnh không liên quan
    </span>
  );
}
