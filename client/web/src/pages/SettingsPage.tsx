import { useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import MainLayout from "@/components/MainLayout";
import { updateProfile, uploadAvatar } from "@/lib/api";
import { useProfile } from "@/lib/profile-context";

const NOTIF_KEY = "vcd_notif_settings";

function loadNotifSettings() {
  try {
    const stored = localStorage.getItem(NOTIF_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* empty */ }
  return { diagnosis: true, alert: true };
}

export default function SettingsPage() {
  const { user } = useAuth();
  const { profile, setProfile } = useProfile();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [notif, setNotif] = useState(loadNotifSettings);

  const [editing, setEditing] = useState(false);
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [avatarUploading, setAvatarUploading] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  const userName = user?.username ?? profile?.username ?? "—";

  function startEdit() {
    setEditEmail(profile?.email ?? "");
    setEditPhone(profile?.phone ?? "");
    setSaveMsg(null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setSaveMsg(null);
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarUploading(true);
    setSaveMsg(null);
    try {
      const updated = await uploadAvatar(file);
      setProfile(updated);
      setSaveMsg({ ok: true, text: "Cập nhật ảnh đại diện thành công!" });
      setTimeout(() => setSaveMsg(null), 3000);
    } catch (err) {
      setSaveMsg({ ok: false, text: err instanceof Error ? err.message : "Upload thất bại" });
    } finally {
      setAvatarUploading(false);
      if (avatarInputRef.current) avatarInputRef.current.value = "";
    }
  }

  async function saveEdit() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await updateProfile({
        email: editEmail.trim() || undefined,
        phone: editPhone.trim() || undefined,
      });
      setProfile(updated);
      setEditing(false);
      setSaveMsg({ ok: true, text: "Cập nhật thành công!" });
      setTimeout(() => setSaveMsg(null), 3000);
    } catch (err) {
      setSaveMsg({ ok: false, text: err instanceof Error ? err.message : "Cập nhật thất bại" });
    } finally {
      setSaving(false);
    }
  }

  function toggleNotif(key: "diagnosis" | "alert") {
    setNotif((prev: typeof notif) => {
      const next = { ...prev, [key]: !prev[key] };
      localStorage.setItem(NOTIF_KEY, JSON.stringify(next));
      return next;
    });
  }

  return (
    <MainLayout>
      <div className="p-4 md:p-8 max-w-4xl mx-auto pb-24">
        <h1 className="text-3xl font-semibold text-on-surface mb-6 hidden md:block">Cài đặt chung</h1>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Thông tin cá nhân */}
            <section className="bg-surface rounded-xl border border-outline-variant p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-on-surface flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">person</span>
                  Thông tin cá nhân
                </h2>
                {!editing && (
                  <button
                    onClick={startEdit}
                    className="flex items-center gap-1 text-sm font-semibold text-primary hover:opacity-70 transition-opacity"
                  >
                    <span className="material-symbols-outlined text-[18px]">edit</span>
                    Chỉnh sửa
                  </button>
                )}
              </div>

              {saveMsg && (
                <div className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 ${saveMsg.ok ? "bg-[#dcfce3] text-[#166534]" : "bg-error-container text-on-error-container"}`}>
                  <span className="material-symbols-outlined text-[18px]">{saveMsg.ok ? "check_circle" : "error"}</span>
                  {saveMsg.text}
                </div>
              )}

              <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 mb-6">
                <div className="relative group">
                  <button
                    type="button"
                    onClick={() => avatarInputRef.current?.click()}
                    disabled={avatarUploading}
                    className="w-24 h-24 rounded-full bg-primary flex items-center justify-center text-on-primary text-3xl font-bold border-4 border-surface shadow-md overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                    title="Đổi ảnh đại diện"
                  >
                    {profile?.avatar_url ? (
                      <img src={profile.avatar_url} alt="avatar" className="w-full h-full object-cover" />
                    ) : (
                      userName[0]?.toUpperCase()
                    )}
                  </button>
                  <div
                    onClick={() => avatarInputRef.current?.click()}
                    className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  >
                    {avatarUploading ? (
                      <span className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <span className="material-symbols-outlined text-white text-[28px]">photo_camera</span>
                    )}
                  </div>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                </div>
                <div className="flex-1 w-full">
                  <div className="grid gap-4">
                    <div>
                      <label className="block text-sm font-medium text-on-surface-variant mb-1">Tên người dùng</label>
                      <div className="flex items-center justify-between border-b border-outline-variant py-2">
                        <span className="text-base text-on-surface">{userName}</span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-on-surface-variant mb-1">Vai trò</label>
                      <div className="flex items-center justify-between border-b border-outline-variant py-2">
                        <span className="text-base text-on-surface capitalize">
                          {user?.role === "admin" ? "Quản trị viên" : user?.role === "agronomist" ? "Kỹ sư nông nghiệp" : "Nông dân"}
                        </span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-on-surface-variant mb-1">Email</label>
                      {editing ? (
                        <input
                          type="email"
                          value={editEmail}
                          onChange={(e) => setEditEmail(e.target.value)}
                          placeholder="email@example.com"
                          className="w-full mt-1 px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-base text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                        />
                      ) : (
                        <div className="flex items-center justify-between border-b border-outline-variant py-2">
                          <span className="text-base text-on-surface">
                            {profile?.email ?? <span className="text-on-surface-variant text-sm">—</span>}
                          </span>
                        </div>
                      )}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-on-surface-variant mb-1">Số điện thoại</label>
                      {editing ? (
                        <input
                          type="tel"
                          value={editPhone}
                          onChange={(e) => setEditPhone(e.target.value)}
                          placeholder="0901234567"
                          className="w-full mt-1 px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-base text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                        />
                      ) : (
                        <div className="flex items-center justify-between border-b border-outline-variant py-2">
                          <span className="text-base text-on-surface">
                            {profile?.phone ?? <span className="text-on-surface-variant text-sm">—</span>}
                          </span>
                        </div>
                      )}
                    </div>
                    {editing && (
                      <div className="flex gap-3 pt-2">
                        <button
                          onClick={saveEdit}
                          disabled={saving}
                          className="flex-1 bg-primary text-on-primary py-2 rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
                        >
                          {saving ? (
                            <span className="w-4 h-4 border-2 border-on-primary border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <span className="material-symbols-outlined text-[18px]">save</span>
                          )}
                          {saving ? "Đang lưu..." : "Lưu thay đổi"}
                        </button>
                        <button
                          onClick={cancelEdit}
                          disabled={saving}
                          className="px-4 py-2 rounded-lg border border-outline-variant text-sm font-semibold text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-50"
                        >
                          Hủy
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </section>

            {/* Cấu hình ứng dụng */}
            <section className="bg-surface rounded-xl border border-outline-variant p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-on-surface mb-6 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">tune</span>
                Cấu hình ứng dụng
              </h2>
              <div className="grid gap-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-medium text-on-surface">Ngôn ngữ</h3>
                    <p className="text-sm text-on-surface-variant">Chọn ngôn ngữ hiển thị</p>
                  </div>
                  <select className="bg-surface-container-low border border-outline-variant rounded-md py-2 px-3 text-base text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none">
                    <option value="vi">Tiếng Việt</option>
                    <option value="en">English</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-medium text-on-surface">Chế độ giao diện</h3>
                    <p className="text-sm text-on-surface-variant">Sáng hoặc Tối</p>
                  </div>
                  <div className="flex bg-surface-container-low rounded-lg p-1 border border-outline-variant">
                    <button onClick={() => setTheme("light")}
                      className={`px-3 py-1 rounded-md text-xs font-semibold flex items-center gap-1 transition-colors ${
                        theme === "light" ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-container-high"
                      }`}>
                      <span className="material-symbols-outlined text-[16px]">light_mode</span>Sáng
                    </button>
                    <button onClick={() => setTheme("dark")}
                      className={`px-3 py-1 rounded-md text-xs font-semibold flex items-center gap-1 transition-colors ${
                        theme === "dark" ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-container-high"
                      }`}>
                      <span className="material-symbols-outlined text-[16px]">dark_mode</span>Tối
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Right Column */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            {/* Thông báo */}
            <section className="bg-surface rounded-xl border border-outline-variant p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-on-surface mb-6 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">notifications_active</span>
                Thông báo
              </h2>
              <div className="grid gap-4">
                <label className="flex items-start justify-between cursor-pointer group">
                  <div className="pr-4">
                    <span className="block text-base font-medium text-on-surface group-hover:text-primary transition-colors">Chẩn đoán mới</span>
                    <span className="block text-sm text-on-surface-variant">Thông báo khi có kết quả chẩn đoán từ AI</span>
                  </div>
                  <div className="relative mt-1 shrink-0">
                    <input type="checkbox" className="sr-only peer" checked={notif.diagnosis} onChange={() => toggleNotif("diagnosis")} />
                    <div className="w-11 h-6 bg-surface-container-high rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary" />
                  </div>
                </label>
                <hr className="border-outline-variant opacity-50" />
                <label className="flex items-start justify-between cursor-pointer group">
                  <div className="pr-4">
                    <span className="block text-base font-medium text-on-surface group-hover:text-primary transition-colors">Cảnh báo dịch bệnh</span>
                    <span className="block text-sm text-on-surface-variant">Cập nhật tình hình sâu bệnh tại khu vực</span>
                  </div>
                  <div className="relative mt-1 shrink-0">
                    <input type="checkbox" className="sr-only peer" checked={notif.alert} onChange={() => toggleNotif("alert")} />
                    <div className="w-11 h-6 bg-surface-container-high rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary" />
                  </div>
                </label>
              </div>
            </section>

            {/* Bảo mật */}
            <section className="bg-surface rounded-xl border border-outline-variant p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-on-surface mb-6 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">security</span>
                Bảo mật
              </h2>
              <button className="w-full flex items-center justify-between p-3 rounded-lg border border-outline-variant hover:bg-surface-container-low transition-colors group">
                <div className="flex items-center gap-3 text-on-surface">
                  <span className="material-symbols-outlined text-on-surface-variant">password</span>
                  <span className="text-base font-medium">Đổi mật khẩu</span>
                </div>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">chevron_right</span>
              </button>
            </section>

            {/* Thông tin */}
            <section className="bg-surface rounded-xl border border-outline-variant p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-on-surface mb-6 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">info</span>
                Thông tin
              </h2>
              <div className="grid gap-2">
                <div className="flex justify-between items-center py-2">
                  <span className="text-base text-on-surface">Phiên bản</span>
                  <span className="text-base text-on-surface-variant">{import.meta.env.VITE_APP_VERSION ?? "1.0.0"}</span>
                </div>
                <a href="#" className="flex justify-between items-center py-2 text-on-surface hover:text-primary transition-colors group">
                  <span className="text-base">Điều khoản sử dụng</span>
                  <span className="material-symbols-outlined text-[18px] text-on-surface-variant group-hover:text-primary">open_in_new</span>
                </a>
                <a href="#" className="flex justify-between items-center py-2 text-on-surface hover:text-primary transition-colors group">
                  <span className="text-base">Chính sách bảo mật</span>
                  <span className="material-symbols-outlined text-[18px] text-on-surface-variant group-hover:text-primary">open_in_new</span>
                </a>
              </div>
            </section>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
