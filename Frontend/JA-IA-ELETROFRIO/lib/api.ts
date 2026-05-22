import { eletrofrioApi } from "@/services/eletrofrioApi";
import type {
  ApiAsset,
  ApiDashboardResponse,
  ApiTemperaturePoint,
} from "@/lib/types";

export async function getApiHealth() {
  return eletrofrioApi.health();
}

export async function getDashboardData(): Promise<ApiDashboardResponse> {
  const overview = await eletrofrioApi.overview();
  const latestInsights = overview.latest_insights || [];
  const deviceMetrics = overview.device_metrics || [];

  const assets: ApiAsset[] = deviceMetrics.slice(0, 80).map((device) => {
    const status =
      (device.alarm_count || 0) >= 3
        ? "critical"
        : (device.alarm_count || 0) >= 1
          ? "warning"
          : "normal";

    return {
      asset_id: String(device.dispositivo_id ?? "-"),
      asset_type: "exhibitor",
      sector: device.loja_nome || `Loja ${device.loja_id ?? "-"}`,
      module_id: device.tag || "-",
      temperature_c: device.temperature_current,
      current_a: null,
      pressure_bar: null,
      humidity_pct: null,
      external_temp_c: null,
      status,
      anomaly_score: null,
      diagnosis:
        device.alarm_count > 0
          ? `${device.alarm_count} alarme(s) associado(s)`
          : "Sem alarme recente associado",
      updated_at: new Date().toISOString(),
    };
  });

  const alerts = latestInsights.map((insight) => ({
    asset_id: String(insight.dispositivo_id ?? insight.loja_id ?? "-"),
    asset_type: "exhibitor" as const,
    module_id: insight.tag || "-",
    sector: insight.loja_nome || `Loja ${insight.loja_id ?? "-"}`,
    level:
      insight.severity === "critical"
        ? ("critical" as const)
        : insight.severity === "warning"
          ? ("warning" as const)
          : ("info" as const),
    message: insight.summary,
    diagnosis: insight.technical_reason,
    anomaly_score: null,
    created_at: insight.created_at,
  }));

  const temperatureSeries: ApiTemperaturePoint[] = deviceMetrics
    .filter((device) => device.temperature_current != null)
    .slice(0, 40)
    .map((device, index) => ({
      time: new Date(Date.now() - (40 - index) * 60_000).toISOString(),
      temperature: Number(device.temperature_current),
      limit: 5,
      asset_id: String(device.dispositivo_id ?? "-"),
    }));

  return {
    metrics: {
      total_assets: overview.totals.devices,
      active_alerts: overview.totals.alarms,
      normal_assets: assets.filter((asset) => asset.status === "normal").length,
      warning_assets: assets.filter((asset) => asset.status === "warning").length,
      critical_assets: assets.filter((asset) => asset.status === "critical").length,
      average_risk_pct: overview.totals.alarms > 0 ? 62 : 12,
      stream_status: "online",
      last_update: new Date().toISOString(),
    },
    assets,
    alerts,
    temperature_series: temperatureSeries,
  };
}

export async function getLiveReadings() {
  return [];
}

export async function getAssets() {
  const data = await getDashboardData();
  return data.assets;
}

export async function getAlerts() {
  const data = await getDashboardData();
  return data.alerts;
}

export async function getTemperatureSeries(assetId?: string) {
  const data = await getDashboardData();
  return assetId
    ? data.temperature_series.filter((point) => point.asset_id === assetId)
    : data.temperature_series;
}
