import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

type Role = "farmer" | "agronomist" | "admin";

interface RoleRouteProps {
  children: ReactNode;
  /** Roles allowed to view the route. */
  allow: Role[];
}

/**
 * Route guard that requires authentication AND one of the allowed roles.
 * Unauthenticated → /login. Authenticated but wrong role → home with a flag the
 * target page can surface. Note: this gates the UI only; the API must enforce
 * the same role server-side.
 */
export default function RoleRoute({ children, allow }: RoleRouteProps) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (!user || !allow.includes(user.role)) {
    return <Navigate to="/" replace state={{ forbidden: location.pathname }} />;
  }
  return <>{children}</>;
}

/** "Expert" in the product == agronomist role in the auth model (admin also allowed). */
export const EXPERT_ROLES: Role[] = ["agronomist", "admin"];
