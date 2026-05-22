/* =========================
   TIPOS DE UI (FRONT)
========================= */

export type MetricItem = {
  label: string;
  value: string;
  helper: string;
  trend: "up" | "down" | "neutral";
};

export type AssetRow = {
  assetId: string;
  sector: string;
  temperature: string;
  current: string;
  pressure: string;
  status: "normal" | "warning" | "critical";
};

export type AlertItem = {
  assetId: string;
  message: string;
  time: string;
  level: "info" | "warning" | "critical";
};

export type ChartPoint = {
  time: string;
  temperature: number;
  limit: number;
};

/* =========================
   TIPOS DA API (BACKEND)
========================= */

export type ApiHealthResponse = {
  status: string;
  message?: string;
};

export type ApiReading = {
  ts: string;
  store_id: string;
  asset_type: "exhibitor" | "cold_room" | "machine_room";
  asset_id: string;
  module_id: string;
  sector: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  current_a: number | null;
  pressure_bar: number | null;
  external_temp_c: number | null;
  is_anomaly?: boolean;
  anomaly_score?: number | null;
  diagnosis?: string | null;
};

export type ApiDashboardMetrics = {
  total_assets: number;
  active_alerts: number;
  normal_assets: number;
  warning_assets: number;
  critical_assets: number;
  average_risk_pct: number;
  stream_status: "online" | "offline";
  last_update: string | null;
};

export type ApiAsset = {
  asset_id: string;
  asset_type: "exhibitor" | "cold_room" | "machine_room";
  sector: string;
  module_id: string;
  temperature_c: number | null;
  current_a: number | null;
  pressure_bar: number | null;
  humidity_pct: number | null;
  external_temp_c: number | null;
  status: "normal" | "warning" | "critical";
  anomaly_score: number | null;
  diagnosis?: string | null;
  updated_at: string;
};

export type ApiAlert = {
  asset_id: string;
  asset_type: "exhibitor" | "cold_room" | "machine_room";
  module_id: string;
  sector: string;
  level: "info" | "warning" | "critical";
  message: string;
  diagnosis?: string | null;
  anomaly_score: number | null;
  created_at: string;
};

export type ApiTemperaturePoint = {
  time: string;
  temperature: number;
  limit: number;
  asset_id: string;
};

export type ApiDashboardResponse = {
  metrics: ApiDashboardMetrics;
  assets: ApiAsset[];
  alerts: ApiAlert[];
  temperature_series: ApiTemperaturePoint[];
};

/* =========================
   MAPPERS (BACK → FRONT)
========================= */

export function mapAssetToRow(asset: ApiAsset): AssetRow {
  return {
    assetId: asset.asset_id,
    sector: asset.sector,
    temperature:
      asset.temperature_c !== null ? `${asset.temperature_c.toFixed(1)}°C` : "-",
    current: asset.current_a !== null ? `${asset.current_a.toFixed(1)} A` : "-",
    pressure:
      asset.pressure_bar !== null ? `${asset.pressure_bar.toFixed(1)} bar` : "-",
    status: asset.status,
  };
}

export function mapAlertToItem(alert: ApiAlert): AlertItem {
  return {
    assetId: alert.asset_id,
    message: alert.message,
    level: alert.level,
    time: new Date(alert.created_at).toLocaleTimeString("pt-BR"),
  };
}

export function mapChart(points: ApiTemperaturePoint[]): ChartPoint[] {
  return points.map((point) => ({
    time: new Date(point.time).toLocaleTimeString("pt-BR"),
    temperature: point.temperature,
    limit: point.limit,
  }));
}
