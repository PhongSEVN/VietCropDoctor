import { useState } from "react";
import type { ReactNode } from "react";
import Sidebar from "./Sidebar";

interface MainLayoutProps {
  children: ReactNode;
  fullHeight?: boolean;
}

export default function MainLayout({ children, fullHeight = false }: MainLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);

  const sidebarW = collapsed ? "md:ml-[72px]" : "md:ml-[300px]";

  return (
    <div className={`flex bg-background text-on-surface ${fullHeight ? "h-screen overflow-hidden" : "min-h-screen"}`}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      {/* Mobile top bar */}
      <header className="md:hidden flex justify-between items-center px-4 h-16 w-full fixed top-0 z-50 bg-surface border-b border-outline-variant">
        <span className="text-2xl font-bold text-primary">VietCropDoctor</span>
        <div className="flex items-center gap-2 text-on-surface-variant">
          <button className="hover:bg-surface-container-high p-2 rounded-full transition-colors">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="hover:bg-surface-container-high p-2 rounded-full transition-colors">
            <span className="material-symbols-outlined">help</span>
          </button>
        </div>
      </header>

      <div
        className={`flex-1 flex flex-col transition-[margin] duration-300 ${sidebarW} ${
          fullHeight ? "h-screen overflow-hidden" : ""
        }`}
      >
        <div className={`mt-16 md:mt-0 ${fullHeight ? "flex-1 overflow-hidden flex flex-col" : ""}`}>
          {children}
        </div>
      </div>
    </div>
  );
}
