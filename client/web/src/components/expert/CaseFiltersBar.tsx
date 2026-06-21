import { STATUS_OPTIONS } from "./badges";
import type { CaseSort, ExpertCaseFilters } from "@/types/expert";

interface Props {
  filters: ExpertCaseFilters;
  crops: string[];
  onChange: (patch: Partial<ExpertCaseFilters>) => void;
  resultCount: number;
}

const SELECT_CLASS =
  "h-9 rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40";

const SORT_OPTIONS: { value: CaseSort; label: string }[] = [
  { value: "newest", label: "Mới nhất" },
  { value: "oldest", label: "Cũ nhất" },
  { value: "priority", label: "Ưu tiên" },
];

export function CaseFiltersBar({ filters, crops, onChange, resultCount }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">
          search
        </span>
        <input
          type="search"
          value={filters.search}
          onChange={(e) => onChange({ search: e.target.value })}
          placeholder="Tìm theo người gửi, bệnh, mô tả..."
          className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest pl-8 pr-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>

      {/* Status */}
      <select
        aria-label="Lọc theo trạng thái"
        value={filters.status}
        onChange={(e) => onChange({ status: e.target.value as ExpertCaseFilters["status"] })}
        className={SELECT_CLASS}
      >
        <option value="all">Tất cả trạng thái</option>
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      {/* Crop */}
      <select
        aria-label="Lọc theo loại cây"
        value={filters.crop}
        onChange={(e) => onChange({ crop: e.target.value })}
        className={SELECT_CLASS}
      >
        <option value="all">Tất cả loại cây</option>
        {crops.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      {/* Sort */}
      <select
        aria-label="Sắp xếp"
        value={filters.sort}
        onChange={(e) => onChange({ sort: e.target.value as CaseSort })}
        className={SELECT_CLASS}
      >
        {SORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      <span className="text-xs text-on-surface-variant whitespace-nowrap ml-auto">
        {resultCount} ca
      </span>
    </div>
  );
}
