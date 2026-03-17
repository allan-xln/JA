"""
Simulador de sensores para o projeto Eletrofrio.

Objetivo:
- Gerar leituras contínuas e realistas de ativos de refrigeração.
- Escrever essas leituras em um arquivo JSONL (uma linha JSON por leitura).
- Servir como fonte de dados "ao vivo" para o consumidor de IA.

Como rodar (recomendado):
    python -m Sensors.simulator

Também pode funcionar com:
    python Sensors/simulator.py

Saída:
    stream/live_readings.jsonl
"""

import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# IMPORT FLEXÍVEL
# ----------------------------------------------------------------------------
# Este bloco permite que o arquivo funcione tanto:
# 1) rodando como módulo: python -m Sensors.simulator
# 2) rodando direto:      python Sensors/simulator.py
# ============================================================================
try:
    from Sensors.config import ASSETS, AssetConfig
except ModuleNotFoundError:
    from config import ASSETS, AssetConfig


# ============================================================================
# CONFIGURAÇÃO DO ARQUIVO DE STREAM
# ----------------------------------------------------------------------------
# O arquivo JSONL funciona como um "stream simples".
# Cada linha é um JSON independente, fácil de consumir em tempo real.
# ============================================================================
STREAM_PATH = Path("stream/live_readings.jsonl")
STREAM_PATH.parent.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    """
    Retorna o timestamp atual em UTC no formato ISO 8601.
    Exemplo: 2026-03-17T22:10:35.123456+00:00
    """
    return datetime.now(timezone.utc).isoformat()


def bounded(value: float, min_v: float, max_v: float) -> float:
    """
    Limita um valor entre um mínimo e um máximo.
    Útil para evitar números absurdos na simulação.
    """
    return max(min_v, min(max_v, value))


def generate_exhibitor_reading(asset: AssetConfig, minute_of_day: int) -> dict:
    """
    Gera leitura para expositores refrigerados.

    Exemplos de setores:
    - açougue
    - peixaria
    - hortifrúti
    - laticínios
    - congelados

    Lógica:
    - usa setpoint do ativo como base
    - adiciona pequena oscilação diária
    - adiciona ruído aleatório
    - pode injetar anomalias ocasionais
    """
    # Oscilação suave ao longo do "dia simulado"
    daily_wave = math.sin((minute_of_day / 1440) * 2 * math.pi) * 0.2

    # Temperatura base com ruído normal
    temp = asset.temp_setpoint_c + daily_wave + random.gauss(0, asset.temp_noise)

    # Umidade opcional, apenas quando o ativo tiver esse parâmetro configurado
    humidity = None
    if asset.humidity_base_pct is not None:
        humidity = bounded(
            asset.humidity_base_pct + random.gauss(0, 2.0),
            75,
            98,
        )

    anomaly_type = None

    # Simulação de porta aberta / carga térmica acima do normal
    if random.random() < 0.01:
        temp += random.uniform(2.5, 6.0)
        anomaly_type = "porta_aberta_ou_carga_termica"

    # Simulação de falha de refrigeração mais severa
    if random.random() < 0.003:
        temp += random.uniform(6.0, 12.0)
        anomaly_type = "falha_refrigeracao"

    return {
        "ts": now_iso(),
        "store_id": asset.store_id,
        "asset_type": asset.asset_type,
        "asset_id": asset.asset_id,
        "module_id": asset.module_id,
        "sector": asset.sector,
        "temperature_c": round(temp, 2),
        "humidity_pct": round(humidity, 2) if humidity is not None else None,
        "current_a": None,
        "pressure_bar": None,
        "external_temp_c": None,
        "simulated_anomaly": anomaly_type,
    }


def generate_cold_room_reading(asset: AssetConfig, minute_of_day: int) -> dict:
    """
    Gera leitura para câmaras frigoríficas.

    Lógica:
    - temperatura mais estável do que expositores
    - pequenas oscilações
    - possibilidade de infiltração térmica ou perda de capacidade
    """
    daily_wave = math.sin((minute_of_day / 1440) * 2 * math.pi) * 0.1
    temp = asset.temp_setpoint_c + daily_wave + random.gauss(0, asset.temp_noise)

    anomaly_type = None

    # Abertura frequente de porta / infiltração
    if random.random() < 0.007:
        temp += random.uniform(1.5, 4.0)
        anomaly_type = "abertura_frequente_ou_infiltracao"

    # Perda crítica de capacidade de refrigeração
    if random.random() < 0.002:
        temp += random.uniform(5.0, 10.0)
        anomaly_type = "perda_critica_de_capacidade"

    return {
        "ts": now_iso(),
        "store_id": asset.store_id,
        "asset_type": asset.asset_type,
        "asset_id": asset.asset_id,
        "module_id": asset.module_id,
        "sector": asset.sector,
        "temperature_c": round(temp, 2),
        "humidity_pct": None,
        "current_a": None,
        "pressure_bar": None,
        "external_temp_c": None,
        "simulated_anomaly": anomaly_type,
    }


