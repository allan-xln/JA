# Levantamento Técnico E Comercial - Eletrofrio/JA

Este levantamento reúne os principais custos e uma faixa comercial realista para conversar com a Eletrofrio. A proposta continua abaixo do mercado, porque o projeto nasceu de uma oportunidade acadêmica, mas já considera que existe uma operação real para manter: painel, dados reais, automação, IA, WhatsApp, deploy e suporte.

## Resumo Executivo

| Item | Recomendação |
|---|---:|
| Custo mensal técnico baixo | R$ 45 a R$ 305 |
| Custo mensal técnico realista | R$ 365 a R$ 890 |
| IA econômica para Eletrofrio | R$ 10 a R$ 30/mês |
| IA agressiva/controlada | R$ 50 a R$ 120/mês |
| VPS mínima aceitável | 2 vCPU / 4 GB RAM |
| VPS ideal sem exagero | 4 vCPU / 8 GB RAM |
| Supabase recomendado | Pro quando telemetria crescer |
| Piloto pago recomendado | R$ 7.000 a R$ 10.000 por 90 dias |
| Entrada mínima definitiva | R$ 15.000 |
| Entrada recomendada | R$ 25.000 a R$ 30.000 |
| Mensalidade mínima | R$ 1.000/mês |
| Mensalidade recomendada | R$ 1.800/mês |
| Melhor proposta de oportunidade | R$ 25.000 + R$ 1.800/mês por 12 meses |

## 1. Uso Atual Do Sistema

Dados usados como base do ambiente atual:

| Métrica | Valor aproximado |
|---|---:|
| Lojas/unidades cadastradas | 319 |
| Dispositivos monitorados | 418 |
| Alarmes históricos | 1.136 |
| Telemetrias históricas | 406.705 |
| Insights operacionais | 743 |
| Anomalias | 433 |
| Runs do collector | 50 |
| Logs de comunicação | 96.887 |
| Consultas RAG registradas | 7 |
| Mensagens WhatsApp registradas | 11 |
| Clientes/tenants cadastrados | 93 |

Média por coleta real observada:

| Item | Média aproximada |
|---|---:|
| Unidades por coleta | 311 a 314 |
| Alarmes por coleta | 57 a 87 |
| Telemetrias por coleta | 28 mil a 46 mil |
| Anomalias por coleta | 14 a 80 |
| Média realista de anomalias | 30 por coleta |

## 2. Cenários De Uso

| Cenário | Coletas | Telemetrias/mês | Anomalias relevantes/dia | Mensagens/dia | RAG/dia |
|---|---:|---:|---:|---:|---:|
| Conservador | 2/dia | 2M a 4M | 3 a 8 | 3 a 10 | 2 a 5 |
| Realista | 4 a 8/dia | 4M a 15M | 8 a 25 | 10 a 40 | 5 a 12 |
| Alto uso | parcial a cada 5/15 min | 20M a 45M | 25 a 80 | 40 a 150 | 20 a 40 |

Partes mais pesadas:

| Área | Impacto |
|---|---|
| Collector de telemetria | maior volume de banco e rede |
| Dashboard de ativos/telemetria | pode pesar se consultar dados brutos demais |
| Scheduler | baixo consumo, mas recorrente |
| WhatsApp/Baileys | RAM moderada e risco de sessão |
| RAG/IA | custo baixo se usado com limite |
| Logs de comunicação | crescimento silencioso no banco |

## 3. Custo De IA - Eletrofrio

Premissas:

- IA não deve analisar tudo.
- Templates e regras locais devem resolver a maior parte dos alertas.
- IA deve entrar para explicação, resumo, RAG e casos críticos.
- Modelo barato/intermediário por padrão.
- Modelo forte só em exceções.

Uso econômico recomendado:

| Uso | Chamadas/dia | Tokens por chamada | Custo mensal estimado |
|---|---:|---:|---:|
| RAG manual | 6 | 2.500 entrada / 700 saída | R$ 5 |
| Alertas com IA | 2 | 1.200 entrada / 350 saída | R$ 1 |
| Resumo diário | 1 | 3.500 entrada / 900 saída | R$ 2 |
| Resumo semanal | 4/mês | 7.000 entrada / 1.200 saída | R$ 1 |
| Reserva e variação | - | - | R$ 10 a R$ 20 |
| Total econômico | - | - | **R$ 10 a R$ 30/mês** |

Uso agressivo, ainda controlado:

| Uso | Chamadas/dia | Tokens por chamada | Custo mensal estimado |
|---|---:|---:|---:|
| RAG intenso | 30 | 3.500 / 900 | R$ 30 a R$ 40 |
| Alertas enriquecidos | 15 | 1.500 / 450 | R$ 5 a R$ 15 |
| Resumos por coleta | 12 | 3.000 / 800 | R$ 10 a R$ 20 |
| Classificação IA | 80 | 700 / 120 | R$ 5 a R$ 15 |
| Total agressivo | - | - | **R$ 50 a R$ 120/mês** |

