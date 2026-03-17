import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Eletrofrio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STREAM_PATH = Path("stream/live_readings.jsonl")


def load_stream_dataframe() -> pd.DataFrame:
    if not STREAM_PATH.exists():
        return pd.DataFrame()

    rows = []
    with STREAM_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


def build_asset_status(row: pd.Series) -> str:
    asset_type = row.get("asset_type")
    temp = row.get("temperature_c")
    current = row.get("current_a")
    pressure = row.get("pressure_bar")
    simulated_anomaly = row.get("simulated_anomaly")

    if simulated_anomaly:
        if simulated_anomaly in {
            "falha_refrigeracao",
            "perda_critica_de_capacidade",
            "pressao_baixa_critica",
        }:
            return "critical"
        return "warning"

    if asset_type in {"exhibitor", "cold_room"} and pd.notna(temp):
        if temp >= 8:
            return "critical"
        if temp >= 5:
            return "warning"

    if asset_type == "machine_room":
        if pd.notna(current) and pd.notna(pressure):
            if current >= 50 and pressure <= 13:
                return "critical"
            if pressure <= 12:
                return "critical"
            if current >= 46:
                return "warning"

    return "normal"


def build_diagnosis(row: pd.Series) -> str | None:
    asset_type = row.get("asset_type")
    temp = row.get("temperature_c")
    current = row.get("current_a")
    pressure = row.get("pressure_bar")
    ext_temp = row.get("external_temp_c")
    simulated_anomaly = row.get("simulated_anomaly")

    if simulated_anomaly == "falha_refrigeracao":
        return "Falha crítica de refrigeração detectada"
    if simulated_anomaly == "porta_aberta_ou_carga_termica":
        return "Possível porta aberta ou carga térmica elevada"
    if simulated_anomaly == "abertura_frequente_ou_infiltracao":
        return "Possível infiltração térmica ou abertura frequente"
    if simulated_anomaly == "perda_critica_de_capacidade":
        return "Possível perda crítica de capacidade de refrigeração"
    if simulated_anomaly == "sobrecarga_ou_baixa_eficiencia":
        return "Possível sobrecarga ou baixa eficiência do compressor"
    if simulated_anomaly == "pressao_baixa_critica":
        return "Possível queda crítica de pressão no circuito"

    if asset_type in {"exhibitor", "cold_room"}:
        if pd.notna(temp):
            if temp >= 8:
                return "Falha crítica de refrigeração ou grande perda de capacidade"
            if temp >= 5:
                return "Possível porta aberta, infiltração térmica ou perda parcial de capacidade"
            if asset_type == "cold_room" and temp >= 3:
                return "Temperatura acima do ideal para câmara resfriada"

    if asset_type == "machine_room":
        if pd.notna(current) and pd.notna(pressure):
            if current >= 50 and pressure <= 13:
                return "Possível sobrecarga de compressor ou baixa eficiência com pressão baixa"
            if pressure <= 12:
                return "Possível queda crítica de pressão; verificar circuito frigorífico"
            if pd.notna(ext_temp) and ext_temp >= 33 and current >= 46:
                return "Carga térmica externa alta impactando eficiência da casa de máquinas"

    return None


def build_alert_level(status: str) -> str:
    if status == "critical":
        return "critical"
    if status == "warning":
        return "warning"
    return "info"


