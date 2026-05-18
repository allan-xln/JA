# Checklist De Validação - Eletrofrio AI

Use esta lista após atualizar o schema do Supabase ou reiniciar o ambiente Docker.

## Supabase

- [ ] Abrir Supabase > SQL Editor.
- [ ] Em instalação nova, executar `sql/001_initial_schema.sql`.
- [ ] Executar `sql/002_collector_runtime_schema.sql`.
- [ ] Confirmar que existem as tabelas `eletrofrio_collector_settings`, `eletrofrio_anomalies` e `eletrofrio_collector_runs`.
- [ ] Confirmar que `eletrofrio_collector_runs` possui a coluna `trigger_source`.
- [ ] Confirmar que `eletrofrio_collector_runs` possui a coluna `anomalies_count`.

## Docker

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA
docker compose up -d --build
docker compose ps
```

- [ ] `ja-api-1` está `healthy`.
- [ ] `ja-frontend-1` está `healthy` ou `Up`.
- [ ] `ja-scheduler-1` está `Up`.
- [ ] `ja-whatsapp-1` está `healthy` ou `Up`.

## Backend

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
curl http://127.0.0.1:8000/api/eletrofrio/overview
curl http://127.0.0.1:8000/api/eletrofrio/insights
curl http://127.0.0.1:8000/api/collector/status
curl "http://127.0.0.1:8000/api/collector/runs?limit=5"
curl "http://127.0.0.1:8000/api/collector/anomalies?limit=5&status=open"
```

- [ ] Health retorna `200 OK`.
- [ ] Overview retorna dados reais.
- [ ] Insights retorna lista ou estado vazio controlado.
- [ ] Collector status retorna configurações operacionais.
- [ ] Runs retorna histórico sem erro de coluna ausente.
- [ ] Anomalies retorna lista ou estado vazio sem erro de tabela ausente.

## WhatsApp

```bash
curl http://127.0.0.1:8091/status
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
```

- [ ] Serviço WhatsApp responde.
- [ ] Backend enxerga o serviço WhatsApp.
- [ ] QR Code aparece quando a sessão ainda não está conectada.
- [ ] Perguntas operacionais pelo WhatsApp recebem resposta baseada nos dados.

## Frontend

- [ ] Abrir `http://localhost:3000`.
- [ ] Visão geral carrega.
- [ ] Ativos monitorados carrega.
- [ ] Ocorrências carrega.
- [ ] Rotina operacional mostra status do collector.
- [ ] Comunicação WhatsApp mostra estado do canal.

## Logs

```bash
docker compose logs -f api
docker compose logs -f scheduler
docker compose logs -f whatsapp
```

- [ ] Não há erro de tabela `eletrofrio_collector_settings` ausente.
- [ ] Não há erro de tabela `eletrofrio_anomalies` ausente.
- [ ] Não há erro de coluna `trigger_source` ausente.
- [ ] Logs de telemetria vazia aparecem de forma curta, sem payload bruto gigante.
