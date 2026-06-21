import { useState } from "react";

import { RoleBadge, UserStatusBadge } from "./badges";
import { UserFormModal } from "./UserFormModal";
import { EmptyState, ErrorState, LoadingState } from "@/components/expert/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useUsers } from "@/hooks/useAdmin";
import {
  ROLE_LABELS,
  changeUserRole,
  downloadCsv,
  lockUser,
  logAudit,
  restoreUser,
  softDeleteUser,
  unlockUser,
} from "@/lib/admin-api";
import type { AdminUser, BackendRole, UserSort, UserStatus } from "@/types/admin";

const MISSING_HINT =
  "Endpoint /admin/users chưa được backend cài đặt (xem TODO trong lib/admin-api.ts).";

const ROLES: BackendRole[] = ["farmer", "agronomist", "admin"];
const STATUSES: UserStatus[] = ["active", "locked", "deleted"];
const SELECT =
  "h-9 rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40";

function Avatar({ user }: { user: AdminUser }) {
  if (user.avatar_url) {
    return <img src={user.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />;
  }
  const initial = (user.full_name || user.username || "?").charAt(0).toUpperCase();
  return (
    <div className="h-8 w-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center text-xs font-semibold">
      {initial}
    </div>
  );
}

function fmtTime(iso?: string | null): string {
  return iso ? iso.slice(0, 16).replace("T", " ") : "—";
}

export function UserManagement() {
  const { data, loading, error, filters, setFilters, refetch } = useUsers();
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function runAction(id: string, fn: () => Promise<unknown>, action: string, before?: unknown) {
    setBusyId(id);
    try {
      await fn();
      await logAudit(action, id, before);
      refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Thao tác thất bại");
    } finally {
      setBusyId(null);
    }
  }

  function handleRoleChange(u: AdminUser, role: BackendRole) {
    if (role === u.role) return;
    runAction(u.id, () => changeUserRole(u.id, role), "user.role_change", { from: u.role, to: role });
  }

  function exportCsv() {
    const rows = (data?.items ?? []).map((u) => ({
      id: u.id,
      username: u.username,
      full_name: u.full_name ?? "",
      email: u.email ?? "",
      phone: u.phone ?? "",
      role: ROLE_LABELS[u.role],
      status: u.status,
      created_at: u.created_at,
      last_login_at: u.last_login_at ?? "",
    }));
    downloadCsv("users.csv", rows);
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Card className="border-outline-variant bg-surface-container-lowest">
      <CardHeader className="pb-3 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">search</span>
            <input
              type="search"
              value={filters.search}
              onChange={(e) => setFilters({ search: e.target.value })}
              placeholder="Tìm theo tên, email, SĐT..."
              className="h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest pl-8 pr-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <select aria-label="Lọc vai trò" value={filters.role} onChange={(e) => setFilters({ role: e.target.value as BackendRole | "all" })} className={SELECT}>
            <option value="all">Tất cả vai trò</option>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
          <select aria-label="Lọc trạng thái" value={filters.status} onChange={(e) => setFilters({ status: e.target.value as UserStatus | "all" })} className={SELECT}>
            <option value="all">Tất cả trạng thái</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select aria-label="Sắp xếp" value={filters.sort} onChange={(e) => setFilters({ sort: e.target.value as UserSort })} className={SELECT}>
            <option value="newest">Mới nhất</option>
            <option value="oldest">Cũ nhất</option>
            <option value="name">Tên A→Z</option>
            <option value="last_login">Đăng nhập gần đây</option>
          </select>
          <Button size="sm" variant="outline" onClick={exportCsv}>
            <span className="material-symbols-outlined text-[18px]">download</span> CSV
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>
            <span className="material-symbols-outlined text-[18px]">add</span> Tạo user
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {loading && !data && <LoadingState label="Đang tải người dùng..." />}
        {error && !data && <ErrorState message={error} onRetry={refetch} hint={MISSING_HINT} />}

        {data && (data.items.length === 0 ? (
          <EmptyState icon="group_off" title="Không có người dùng" description={data.total === 0 ? MISSING_HINT : "Thử đổi bộ lọc."} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant">
                    <th className="py-2 pr-3 font-medium">Người dùng</th>
                    <th className="py-2 pr-3 font-medium hidden md:table-cell">Email</th>
                    <th className="py-2 pr-3 font-medium hidden lg:table-cell">SĐT</th>
                    <th className="py-2 pr-3 font-medium">Vai trò</th>
                    <th className="py-2 pr-3 font-medium">Trạng thái</th>
                    <th className="py-2 pr-3 font-medium hidden lg:table-cell">Tạo lúc</th>
                    <th className="py-2 pr-3 font-medium hidden xl:table-cell">Đăng nhập cuối</th>
                    <th className="py-2 font-medium text-right">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((u) => {
                    const busy = busyId === u.id;
                    return (
                      <tr key={u.id} className="border-b border-outline-variant/60 hover:bg-surface-container-low">
                        <td className="py-2 pr-3">
                          <div className="flex items-center gap-2">
                            <Avatar user={u} />
                            <div className="min-w-0">
                              <p className="font-medium text-on-surface truncate">{u.full_name || u.username}</p>
                              <p className="text-xs text-on-surface-variant truncate">@{u.username}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-on-surface-variant hidden md:table-cell truncate max-w-[180px]">{u.email || "—"}</td>
                        <td className="py-2 pr-3 text-on-surface-variant hidden lg:table-cell">{u.phone || "—"}</td>
                        <td className="py-2 pr-3">
                          <select
                            aria-label="Đổi vai trò"
                            value={u.role}
                            disabled={busy || u.status === "deleted"}
                            onChange={(e) => handleRoleChange(u, e.target.value as BackendRole)}
                            className="rounded-md border border-outline-variant bg-surface-container-lowest px-1.5 py-0.5 text-xs text-on-surface"
                          >
                            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                          </select>
                        </td>
                        <td className="py-2 pr-3"><UserStatusBadge status={u.status} /></td>
                        <td className="py-2 pr-3 text-on-surface-variant hidden lg:table-cell text-xs whitespace-nowrap">{fmtTime(u.created_at)}</td>
                        <td className="py-2 pr-3 text-on-surface-variant hidden xl:table-cell text-xs whitespace-nowrap">{fmtTime(u.last_login_at)}</td>
                        <td className="py-2">
                          <div className="flex items-center justify-end gap-1">
                            <IconBtn icon="edit" title="Sửa" disabled={busy} onClick={() => setEditing(u)} />
                            {u.status === "active" && (
                              <IconBtn icon="lock" title="Khóa" disabled={busy}
                                onClick={() => runAction(u.id, () => lockUser(u.id), "user.lock")} />
                            )}
                            {u.status === "locked" && (
                              <IconBtn icon="lock_open" title="Mở khóa" disabled={busy}
                                onClick={() => runAction(u.id, () => unlockUser(u.id), "user.unlock")} />
                            )}
                            {u.status !== "deleted" ? (
                              <IconBtn icon="delete" title="Xóa (mềm)" danger disabled={busy}
                                onClick={() => runAction(u.id, () => softDeleteUser(u.id), "user.soft_delete")} />
                            ) : (
                              <IconBtn icon="restore_from_trash" title="Khôi phục" disabled={busy}
                                onClick={() => runAction(u.id, () => restoreUser(u.id), "user.restore")} />
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-3 text-sm">
              <span className="text-xs text-on-surface-variant">
                {data.total.toLocaleString("vi-VN")} người dùng · trang {data.page}/{totalPages}
              </span>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={data.page <= 1} onClick={() => setFilters({ page: data.page - 1 })}>
                  Trước
                </Button>
                <Button size="sm" variant="outline" disabled={data.page >= totalPages} onClick={() => setFilters({ page: data.page + 1 })}>
                  Sau
                </Button>
              </div>
            </div>
          </>
        ))}
      </CardContent>

      {creating && <UserFormModal onClose={() => setCreating(false)} onSaved={refetch} />}
      {editing && <UserFormModal user={editing} onClose={() => setEditing(null)} onSaved={refetch} />}
    </Card>
  );
}

function IconBtn({ icon, title, onClick, disabled, danger }: {
  icon: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md p-1.5 transition-colors disabled:opacity-40 ${
        danger ? "text-error hover:bg-error-container/40" : "text-on-surface-variant hover:bg-surface-container-high"
      }`}
    >
      <span className="material-symbols-outlined text-[18px]">{icon}</span>
    </button>
  );
}