def generate_machine_room_reading(asset: AssetConfig, minute_of_day: int) -> dict:
    """
    Gera leitura para casa de máquinas.

    Variáveis simuladas:
    - temperatura externa
    - corrente elétrica
    - pressão do sistema

    Lógica:
    - temperatura externa varia ao longo do dia
    - corrente e pressão reagem parcialmente à temperatura externa
    - anomalias simulam sobrecarga ou queda crítica de pressão
    """
    # Temperatura externa com ciclo diário e ruído
    ext_temp = asset.external_temp_base_c + math.sin((minute_of_day / 1440) * 2 * math.pi) * 3
    ext_temp += random.gauss(0, 0.8)

    # Corrente cresce um pouco com o aumento da temperatura externa
    current = asset.current_base_a + ((ext_temp - asset.external_temp_base_c) * 0.35)
    current += random.gauss(0, 0.9)

    # Pressão também sofre variação, porém menor
    pressure = asset.pressure_base_bar + ((ext_temp - asset.external_temp_base_c) * 0.08)
    pressure += random.gauss(0, 0.25)

    anomaly_type = None
    temperature_c = None  # casa de máquinas não usa temperatura interna do módulo aqui

    # Sobrecarga / baixa eficiência
    if random.random() < 0.008:
        current += random.uniform(6.0, 12.0)
        pressure -= random.uniform(1.0, 2.5)
        anomaly_type = "sobrecarga_ou_baixa_eficiencia"

    # Possível perda de fluido / baixa pressão crítica
    if random.random() < 0.003:
        current += random.uniform(2.0, 5.0)
        pressure -= random.uniform(2.5, 4.5)
        anomaly_type = "pressao_baixa_critica"

    return {
        "ts": now_iso(),
        "store_id": asset.store_id,
        "asset_type": asset.asset_type,
        "asset_id": asset.asset_id,
        "module_id": asset.module_id,
        "sector": asset.sector,
        "temperature_c": temperature_c,
        "humidity_pct": None,
        "current_a": round(current, 2),
        "pressure_bar": round(pressure, 2),
        "external_temp_c": round(ext_temp, 2),
        "simulated_anomaly": anomaly_type,
    }


def generate_reading(asset: AssetConfig, minute_of_day: int) -> dict:
    """
    Direciona a geração de leitura conforme o tipo de ativo.
    """
    if asset.asset_type == "exhibitor":
        return generate_exhibitor_reading(asset, minute_of_day)

    if asset.asset_type == "cold_room":
        return generate_cold_room_reading(asset, minute_of_day)

    if asset.asset_type == "machine_room":
        return generate_machine_room_reading(asset, minute_of_day)

    raise ValueError(f"asset_type desconhecido: {asset.asset_type}")


def append_reading_to_stream(reading: dict) -> None:
    """
    Escreve uma leitura no arquivo JSONL.
    Cada leitura vira uma linha.
    """
    with STREAM_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reading, ensure_ascii=False) + "\n")


def print_reading_summary(reading: dict) -> None:
    """
    Imprime um resumo curto da leitura no terminal,
    útil para acompanhar a simulação em tempo real.
    """
    print(
        f"[SIM] "
        f"{reading['asset_type']} "
        f"{reading['asset_id']} "
        f"module={reading['module_id']} "
        f"temp={reading['temperature_c']} "
        f"hum={reading['humidity_pct']} "
        f"curr={reading['current_a']} "
        f"press={reading['pressure_bar']} "
        f"ext={reading['external_temp_c']} "
        f"anomaly={reading['simulated_anomaly']}"
    )


def main() -> None:
    """
    Loop principal do simulador.

    A cada ciclo:
    - calcula o minuto do dia simulado
    - gera uma leitura para cada ativo configurado
    - grava a leitura no stream
    - imprime no terminal
    - espera 1 segundo

    Observação:
    1 segundo real = 1 "tick" de simulação
    """
    print("Simulador iniciado. Gravando em stream/live_readings.jsonl")
    print(f"Total de ativos configurados: {len(ASSETS)}")
    print("Pressione Ctrl + C para encerrar.\n")

    minute_counter = 0

    try:
        while True:
            minute_of_day = minute_counter % 1440

            for asset in ASSETS:
                reading = generate_reading(asset, minute_of_day)
                append_reading_to_stream(reading)
                print_reading_summary(reading)

            minute_counter += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nSimulador encerrado manualmente.")


if __name__ == "__main__":
    main()