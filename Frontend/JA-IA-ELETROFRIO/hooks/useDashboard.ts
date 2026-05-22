"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getDashboardData } from "@/lib/api";
import {
  mapAlertToItem,
  mapAssetToRow,
  mapChart,
  type AlertItem,
  type AssetRow,
  type ChartPoint,
  type MetricItem,
} from "@/lib/types";

type UseDashboardResult = {
  metrics: MetricItem[];
  assets: AssetRow[];
  alerts: AlertItem[];
  chartData: ChartPoint[];
  loading: boolean;
  error: string | null;
  lastUpdate: string | null;
  refresh: () => Promise<void>;
};

function formatDateTime(value: string | null) {
  if (!value) return null;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleString("pt-BR");
}

export function useDashboard(autoRefreshMs = 5000): UseDashboardResult {
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      setError(null);

      const data = await getDashboardData();

      const mappedMetrics: MetricItem[] = [
        {
          label: "Ativos monitorados",
          value: String(data.metrics.total_assets),
          helper: `${data.metrics.normal_assets} em operação normal`,
          trend: "neutral",
        },
        {
          label: "Alertas ativos",
          value: String(data.metrics.active_alerts),
          helper:
            data.metrics.active_alerts > 0
              ? `${data.metrics.critical_assets} críticos no momento`
              : "Nenhum alerta ativo",
          trend: data.metrics.active_alerts > 0 ? "down" : "up",
        },
        {
          label: "Risco médio",
          value: `${data.metrics.average_risk_pct.toFixed(1)}%`,
          helper:
            data.metrics.average_risk_pct >= 60
              ? "Operação exige atenção imediata"
              : data.metrics.average_risk_pct >= 30
                ? "Risco moderado na operação"
                : "Operação estável",
          trend:
            data.metrics.average_risk_pct >= 60
              ? "down"
              : data.metrics.average_risk_pct >= 30
                ? "neutral"
                : "up",
        },
        {
          label: "Coleta",
          value: data.metrics.stream_status === "online" ? "Online" : "Offline",
          helper:
            data.metrics.stream_status === "online"
              ? "Leitura contínua ativa"
              : "Sem atualização recente",
          trend: data.metrics.stream_status === "online" ? "up" : "down",
        },
      ];

      setMetrics(mappedMetrics);
      setAssets(data.assets.map(mapAssetToRow));
      setAlerts(data.alerts.map(mapAlertToItem));
      setChartData(mapChart(data.temperature_series));
      setLastUpdate(formatDateTime(data.metrics.last_update));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Erro ao carregar dashboard";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!autoRefreshMs || autoRefreshMs <= 0) return;

    const interval = setInterval(() => {
      void loadDashboard();
    }, autoRefreshMs);

    return () => clearInterval(interval);
  }, [autoRefreshMs, loadDashboard]);

  return useMemo(
    () => ({
      metrics,
      assets,
      alerts,
      chartData,
      loading,
      error,
      lastUpdate,
      refresh: loadDashboard,
    }),
    [metrics, assets, alerts, chartData, loading, error, lastUpdate, loadDashboard]
  );
}
