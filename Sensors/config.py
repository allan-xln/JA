from dataclasses import dataclass
from typing import Optional


@dataclass
class AssetConfig:
    store_id: str
    asset_type: str           # exhibitor | cold_room | machine_room
    asset_id: str
    module_id: str
    sector: str
    temp_setpoint_c: Optional[float] = None
    temp_noise: float = 0.2
    current_base_a: Optional[float] = None
    pressure_base_bar: Optional[float] = None
    external_temp_base_c: Optional[float] = None
    humidity_base_pct: Optional[float] = None


ASSETS = [
    # EXPOSTORES / MÓDULOS
    AssetConfig(
        store_id="01",
        asset_type="exhibitor",
        asset_id="ACO-VPHRL-01",
        module_id="01",
        sector="acougue",
        temp_setpoint_c=2.0,
        temp_noise=0.25,
        humidity_base_pct=88.0,
    ),
    AssetConfig(
        store_id="01",
        asset_type="exhibitor",
        asset_id="PEX-VPHRL-01",
        module_id="01",
        sector="peixaria",
        temp_setpoint_c=1.0,
        temp_noise=0.20,
        humidity_base_pct=92.0,
    ),
    AssetConfig(
        store_id="01",
        asset_type="exhibitor",
        asset_id="HFT-EVH6-01",
        module_id="01",
        sector="hortifruti",
        temp_setpoint_c=5.0,
        temp_noise=0.35,
        humidity_base_pct=90.0,
    ),
    AssetConfig(
        store_id="01",
        asset_type="exhibitor",
        asset_id="LAT-VIT-01",
        module_id="01",
        sector="laticinios",
        temp_setpoint_c=4.0,
        temp_noise=0.25,
    ),
    AssetConfig(
        store_id="01",
        asset_type="exhibitor",
        asset_id="CON-ILH-01",
        module_id="01",
        sector="congelados",
        temp_setpoint_c=-18.0,
        temp_noise=0.60,
    ),

    # CÂMARAS
    AssetConfig(
        store_id="01",
        asset_type="cold_room",
        asset_id="CAM-RES-01",
        module_id="01",
        sector="camara_resfriada",
        temp_setpoint_c=2.0,
        temp_noise=0.20,
    ),
    AssetConfig(
        store_id="01",
        asset_type="cold_room",
        asset_id="CAM-CON-01",
        module_id="01",
        sector="camara_congelada",
        temp_setpoint_c=-20.0,
        temp_noise=0.50,
    ),

    # CASA DE MÁQUINAS
    AssetConfig(
        store_id="01",
        asset_type="machine_room",
        asset_id="CM-01",
        module_id="01",
        sector="casa_maquinas",
        current_base_a=42.0,
        pressure_base_bar=16.0,
        external_temp_base_c=29.0,
    ),
]