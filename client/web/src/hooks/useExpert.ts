import { useCallback, useEffect, useMemo, useState } from "react";

import { applyCaseFilters, getAllDiagnoses, getExpertCase, getExpertQueue } from "@/lib/expert-api";
import { getCropName } from "@/lib/api";
import type { DiagnosisItem, ExpertCase, ExpertCaseFilters } from "@/types/expert";

const DEFAULT_FILTERS: ExpertCaseFilters = {
  search: "",
  status: "all",
  crop: "all",
  sort: "newest",
};

interface UseExpertQueue {
  cases: ExpertCase[];        // filtered + sorted
  allCases: ExpertCase[];     // unfiltered (for stats)
  crops: string[];            // distinct crops for the filter dropdown
  loading: boolean;
  error: string | null;
  filters: ExpertCaseFilters;
  setFilters: (patch: Partial<ExpertCaseFilters>) => void;
  refetch: () => void;
}

export function useExpertQueue(): UseExpertQueue {
  const [allCases, setAllCases] = useState<ExpertCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFiltersState] = useState<ExpertCaseFilters>(DEFAULT_FILTERS);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getExpertQueue()
      .then(setAllCases)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được hàng đợi"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const setFilters = useCallback((patch: Partial<ExpertCaseFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...patch }));
  }, []);

  const cases = useMemo(() => applyCaseFilters(allCases, filters), [allCases, filters]);

  const crops = useMemo(() => {
    const set = new Set<string>();
    for (const c of allCases) {
      const crop = c.crop || getCropName(c.ai.predicted_disease);
      if (crop) set.add(crop);
    }
    return [...set].sort();
  }, [allCases]);

  return { cases, allCases, crops, loading, error, filters, setFilters, refetch };
}

interface UseAllDiagnoses {
  diagnoses: DiagnosisItem[];
  loading: boolean;
  error: string | null;
  pendingOnly: boolean;
  setPendingOnly: (v: boolean) => void;
  refetch: () => void;
}

/** Load EVERY image diagnosis (incl. images the user never gave feedback on). */
export function useAllDiagnoses(): UseAllDiagnoses {
  const [diagnoses, setDiagnoses] = useState<DiagnosisItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingOnly, setPendingOnly] = useState(false);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getAllDiagnoses(pendingOnly)
      .then(setDiagnoses)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách ảnh"))
      .finally(() => setLoading(false));
  }, [pendingOnly]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { diagnoses, loading, error, pendingOnly, setPendingOnly, refetch };
}

interface UseExpertCase {
  detail: ExpertCase | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Load full detail for a selected case. Pass null to clear. */
export function useExpertCase(id: string | null): UseExpertCase {
  const [detail, setDetail] = useState<ExpertCase | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    if (!id) {
      setDetail(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    getExpertCase(id)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được chi tiết ca"))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { detail, loading, error, refetch };
}
