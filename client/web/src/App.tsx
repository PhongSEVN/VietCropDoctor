import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ProfileProvider } from "@/lib/profile-context";
import ProtectedRoute from "@/components/ProtectedRoute";
import RoleRoute, { EXPERT_ROLES } from "@/components/RoleRoute";
import ExpertDashboardPage from "./pages/expert/ExpertDashboardPage";
import AdminDashboardPage from "./pages/admin/AdminDashboardPage";
import HomePage from "./pages/HomePage";
import ChatPage from "./pages/ChatPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import LoginPage from "./pages/LoginPage";
import DiagnosePage from "./pages/DiagnosePage";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";
import LibraryPage from "./pages/LibraryPage";
import NotFoundPage from "./pages/NotFoundPage";

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route
        path="/"
        element={<ProtectedRoute><HomePage /></ProtectedRoute>}
      />
      <Route
        path="/chat"
        element={<ProtectedRoute><ChatPage /></ProtectedRoute>}
      />
      <Route
        path="/diagnose"
        element={<ProtectedRoute><DiagnosePage /></ProtectedRoute>}
      />
      <Route
        path="/library"
        element={<ProtectedRoute><LibraryPage /></ProtectedRoute>}
      />
      <Route
        path="/history"
        element={<ProtectedRoute><HistoryPage /></ProtectedRoute>}
      />
      <Route
        path="/settings"
        element={<ProtectedRoute><SettingsPage /></ProtectedRoute>}
      />
      <Route
        path="/analytics"
        element={<ProtectedRoute><AnalyticsPage /></ProtectedRoute>}
      />
      <Route
        path="/expert/dashboard"
        element={<RoleRoute allow={EXPERT_ROLES}><ExpertDashboardPage /></RoleRoute>}
      />
      <Route
        path="/admin"
        element={<RoleRoute allow={["admin"]}><AdminDashboardPage /></RoleRoute>}
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ProfileProvider>
          <AppRoutes />
        </ProfileProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

