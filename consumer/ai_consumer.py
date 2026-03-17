import json
import time
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


STREAM_PATH = Path("stream/live_readings.jsonl")
POLL_INTERVAL = 1.0
MIN_TRAIN_ROWS = 120


def load_all_readings() -> pd.DataFrame:
    if not STREAM_PATH.exists():
        return pd.DataFrame()

    rows = []
    with STREAM_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    numeric_cols = [
        "temperature_c",
        "humidity_pct",
        "current_a",
        "pressure_bar",
        "external_temp_c",
    ]

    for col in numeric_cols:
        if col not in work.columns:
            work[col] = None
        work[col] = pd.to_numeric(work[col], errors="coerce")

    work["temperature_c"] = work.groupby("asset_type")["temperature_c"].transform(lambda s: s.fillna(s.median()))
    work["humidity_pct"] = work.groupby("asset_type")["humidity_pct"].transform(lambda s: s.fillna(s.median()))
    work["current_a"] = work.groupby("asset_type")["current_a"].transform(lambda s: s.fillna(s.median()))
    work["pressure_bar"] = work.groupby("asset_type")["pressure_bar"].transform(lambda s: s.fillna(s.median()))
    work["external_temp_c"] = work.groupby("asset_type")["external_temp_c"].transform(lambda s: s.fillna(s.median()))

    work = work.fillna({
        "temperature_c": 0.0,
        "humidity_pct": 0.0,
        "current_a": 0.0,
        "pressure_bar": 0.0,
        "external_temp_c": 0.0,
    })

    work["asset_type_code"] = work["asset_type"].map({
        "exhibitor": 1,
        "cold_room": 2,
        "machine_room": 3,
    }).fillna(0)

    feature_cols = [
        "temperature_c",
        "humidity_pct",
        "current_a",
        "pressure_bar",
        "external_temp_c",
        "asset_type_code",
    ]
    return work[feature_cols]


def build_diagnosis(row: pd.Series) -> str:
    asset_type = row.get("asset_type")
    temp = row.get("temperature_c")
    current = row.get("current_a")
    pressure = row.get("pressure_bar")
    ext_temp = row.get("external_temp_c")

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

    return "Anomalia detectada; investigar ativo"


def train_model(df: pd.DataFrame):
    features = prepare_features(df)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(features)

    model = IsolationForest(
        n_estimators=250,
        contamination=0.03,
        random_state=42,
    )
    model.fit(x_scaled)
    return model, scaler


def score_rows(df_rows: pd.DataFrame, model, scaler) -> pd.DataFrame:
    work = df_rows.copy()
    features = prepare_features(work)
    x_scaled = scaler.transform(features)

    preds = model.predict(x_scaled)
    scores = model.decision_function(x_scaled)

    work["is_anomaly"] = preds == -1
    work["anomaly_score"] = scores
    return work


def main():
    print("Consumidor IA iniciado. Aguardando leituras...")
    processed_rows = 0

    while True:
        df = load_all_readings()

        if df.empty or len(df) < MIN_TRAIN_ROWS:
            print(f"[IA] Aguardando histórico suficiente... leituras atuais: {len(df)}")
            time.sleep(POLL_INTERVAL)
            continue

        if len(df) > processed_rows:
            model, scaler = train_model(df)

            new_rows = df.iloc[processed_rows:].copy()
            scored = score_rows(new_rows, model, scaler)

            for _, row in scored.iterrows():
                if row["is_anomaly"]:
                    diagnosis = build_diagnosis(row)
                    print(
                        f"[ALERTA] {row['ts']} | {row['asset_type']} | {row['asset_id']} "
                        f"| module={row['module_id']} | score={row['anomaly_score']:.4f} "
                        f"| {diagnosis}"
                    )
                else:
                    print(
                        f"[OK] {row['ts']} | {row['asset_type']} | {row['asset_id']} "
                        f"| module={row['module_id']} | score={row['anomaly_score']:.4f}"
                    )

            processed_rows = len(df)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()