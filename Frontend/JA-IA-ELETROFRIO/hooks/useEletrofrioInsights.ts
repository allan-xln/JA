"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { eletrofrioApi } from "@/services/eletrofrioApi";
import type { EletrofrioInsight } from "@/types/eletrofrio";

export function useEletrofrioInsights() {
  const [insights, setInsights] = useState<EletrofrioInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const response = await eletrofrioApi.insights(120);
      setInsights(response.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar insights.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return useMemo(
    () => ({ insights, loading, error, refresh }),
    [insights, loading, error, refresh]
  );
}
