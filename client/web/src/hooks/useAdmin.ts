import { useCallback, useEffect, useState } from "react";

import {
  getAdminKpis,
  getSystemMetrics,
  listAuditLogs,
  listExperts,
  listUsers,
} from "@/lib/admin-api";
import type {
  AdminKpis,
  AdminUser,
  AuditFilters,
  AuditLog,
  ExpertProfile,
  Paginated,
  SystemMetrics,
  UserFilters,
} from "@/types/admin";

const DEFAULT_USER_FILTERS: UserFilters = {
  search: "",
  role: "all",
  status: "all",
  sort: "newest",
  page: 1,
  page_size: 20,
};

interface UseUsers {
  data: Paginated<AdminUser> | null;
  loading: boolean;
  error: string | null;
  filters: UserFilters;
  setFilters: (patch: Partial<UserFilters>) => void;
  refetch: () => void;
}

export function useUsers(): UseUsers {
  const [data, setData] = useState<Paginated<AdminUser> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFiltersState] = useState<UserFilters>(DEFAULT_USER_FILTERS);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    listUsers(filters)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách người dùng"))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Changing any filter (other than page) resets pagination to page 1.
  const setFilters = useCallback((patch: Partial<UserFilters>) => {
    setFiltersState((prev) => {
      const next = { ...prev, ...patch };
      if (!("page" in patch)) next.page = 1;
      return next;
    });
  }, []);

  return { data, loading, error, filters, setFilters, refetch };
}

const DEFAULT_AUDIT_FILTERS: AuditFilters = { search: "", action: "all", page: 1, page_size: 25 };

interface UseAuditLogs {
  data: Paginated<AuditLog> | null;
  loading: boolean;
  error: string | null;
  filters: AuditFilters;
  setFilters: (patch: Partial<AuditFilters>) => void;
  refetch: () => void;
}

export function useAuditLogs(): UseAuditLogs {
  const [data, setData] = useState<Paginated<AuditLog> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFiltersState] = useState<AuditFilters>(DEFAULT_AUDIT_FILTERS);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    listAuditLogs(filters)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được nhật ký audit"))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const setFilters = useCallback((patch: Partial<AuditFilters>) => {
    setFiltersState((prev) => {
      const next = { ...prev, ...patch };
      if (!("page" in patch)) next.page = 1;
      return next;
    });
  }, []);

  return { data, loading, error, filters, setFilters, refetch };
}

interface UseAsync<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

function useAsync<T>(fn: () => Promise<T>, fallbackMsg: string, pollMs?: number): UseAsync<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    fn()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : fallbackMsg))
      .finally(() => setLoading(false));
    // fn identity is stable per caller (module function); intentional single binding.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refetch();
    if (!pollMs) return;
    const t = setInterval(refetch, pollMs);
    return () => clearInterval(t);
  }, [refetch, pollMs]);

  return { data, loading, error, refetch };
}

export function useSystemHealth(pollMs = 15_000): UseAsync<SystemMetrics> {
  return useAsync(getSystemMetrics, "Không tải được trạng thái hệ thống", pollMs);
}

export function useAdminKpis(): UseAsync<AdminKpis> {
  return useAsync(getAdminKpis, "Không tải được KPI");
}

export function useExperts(): UseAsync<ExpertProfile[]> {
  return useAsync(listExperts, "Không tải được danh sách chuyên gia");
}
