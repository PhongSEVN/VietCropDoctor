import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/profile-context";
import PortalSwitcher from "@/components/PortalSwitcher";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { path: "/history", icon: "history", label: "Lịch sử chẩn đoán" },
  // { path: "/library", icon: "potted_plant", label: "Thư viện bệnh hại" },
  { path: "/settings", icon: "settings", label: "Cài đặt" },
];

const ROLE_LABELS: Record<string, string> = {
  farmer: "Nông dân",
  agronomist: "Chuyên gia nông nghiệp",
  admin: "Quản trị viên",
};

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation();
  const { user, logout } = useAuth();
  const { profile } = useProfile();

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + "/");

  const avatarLetter = user?.username?.[0]?.toUpperCase() ?? "U";
  const avatarUrl = profile?.avatar_url;
  const roleLabel = ROLE_LABELS[user?.role ?? ""] ?? "Người dùng";

  return (
    <nav
      className={`hidden md:flex flex-col h-screen fixed left-0 top-0 bg-surface-container-low border-r border-outline-variant z-40 transition-[width] duration-300 overflow-hidden ${
        collapsed ? "w-[72px]" : "w-[300px]"
      }`}
    >
      {/* Header */}
      <div className={`py-4 border-b border-outline-variant flex-shrink-0 ${collapsed ? "px-3" : "px-4"}`}>
        {/* Toggle + Title row */}
        <div className={`flex items-center mb-3 ${collapsed ? "justify-center" : "justify-between"}`}>
          {!collapsed && (
            <h1 className="text-2xl font-bold text-primary leading-tight">VietCropDoctor</h1>
          )}
          <button
            onClick={onToggle}
            className="p-2 rounded-full hover:bg-surface-container-high transition-colors text-on-surface-variant flex-shrink-0"
          >
            <span className="material-symbols-outlined text-[20px]">
              {collapsed ? "menu_open" : "menu"}
            </span>
          </button>
        </div>

        {/* User info */}
        {!collapsed && (
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold text-sm shadow-sm flex-shrink-0 overflow-hidden">
              {avatarUrl ? (
                <img src={avatarUrl} alt="avatar" className="w-full h-full object-cover" />
              ) : (
                avatarLetter
              )}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-on-surface truncate">
                {user?.username ?? "Người dùng"}
              </div>
              <div className="text-xs font-semibold tracking-wider text-on-surface-variant uppercase">
                {roleLabel}
              </div>
            </div>
          </div>
        )}

        {/* New chat CTA */}
        <Link
          to="/"
          className={`bg-primary text-on-primary rounded-full font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-opacity shadow-sm ${
            collapsed ? "justify-center p-2" : "py-2 px-4 w-full justify-center"
          }`}
          title={collapsed ? "Cuộc trò chuyện mới" : undefined}
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          {!collapsed && "Cuộc trò chuyện mới"}
        </Link>

        {/* Role-based shortcut into the expert/admin work area (hidden for farmers) */}
        <PortalSwitcher collapsed={collapsed} />
      </div>

      {/* Nav links */}
      <div className="flex-1 flex flex-col gap-1 overflow-y-auto py-2">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              title={collapsed ? item.label : undefined}
              className={`mx-2 py-3 rounded-lg flex items-center gap-3 transition-all text-sm ${
                collapsed ? "justify-center px-2" : "px-4"
              } ${
                active
                  ? "bg-secondary-container text-on-secondary-container font-bold"
                  : "text-on-surface-variant hover:bg-surface-container-high font-medium"
              }`}
            >
              <span
                className={`material-symbols-outlined text-[20px] flex-shrink-0 ${active ? "icon-fill" : ""}`}
              >
                {item.icon}
              </span>
              {!collapsed && item.label}
            </Link>
          );
        })}
      </div>

      {/* Footer */}
      <div className="mt-auto pt-3 border-t border-outline-variant px-2 pb-3">
        <button
          onClick={logout}
          title={collapsed ? "Đăng xuất" : undefined}
          className={`w-full text-on-surface-variant py-3 rounded-lg flex items-center gap-3 hover:bg-surface-container-high transition-all text-sm font-medium ${
            collapsed ? "justify-center px-2" : "px-4"
          }`}
        >
          <span className="material-symbols-outlined text-[20px] flex-shrink-0">logout</span>
          {!collapsed && "Đăng xuất"}
        </button>
      </div>
    </nav>
  );
}
