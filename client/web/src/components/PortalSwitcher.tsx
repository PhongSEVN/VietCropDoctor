import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/lib/auth";

interface Portal {
  path: string;
  icon: string;
  label: string;
}

/** Work areas a role may switch into. Farmers get none (component renders null). */
function portalsForRole(role?: string): Portal[] {
  if (role === "agronomist") {
    return [{ path: "/expert/dashboard", icon: "agriculture", label: "Trang chuyên gia" }];
  }
  if (role === "admin") {
    return [{ path: "/admin", icon: "admin_panel_settings", label: "Trang quản trị" }];
  }
  return [];
}

/**
 * Sits next to the "Cuộc trò chuyện mới" CTA. Click to reveal a link into the
 * user's privileged work area (expert console for agronomists, admin console for
 * admins). Inline-expands so the sidebar's overflow-hidden never clips it.
 */
export default function PortalSwitcher({ collapsed }: { collapsed: boolean }) {
  const { user } = useAuth();
  const portals = portalsForRole(user?.role);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close when clicking outside.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  if (portals.length === 0) return null;

  return (
    <div ref={ref} className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={collapsed ? "Khu vực làm việc" : undefined}
        aria-expanded={open}
        className={`w-full rounded-full border border-outline-variant text-on-surface-variant text-sm font-medium flex items-center gap-2 hover:bg-surface-container-high transition-colors ${
          collapsed ? "justify-center p-2" : "py-2 px-4"
        }`}
      >
        <span className="material-symbols-outlined text-[18px]">workspaces</span>
        {!collapsed && <span className="flex-1 text-left">Khu vực làm việc</span>}
        {!collapsed && (
          <span className="material-symbols-outlined text-[18px]">
            {open ? "expand_less" : "expand_more"}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-1 space-y-1">
          {portals.map((p) => (
            <Link
              key={p.path}
              to={p.path}
              onClick={() => setOpen(false)}
              title={collapsed ? p.label : undefined}
              className={`rounded-lg flex items-center gap-3 text-sm text-on-surface-variant hover:bg-secondary-container hover:text-on-secondary-container transition-colors ${
                collapsed ? "justify-center p-2" : "py-2 px-4"
              }`}
            >
              <span className="material-symbols-outlined text-[20px] flex-shrink-0">{p.icon}</span>
              {!collapsed && p.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
