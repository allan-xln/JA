"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { eletrofrioApi } from "@/services/eletrofrioApi";
import type { EletrofrioInsight } from "@/types/eletrofrio";

export function useEletrofrioInsights(enabled = true) {
  const [insights, setInsights] = useState<EletrofrioInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const response = await eletrofrioApi.insights(120);
      setInsights(response.items || []);
      if (response.data_unavailable) {
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar insights.");
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

  return useMemo(
    () => ({ insights, loading, error, refresh }),
    [insights, loading, error, refresh]
  );
}