Uso ruim, não recomendado:

| Uso | Resultado |
|---|---|
| Enviar toda telemetria para IA | aumenta custo, latência e risco de resposta ruim |
| Gerar IA para toda anomalia | desperdiça token em evento repetido |
| Fazer resumo completo por dispositivo | pouco valor prático |

Conclusão: **IA não é o maior custo do projeto**. O maior custo é suporte, manutenção, banco, retenção e responsabilidade operacional.

## 4. Custo De IA Por Cliente/Tenant

| Cliente | Perfil | Custo IA/mês | Cobrança sugerida embutida |
|---|---|---:|---:|
| Pequeno | poucas lojas e poucos alertas | R$ 2 a R$ 10 | R$ 20 a R$ 50 |
| Médio | uso diário realista | R$ 10 a R$ 40 | R$ 50 a R$ 150 |
| Grande | muitas lojas, alertas e consultas | R$ 40 a R$ 150 | R$ 150 a R$ 500 |

Limites sugeridos:

| Plano | RAG/mês | Alertas IA/mês | Observação |
|---|---:|---:|---|
| Básico | 100 | 100 | foco em template local |
| Profissional | 500 | 500 | IA em alertas importantes |
| Empresa | 1.500 | 2.000 | limites negociados |

## 5. VPS / Infraestrutura

| Opção | Custo aproximado | Uso recomendado |
|---|---:|---|
| Oracle Always Free | R$ 0 | demo/piloto, com risco |
| VPS 2 vCPU / 4 GB | R$ 25 a R$ 130/mês | mínimo pago aceitável |
| VPS 4 vCPU / 8 GB | R$ 40 a R$ 250/mês | ideal sem exagero |
| VPS 4/8 vCPU / 16 GB | R$ 100 a R$ 500+/mês | multi-cliente ou alto uso |

Situação atual observada:

- VPS atual roda, mas é apertada.
- 1 GB de RAM usa swap e deixa build/deploy lento.
- Para vender comercialmente, o ideal é 4 vCPU / 8 GB.

Recomendação:

| Fase | VPS |
|---|---|
| Piloto | Oracle Free ou 2 vCPU / 4 GB |
| Eletrofrio produção | 4 vCPU / 8 GB |
| SaaS até 5 clientes | 4 vCPU / 8 GB |
| SaaS 20 clientes | 8 vCPU / 16 GB ou separar workers |
| SaaS 50 clientes | separar frontend, API, workers, logs e banco |

## 6. Supabase / Banco / Storage

O Supabase é onde o custo pode crescer se a telemetria bruta ficar acumulando sem retenção.

Estimativa de crescimento:

| Cenário | Telemetrias/mês | Volume estimado |
|---|---:|---:|
| Conservador | 2M a 4M | 2 GB a 5 GB/mês |
| Realista | 4M a 15M | 5 GB a 20 GB/mês |
| Alto uso | 20M a 45M | 25 GB a 50 GB/mês |

Política de retenção recomendada:

| Dado | Retenção |
|---|---|
| Telemetria bruta | 30 a 60 dias |
| Agregados horários/diários | 12 a 24 meses |
| Alarmes | 12 a 24 meses |
| Insights/anomalias | 12 a 24 meses |
| Logs de notificação | 90 a 180 dias |
| Logs técnicos | 14 a 30 dias |
| Arquivo frio | CSV/Parquet mensal fora do banco |

## 7. WhatsApp / Mensagens

| Item | Situação |
|---|---|
| Baileys | sem custo direto de API |
| Custo real | manutenção, QR, reconexão e risco operacional |
| Risco | sessão cair, bloqueio, instabilidade do WhatsApp Web |
| API oficial | melhor para SLA, mas com custo variável por provedor/região |

Recomendação:

- Piloto: Baileys é suficiente.
- Contrato comercial: cobrar manutenção mensal.
- Enterprise/SLA: prever migração futura para API oficial.

## 8. Custo Total Mensal

| Cenário | Infra | Banco | IA | Backup/monitoramento | Total direto |
|---|---:|---:|---:|---:|---:|
| Demo/piloto | R$ 0 a R$ 50 | R$ 0 a R$ 130 | R$ 10 a R$ 30 | R$ 30 a R$ 80 | **R$ 40 a R$ 290** |
| Produção Eletrofrio baixo custo | R$ 50 a R$ 130 | R$ 130 | R$ 10 a R$ 50 | R$ 50 a R$ 100 | **R$ 240 a R$ 410** |
| Produção Eletrofrio confortável | R$ 130 a R$ 250 | R$ 130 a R$ 300 | R$ 50 a R$ 120 | R$ 100 a R$ 200 | **R$ 410 a R$ 870** |
| SaaS 5 clientes | R$ 130 a R$ 250 | R$ 130 a R$ 500 | R$ 50 a R$ 250 | R$ 100 a R$ 250 | **R$ 410 a R$ 1.250** |
| SaaS 20 clientes | R$ 250 a R$ 500 | R$ 400 a R$ 1.500 | R$ 100 a R$ 900 | R$ 250 a R$ 600 | **R$ 1.000 a R$ 3.500** |

