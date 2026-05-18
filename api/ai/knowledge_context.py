from __future__ import annotations


OPERATIONAL_RULES = [
    "OFFLINE sugere verificar comunicacao, sinal, alimentacao e conexao do equipamento.",
    "Alta temperatura sugere verificar porta aberta, carga termica, sensor, degelo, ventilacao e refrigeracao.",
    "Baixa temperatura sugere verificar setpoint, sensor, controle e configuracao.",
    "Compressor em alarme deve ser analisado com historico, carga termica, comando eletrico e protecoes antes de concluir defeito.",
    "Camara fria com desvio de temperatura deve ser validada contra porta aberta, degelo, ventilacao, sensor e carga de produto.",
    "Rack ou sistema com recorrencia deve ser priorizado por impacto em multiplos equipamentos.",
    "Pressao ou glicol fora do esperado exige validacao de sensor, bomba, fluido e troca termica.",
    "Telemetria vazia nao confirma falha; apenas indica falta de evidencia.",
    "Criticidade A/C deve ser tratada como alta prioridade.",
    "Criticidade M deve ser tratada como warning.",
    "Loja com muitos alarmes deve ser priorizada.",
    "Dispositivo com repeticao de alarme exige atencao operacional.",
    "Se nao houver dados recentes, recomendar nova coleta ou validacao.",
]


def rules_for_terms(text: str) -> list[str]:
    normalized = text.casefold()
    selected: list[str] = []

    if "offline" in normalized:
        selected.append(OPERATIONAL_RULES[0])
    if any(term in normalized for term in ("alta temperatura", "temperatura alta", "quente", "camara", "câmara")):
        selected.append(OPERATIONAL_RULES[1])
    if any(term in normalized for term in ("baixa temperatura", "temperatura baixa", "frio demais")):
        selected.append(OPERATIONAL_RULES[2])
    if "compressor" in normalized:
        selected.append(OPERATIONAL_RULES[3])
    if any(term in normalized for term in ("camara", "câmara", "congelado", "resfriado")):
        selected.append(OPERATIONAL_RULES[4])
    if "rack" in normalized:
        selected.append(OPERATIONAL_RULES[5])
    if any(term in normalized for term in ("pressao", "pressão", "glicol")):
        selected.append(OPERATIONAL_RULES[6])
    if any(term in normalized for term in ("telemetria", "leitura", "temperatura", "sensor")):
        selected.append(OPERATIONAL_RULES[7])
    if any(term in normalized for term in ("criticidade a", "criticidade c", "critico", "crítico")):
        selected.append(OPERATIONAL_RULES[8])
    if "criticidade m" in normalized:
        selected.append(OPERATIONAL_RULES[9])
    if "loja" in normalized:
        selected.append(OPERATIONAL_RULES[10])
    if any(term in normalized for term in ("repeticao", "repetição", "recorrente", "reincidente")):
        selected.append(OPERATIONAL_RULES[11])

    selected.append(OPERATIONAL_RULES[12])
    return list(dict.fromkeys(selected))
