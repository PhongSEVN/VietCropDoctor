import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/lib/auth";

export type AdminSection =
  | "overview"
  | "users"
  | "experts"
  | "models"
  | "analytics"
  | "trends"
  | "monitoring"
  | "kafka"
  | "audit"
  | "notifications"
  | "reports";

interface NavItem {
  id: AdminSection;
  label: string;
  icon: string;
  /** When true, only SUPER_ADMIN sees it (none today — reserved). */
  superOnly?: boolean;
}

const NAV: NavItem[] = [
  { id: "overview", label: "Tổng quan", icon: "dashboard" },
  { id: "users", label: "Người dùng", icon: "group" },
  { id: "experts", label: "Chuyên gia", icon: "agriculture" },
  { id: "models", label: "Model & Retrain", icon: "model_training" },
  { id: "analytics", label: "Analytics", icon: "monitoring" },
  { id: "trends", label: "Xu hướng", icon: "trending_up" },
  { id: "monitoring", label: "Giám sát hệ thống", icon: "monitor_heart" },
  { id: "kafka", label: "Kafka", icon: "swap_horiz" },
  { id: "audit", label: "Audit logs", icon: "history" },
  { id: "notifications", label: "Thông báo", icon: "campaign" },
  { id: "reports", label: "Báo cáo", icon: "summarize" },
];

interface Props {
  active: AdminSection;
  onNavigate: (s: AdminSection) => void;
  /** Permission-based rendering: items can be filtered by capability. */
  isSuperAdmin?: boolean;
  children: ReactNode;
}

export function AdminLayout({ active, onNavigate, isSuperAdmin = false, children }: Props) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const items = NAV.filter((i) => !i.superOnly || isSuperAdmin);

  return (
    <div className="min-h-screen bg-background text-on-surface flex flex-col md:flex-row">
      <aside className="md:w-64 md:min-h-screen border-b md:border-b-0 md:border-r border-outline-variant bg-surface flex md:flex-col">
        <div className="hidden md:flex items-center gap-2 px-5 h-16 border-b border-outline-variant">
          <span className="material-symbols-outlined text-primary icon-fill">admin_panel_settings</span>
          <span className="font-bold text-on-surface">Admin Console</span>
        </div>

        <nav className="flex md:flex-col gap-1 p-2 overflow-x-auto md:overflow-visible w-full">
          {items.map((item) => {
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? "bg-primary-container text-on-primary-container font-medium"
                    : "text-on-surface-variant hover:bg-surface-container-high"
                }`}
              >
                <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="hidden md:block mt-auto p-3 border-t border-outline-variant">
          <p className="text-xs text-on-surface-variant px-2">{user?.username}</p>
          <p className="text-[10px] text-on-surface-variant px-2 mb-2">Vai trò: {user?.role}</p>
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-2 w-full rounded-lg px-2 py-1.5 text-sm text-on-surface-variant hover:bg-surface-container-high"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Quay lại ứng dụng
          </button>
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full rounded-lg px-2 py-1.5 text-sm text-error hover:bg-error-container/40"
          >
            <span className="material-symbols-outlined text-[18px]">logout</span>
            Đăng xuất
          </button>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">{children}</div>
    </div>
  );
}