Esses valores são custo técnico direto. Não incluem tempo de suporte, responsabilidade, reunião, correção e evolução.

## 9. Preço Comercial Abaixo Do Mercado

Faixa comercial pensada para uma primeira negociação:

| Faixa | Valor |
|---|---:|
| Simbólico demais | R$ 7.000 a R$ 12.000 |
| Oportunidade acadêmica | R$ 15.000 a R$ 25.000 |
| Recomendado para fechar barato | R$ 25.000 a R$ 35.000 |
| Justo abaixo do mercado | R$ 40.000 a R$ 60.000 |
| Mercado normal | R$ 100.000 a R$ 180.000+ |

Valores finais sugeridos:

| Item | Valor |
|---|---:|
| Piloto pago 90 dias | R$ 7.000 a R$ 10.000 |
| Entrada mínima definitiva | R$ 15.000 |
| Entrada recomendada | R$ 25.000 a R$ 30.000 |
| Setup/treinamento | R$ 2.500 a R$ 3.500 |
| Mensalidade mínima | R$ 1.000/mês |
| Mensalidade recomendada | R$ 1.800/mês |
| Mensalidade com evolução | R$ 2.500 a R$ 3.200/mês |
| Hora extra | R$ 80 a R$ 130/h |

## 10. Modelos De Cobrança

| Modelo | Preço sugerido | Quando usar |
|---|---:|---|
| Piloto pago | R$ 7.000 a R$ 10.000 por 90 dias | melhor para abrir relação |
| Entrada baixa + mensalidade | R$ 10.000 a R$ 12.000 + R$ 2.500/mês | quando o cliente trava no inicial |
| Contrato de oportunidade | R$ 25.000 + R$ 1.800/mês | melhor equilíbrio |
| Licença anual simples | R$ 40.000 a R$ 55.000/ano | se preferirem orçamento anual |
| SaaS por plano | R$ 249 a R$ 3.500/mês | produto multi-cliente futuro |

Melhor proposta para apresentar agora:

> R$ 7.000 a R$ 10.000 por 90 dias de piloto. Se fizer sentido para a operação, converter para R$ 1.800/mês.

Melhor proposta definitiva:

> R$ 25.000 de entrada + R$ 1.800/mês por 12 meses.

## 11. Planos SaaS Futuros

| Plano | Valor | Inclui |
|---|---:|---|
| Básico | R$ 249 a R$ 449/mês | poucas lojas, alertas simples, painel |
| Profissional | R$ 699 a R$ 1.190/mês | mais lojas, IA/RAG, WhatsApp, relatórios |
| Empresa | R$ 1.800 a R$ 3.500/mês | multiunidade, prioridade, operação assistida |
| Enterprise | sob proposta | SLA, customizações e API oficial WhatsApp |

## 12. ROI E Valor Operacional

Pontos para defender o preço:

| Valor entregue | Como explicar |
|---|---|
| Redução de tempo de análise | menos tempo olhando dado bruto |
| Alertas preventivos | reação antes de falha grave |
| Histórico e auditoria | evidência de recorrência e decisão |
| WhatsApp ativo | alerta chega onde a equipe já está |
| Priorização | separa ruído de ocorrência importante |
| Menos risco de perda de produto | refrigeração ruim pode gerar prejuízo alto |
| Centralização | menos planilha e menos dependência manual |

Frase comercial:

> O preço inicial fica abaixo do que esse tipo de sistema custaria no mercado porque o projeto nasceu de uma oportunidade acadêmica. A mensalidade é o que mantém a operação acompanhada, com suporte e pequenos ajustes sem transformar a entrega em trabalho gratuito.

## 13. Riscos E Cuidados

| Risco | Cuidado |
|---|---|
| Supabase crescer rápido | retenção e agregados |
| WhatsApp cair | QR, reconexão e fallback |
| Cliente pedir evolução infinita | separar suporte de customização |
| IA gastar demais | limites por dia/tenant |
| VPS free instável | migrar quando virar contrato |
| Alertas demais | cooldown, severidade e deduplicação |

## 14. Recomendação Final Direta

| Decisão | Valor recomendado |
|---|---:|
| Para começar sem assustar | R$ 7.000 a R$ 10.000 por 90 dias |
| Para contrato definitivo barato | R$ 25.000 + R$ 1.800/mês |
| Para não tomar prejuízo | não baixar de R$ 15.000 definitivo |
| Mensalidade mínima aceitável | R$ 1.000/mês |
| Mensalidade saudável | R$ 1.800/mês |
| VPS ideal | 4 vCPU / 8 GB |
| Custo técnico mensal realista | R$ 365 a R$ 890 |
| Custo de IA realista | R$ 10 a R$ 120/mês |