def get_temperature_limit(row: pd.Series) -> float:
    asset_type = row.get("asset_type")
    sector = row.get("sector")

    if asset_type == "cold_room":
        if sector == "camara_congelada":
            return -18.0
        return 3.0

    if asset_type == "exhibitor":
        if sector == "congelados":
            return -18.0
        if sector == "hortifruti":
            return 7.0
        return 5.0

    return 0.0


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
def get_dashboard():
    df = load_stream_dataframe()

    if df.empty:
        return {
            "metrics": {
                "total_assets": 0,
                "active_alerts": 0,
                "normal_assets": 0,
                "warning_assets": 0,
                "critical_assets": 0,
                "average_risk_pct": 0.0,
                "stream_status": "offline",
                "last_update": None,
            },
            "assets": [],
            "alerts": [],
            "temperature_series": [],
        }

    latest_by_asset = (
        df.sort_values("ts")
        .groupby("asset_id", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )

    assets = []
    alerts = []

    normal_count = 0
    warning_count = 0
    critical_count = 0
    risk_values = []

    for _, row in latest_by_asset.iterrows():
        status = build_asset_status(row)
        diagnosis = build_diagnosis(row)

        if status == "normal":
            normal_count += 1
            risk_values.append(10.0)
        elif status == "warning":
            warning_count += 1
            risk_values.append(55.0)
        else:
            critical_count += 1
            risk_values.append(90.0)

        asset = {
            "asset_id": row["asset_id"],
            "asset_type": row["asset_type"],
            "sector": row["sector"],
            "module_id": row["module_id"],
            "temperature_c": None if pd.isna(row.get("temperature_c")) else float(row.get("temperature_c")),
            "current_a": None if pd.isna(row.get("current_a")) else float(row.get("current_a")),
            "pressure_bar": None if pd.isna(row.get("pressure_bar")) else float(row.get("pressure_bar")),
            "humidity_pct": None if pd.isna(row.get("humidity_pct")) else float(row.get("humidity_pct")),
            "external_temp_c": None if pd.isna(row.get("external_temp_c")) else float(row.get("external_temp_c")),
            "status": status,
            "anomaly_score": None,
            "diagnosis": diagnosis,
            "updated_at": row["ts"].isoformat(),
        }
        assets.append(asset)

        if status in {"warning", "critical"}:
            alerts.append(
                {
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "module_id": row["module_id"],
                    "sector": row["sector"],
                    "level": build_alert_level(status),
                    "message": diagnosis or "Anomalia operacional detectada",
                    "diagnosis": diagnosis,
                    "anomaly_score": None,
                    "created_at": row["ts"].isoformat(),
                }
            )

    temp_df = df[df["temperature_c"].notna()].copy().tail(60)

    temperature_series = []
    for _, row in temp_df.iterrows():
        temperature_series.append(
            {
                "time": row["ts"].isoformat(),
                "temperature": float(row["temperature_c"]),
                "limit": get_temperature_limit(row),
                "asset_id": row["asset_id"],
            }
        )

    average_risk_pct = round(sum(risk_values) / len(risk_values), 1) if risk_values else 0.0

    return {
        "metrics": {
            "total_assets": len(assets),
            "active_alerts": len(alerts),
            "normal_assets": normal_count,
            "warning_assets": warning_count,
            "critical_assets": critical_count,
            "average_risk_pct": average_risk_pct,
            "stream_status": "online",
            "last_update": df.iloc[-1]["ts"].isoformat(),
        },
        "assets": assets,
        "alerts": alerts,
        "temperature_series": temperature_series,
    }


@app.get("/api/assets")
def get_assets():
    return get_dashboard()["assets"]


@app.get("/api/alerts")
def get_alerts():
    return get_dashboard()["alerts"]


@app.get("/api/charts/temperature")
def get_temperature_chart(asset_id: str | None = None):
    data = get_dashboard()["temperature_series"]
    if asset_id:
        data = [item for item in data if item["asset_id"] == asset_id]
    return data


@app.get("/api/readings/live")
def get_live_readings():
    df = load_stream_dataframe()
    if df.empty:
        return []

    latest_rows = df.tail(50).copy()

    results = []
    for _, row in latest_rows.iterrows():
        diagnosis = build_diagnosis(row)
        status = build_asset_status(row)

        results.append(
            {
                "ts": row["ts"].isoformat(),
                "store_id": row["store_id"],
                "asset_type": row["asset_type"],
                "asset_id": row["asset_id"],
                "module_id": row["module_id"],
                "sector": row["sector"],
                "temperature_c": None if pd.isna(row.get("temperature_c")) else float(row.get("temperature_c")),
                "humidity_pct": None if pd.isna(row.get("humidity_pct")) else float(row.get("humidity_pct")),
                "current_a": None if pd.isna(row.get("current_a")) else float(row.get("current_a")),
                "pressure_bar": None if pd.isna(row.get("pressure_bar")) else float(row.get("pressure_bar")),
                "external_temp_c": None if pd.isna(row.get("external_temp_c")) else float(row.get("external_temp_c")),
                "simulated_anomaly": row.get("simulated_anomaly"),
                "is_anomaly": status in {"warning", "critical"},
                "anomaly_score": None,
                "diagnosis": diagnosis,
            }
        )

    return results