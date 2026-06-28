import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/lib/auth";

export type ExpertTab = "overview" | "queue" | "diagnoses" | "stats" | "experts";

const NAV: { id: ExpertTab; label: string; icon: string }[] = [
  { id: "overview", label: "Tổng quan", icon: "dashboard" },
  { id: "queue", label: "Hàng đợi xử lý", icon: "inbox" },
  { id: "diagnoses", label: "Tất cả ảnh", icon: "photo_library" },
  { id: "stats", label: "Thống kê", icon: "analytics" },
  { id: "experts", label: "Chuyên gia", icon: "groups" },
];

interface Props {
  active: ExpertTab;
  onNavigate: (tab: ExpertTab) => void;
  pendingCount?: number;
  children: ReactNode;
}

export function ExpertLayout({ active, onNavigate, pendingCount = 0, children }: Props) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-background text-on-surface flex flex-col md:flex-row">
      {/* Sidebar (desktop) / top nav (mobile) */}
      <aside className="md:w-64 md:min-h-screen border-b md:border-b-0 md:border-r border-outline-variant bg-surface flex md:flex-col">
        <div className="hidden md:flex items-center gap-2 px-5 h-16 border-b border-outline-variant">
          <span className="material-symbols-outlined text-primary icon-fill">eco</span>
          <span className="font-bold text-on-surface">Expert Console</span>
        </div>

        <nav className="flex md:flex-col gap-1 p-2 overflow-x-auto md:overflow-visible w-full">
          {NAV.map((item) => {
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
                {item.id === "queue" && pendingCount > 0 && (
                  <span className="ml-auto rounded-full bg-error text-on-error text-[10px] px-1.5 py-0.5">
                    {pendingCount}
                  </span>
                )}
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

      {/* Content */}
      <div className="flex-1 min-w-0 flex flex-col">{children}</div>
    </div>
  );
}
