import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ROLE_LABELS, createUser, logAudit, updateUser } from "@/lib/admin-api";
import type { AdminUser, BackendRole, CreateUserDto, UpdateUserDto } from "@/types/admin";

interface Props {
  /** When provided, the modal edits this user; otherwise it creates a new one. */
  user?: AdminUser | null;
  onClose: () => void;
  onSaved: () => void;
}

const ROLES: BackendRole[] = ["farmer", "agronomist", "admin"];
const INPUT =
  "h-9 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40";

export function UserFormModal({ user, onClose, onSaved }: Props) {
  const isEdit = !!user;
  const [username, setUsername] = useState(user?.username ?? "");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [role, setRole] = useState<BackendRole>(user?.role ?? "farmer");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isEdit && (!username.trim() || password.length < 8)) {
      setError("Tên đăng nhập bắt buộc và mật khẩu tối thiểu 8 ký tự.");
      return;
    }

    setSubmitting(true);
    try {
      if (isEdit && user) {
        const dto: UpdateUserDto = {
          full_name: fullName || null,
          email: email || null,
          phone: phone || null,
          role,
        };
        await updateUser(user.id, dto);
        await logAudit("user.update", user.id, user, dto);
      } else {
        const dto: CreateUserDto = {
          username: username.trim(),
          password,
          full_name: fullName || null,
          email: email || null,
          phone: phone || null,
          role,
        };
        const created = await createUser(dto);
        await logAudit("user.create", created.id, null, { ...dto, password: "***" });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu người dùng thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-2 sm:p-6 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? "Chỉnh sửa người dùng" : "Tạo người dùng"}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="bg-surface w-full max-w-md rounded-xl shadow-2xl my-4"
      >
        <header className="flex items-center justify-between border-b border-outline-variant px-5 py-3">
          <h2 className="text-lg font-semibold text-on-surface">
            {isEdit ? "Chỉnh sửa người dùng" : "Tạo người dùng mới"}
          </h2>
          <button type="button" onClick={onClose} className="text-on-surface-variant hover:bg-surface-container-high rounded-full p-1.5">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="p-5 space-y-3">
          {!isEdit && (
            <>
              <div>
                <label className="text-xs text-on-surface-variant">Tên đăng nhập *</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} className={INPUT} />
              </div>
              <div>
                <label className="text-xs text-on-surface-variant">Mật khẩu * (≥ 8 ký tự)</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT} />
              </div>
            </>
          )}
          <div>
            <label className="text-xs text-on-surface-variant">Họ tên</label>
            <input value={fullName ?? ""} onChange={(e) => setFullName(e.target.value)} className={INPUT} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-on-surface-variant">Email</label>
              <input type="email" value={email ?? ""} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className="text-xs text-on-surface-variant">Số điện thoại</label>
              <input value={phone ?? ""} onChange={(e) => setPhone(e.target.value)} className={INPUT} />
            </div>
          </div>
          <div>
            <label className="text-xs text-on-surface-variant">Vai trò</label>
            <select value={role} onChange={(e) => setRole(e.target.value as BackendRole)} className={INPUT}>
              {ROLES.map((r) => (
                <option key={r} value={r}>{ROLE_LABELS[r]}</option>
              ))}
            </select>
          </div>

          {error && <p className="text-xs text-error">{error}</p>}
        </div>

        <footer className="flex justify-end gap-2 border-t border-outline-variant px-5 py-3">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>Hủy</Button>
          <Button type="submit" size="sm" disabled={submitting}>
            {submitting ? "Đang lưu..." : isEdit ? "Lưu thay đổi" : "Tạo user"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
