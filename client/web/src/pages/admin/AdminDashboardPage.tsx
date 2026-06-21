import { useState } from "react";

import { AdminLayout, type AdminSection } from "@/components/admin/AdminLayout";
import { AdminKpiCards } from "@/components/admin/AdminKpiCards";
import { UserManagement } from "@/components/admin/UserManagement";
import { ExpertManagement } from "@/components/admin/ExpertManagement";
import { ModelManagement } from "@/components/admin/ModelManagement";
import { AdminAnalytics } from "@/components/admin/AdminAnalytics";
import { TrendAnalysis } from "@/components/admin/TrendAnalysis";
import { SystemMonitoring } from "@/components/admin/SystemMonitoring";
import { AuditLogs } from "@/components/admin/AuditLogs";
import { NotificationCenter } from "@/components/admin/NotificationCenter";
import { Reports } from "@/components/admin/Reports";
import { ErrorState, LoadingState } from "@/components/expert/states";
import { useAdminKpis } from "@/hooks/useAdmin";

const SECTION_META: Record<AdminSection, { title: string; subtitle: string }> = {
  overview:      { title: "Tổng quan", subtitle: "Chỉ số tổng hợp toàn hệ thống" },
  users:         { title: "Quản lý người dùng", subtitle: "Danh sách, CRUD, phân quyền" },
  experts:       { title: "Quản lý chuyên gia", subtitle: "Hiệu suất và phân công lĩnh vực" },
  models:        { title: "Model & Retrain", subtitle: "Hiệu năng model, huấn luyện lại, triển khai" },
  analytics:     { title: "Analytics", subtitle: "Phân tích dữ liệu từ ClickHouse" },
  trends:        { title: "Phân tích xu hướng", subtitle: "Cây trồng, bệnh, khu vực, dự báo" },
  monitoring:    { title: "Giám sát hệ thống", subtitle: "Trạng thái dịch vụ và tài nguyên" },
  audit:         { title: "Audit logs", subtitle: "Mọi thao tác quản trị được ghi vết" },
  notifications: { title: "Trung tâm thông báo", subtitle: "Gửi thông báo toàn hệ thống/nhóm" },
  reports:       { title: "Báo cáo", subtitle: "Export CSV / Excel / PDF" },
};

export default function AdminDashboardPage() {
  const [section, setSection] = useState<AdminSection>("overview");
  const meta = SECTION_META[section];

  return (
    <AdminLayout active={section} onNavigate={setSection}>
      <header className="flex items-center justify-between gap-4 border-b border-outline-variant px-5 h-16 bg-surface">
        <div>
          <h1 className="text-lg font-bold text-on-surface">{meta.title}</h1>
          <p className="text-xs text-on-surface-variant">{meta.subtitle}</p>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-5">
        {section === "overview" && <Overview />}
        {section === "users" && <UserManagement />}
        {section === "experts" && <ExpertManagement />}
        {section === "models" && <ModelManagement />}
        {section === "analytics" && <AdminAnalytics />}
        {section === "trends" && <TrendAnalysis />}
        {section === "monitoring" && <SystemMonitoring />}
        {section === "audit" && <AuditLogs />}
        {section === "notifications" && <NotificationCenter />}
        {section === "reports" && <Reports />}
      </main>
    </AdminLayout>
  );
}

function Overview() {
  const { data, loading, error, refetch } = useAdminKpis();
  return (
    <div className="space-y-4">
      {loading && !data && <LoadingState label="Đang tải KPI tổng quan..." />}
      {error && !data && (
        <ErrorState message={error} onRetry={refetch} hint="Endpoint /admin/kpis chưa được backend cài đặt (xem TODO trong lib/admin-api.ts)." />
      )}
      {data && <AdminKpiCards kpis={data} />}
      <p className="text-xs text-on-surface-variant">
        Dùng thanh bên để vào từng module: Người dùng, Chuyên gia, Analytics, Xu hướng, Giám sát, Audit, Thông báo, Báo cáo.
      </p>
    </div>
  );
}
