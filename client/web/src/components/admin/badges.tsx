import { ROLE_LABELS } from "@/lib/admin-api";
import type { BackendRole, UserStatus } from "@/types/admin";

const ROLE_CLASS: Record<BackendRole, string> = {
  farmer: "bg-slate-100 text-slate-700",
  agronomist: "bg-emerald-100 text-emerald-800",
  admin: "bg-violet-100 text-violet-800",
};

const STATUS_META: Record<UserStatus, { label: string; className: string; dot: string }> = {
  active:  { label: "Hoạt động", className: "bg-green-100 text-green-800", dot: "bg-green-500" },
  locked:  { label: "Đã khóa",   className: "bg-amber-100 text-amber-800", dot: "bg-amber-500" },
  deleted: { label: "Đã xóa",    className: "bg-red-100 text-red-800",     dot: "bg-red-400" },
};

export function RoleBadge({ role }: { role: BackendRole }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${ROLE_CLASS[role]}`}>
      {ROLE_LABELS[role]}
    </span>
  );
}

export function UserStatusBadge({ status }: { status: UserStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
