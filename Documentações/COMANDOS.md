# Comandos Úteis - Eletrofrio AI

## Ambiente

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
```

## Apresentação Rápida

Subir tudo e ver containers:

```bash
make demo-up
```

Validar API, overview, collector, WhatsApp e endereço do frontend:

```bash
make demo-check
```

Executar uma coleta manual:

```bash
make demo-collector
```

Enviar o resumo operacional para WhatsApp:

```bash
make demo-whatsapp-summary
```

Ver logs da apresentação:

```bash
make demo-logs
```

## Backend

Rodar API:

```bash
uvicorn api.main:app --reload
```

Health:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
```

Overview:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/overview
```

Unidades:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/units
```

Dispositivos:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/devices
```

Alarmes:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/alarms
```

Telemetria:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/telemetry
```

Insights:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/insights
```

## Collector E Scheduler

Rodar coleta manual:

```bash
python -m api.collector
```

Rodar scheduler:

```bash
python -m api.scheduler
```

Executar coleta via API:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/run-collector
```

Status da automação:

```bash
curl http://127.0.0.1:8000/api/collector/status
```

Histórico de execuções:

```bash
curl http://127.0.0.1:8000/api/collector/runs?limit=10
```

Salvar configuração:

```bash
curl -X PUT http://127.0.0.1:8000/api/collector/settings \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"intervalMinutes":5,"alertCooldownMinutes":60}'
```

Rodar coleta agora:

```bash
curl -X POST http://127.0.0.1:8000/api/collector/run-now
```

Anomalias abertas:

```bash
curl 'http://127.0.0.1:8000/api/collector/anomalies?limit=10&status=open'
```

Timeouts da API Eletrofrio:

```env
ELETROFRIO_TIMEOUT_SECONDS=20
ELETROFRIO_RETRY_ATTEMPTS=1
```

Se `unidades` ou `alarmes` estiverem temporariamente indisponíveis, o coletor usa o último snapshot salvo no Supabase e registra a execução como `partial_success`.

Manter automação desligada durante apresentação:

```bash
curl -X PUT http://127.0.0.1:8000/api/collector/settings \
  -H "Content-Type: application/json" \
  -d '{"enabled":false,"intervalMinutes":5,"alertCooldownMinutes":60}'
```

Processar fila operacional para WhatsApp:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

## Ocorrencias Operacionais

Listar ocorrencias priorizadas:

```bash
curl 'http://127.0.0.1:8000/api/eletrofrio/anomalies?status=active&limit=20'
```

Buscar por codigo publico:

```bash
curl 'http://127.0.0.1:8000/api/eletrofrio/anomalies/search?code=OC-20260622-0001'
```

Abrir detalhe de uma ocorrencia:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA
```

Gerar sugestao de correcao:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/suggest-solution
```

Enviar sugestao por WhatsApp:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/send-whatsapp
```

Resolver, reabrir, adicionar observacao e abrir chamado:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/resolve
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/reopen
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/notes \
  -H "Content-Type: application/json" \
  -d '{"note":"Tecnico acionado."}'
curl -X POST http://127.0.0.1:8000/api/eletrofrio/anomalies/ID_DA_OCORRENCIA/ticket
```

No painel, a tela Ocorrencias mostra o codigo publico, abre o modal operacional
por clique no card e permite pesquisar por `OC-AAAAMMDD-NNNN`.

## Retencao / Plano Free

Aplicar as migrations na ordem normal:

```text
001, 002_collector_runtime_schema, 003, 004, 005, 006, 007, 008, 009
```

Limpeza curta para Supabase no plano free:

```text
sql/011_free_plan_retention_cleanup.sql
```

Esse SQL preserva usuarios, clientes, regras, destinatarios, auth e sessao do
WhatsApp. Ele apaga dados operacionais antigos em lote. Se algum notice voltar
com `15000` linhas apagadas, rode o 011 novamente ate diminuir.

Depois de uma limpeza grande, se o Supabase aceitar, rode separadamente:

```sql
vacuum analyze public.eletrofrio_telemetry;
vacuum analyze public.eletrofrio_alarms;
vacuum analyze public.eletrofrio_anomalies;
vacuum analyze public.eletrofrio_ai_insights;
vacuum analyze public.eletrofrio_notification_events;
```

## Motor de Regras Operacionais

```bash
curl http://127.0.0.1:8000/api/eletrofrio/rules
curl http://127.0.0.1:8000/api/eletrofrio/rules/defaults/preview
curl -X POST http://127.0.0.1:8000/api/eletrofrio/rules/defaults/apply
curl -X POST http://127.0.0.1:8000/api/eletrofrio/rules/evaluate
curl http://127.0.0.1:8000/api/eletrofrio/rule-evaluations
```

Se aparecer a mensagem de schema pendente, abra o Supabase SQL Editor e execute:

```text
sql/003_operational_rules.sql
```

A tela Centro Operacional mostra o snapshot consolidado do Supabase, o diagnóstico operacional e a fila de comunicação. Ela filtra tentativas automáticas sem dados para não poluir a apresentação.

## Frontend

Rodar localmente:

```bash
cd /caminho/onde/voce/clonou/JA/Frontend/JA-IA-ELETROFRIO
npm run dev
```

Typecheck:

```bash
npm run typecheck
```

Build:

```bash
npm run build
```

Abrir:

```text
http://localhost:3000
```

## WhatsApp

Rodar serviço:

```bash
cd /caminho/onde/voce/clonou/JA/whatsapp
npm run dev
```

Status direto:

```bash
curl http://127.0.0.1:8091/status
```

Status via API:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
```

Iniciar conexão:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start
```

Buscar QR Code:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/qr
```

Encerrar sessão:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/logout
```

Enviar teste:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/send-test \
  -H "Content-Type: application/json" \
  -d '{"phone":"5541999999999","message":"Teste operacional Eletrofrio."}'
```

Processar insights pendentes:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

Conectar por QR:

1. Suba o serviço WhatsApp.
2. Chame `/api/eletrofrio/whatsapp/start`.
3. Abra `/api/eletrofrio/whatsapp/qr`.
4. Escaneie o QR Code pelo WhatsApp.
5. Valide `connected=true` no status.

Testar modo seguro sem envio real:

```env
WHATSAPP_ENABLED=true
WHATSAPP_DRY_RUN=true
WHATSAPP_ALLOWED_RECIPIENTS=5541999999999
```

O retorno de `/process-insights` informa:

- `total_analyzed`;
- `total_eligible`;
- `total_sent`;
- `total_ignored`;
- `ignore_reasons`;
- `dry_run`;
- `simulated_messages`.

Observação: se `WHATSAPP_ALLOWED_RECIPIENTS` estiver vazio, o serviço usa o número conectado na sessão como destino de demonstração. Para produção, configure destinatários explicitamente:

```env
WHATSAPP_ALLOWED_RECIPIENTS=5541999999999
```

Perguntas boas para demonstrar pelo próprio WhatsApp:

```text
Me dá um resumo da operação
Como está a loja Sítio Cercado?
Quais equipamentos estão críticos?
Quais equipamentos estão offline?
Teve alguma anomalia hoje?
```

Na apresentação, explique que o WhatsApp não é um chat genérico: ele é o canal operacional da equipe. A mensagem entra pelo WhatsApp, o backend consulta Supabase, alarmes, telemetria e insights, e a resposta volta curta, com evidência e recomendação.

## Diagnóstico Operacional

Resumo da operação:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Me dá um resumo da operação agora"}'
```

Status de loja:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Como está a loja Sítio Cercado?"}'
```

Equipamentos offline:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Quais equipamentos estão offline?"}'
```

Sugestões:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/assistant/suggestions
```

## Docker

Preparar `.env`:

```bash
cd /caminho/onde/voce/clonou/JA
cp .env.docker.example .env
nano .env
```

Subir tudo:

```bash
docker compose up --build
```

Subir em background:

```bash
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f
```

Logs da API:

```bash
docker compose logs -f api
```

Logs do WhatsApp:

```bash
docker compose logs -f whatsapp
```

Rodar collector manual no container:

```bash
docker compose exec api python -m api.collector
```

Entrar no shell da API:

```bash
docker compose exec api bash
```

Parar:

```bash
docker compose down
```

Limpar volumes:

```bash
docker compose down -v
```

Atenção: esse comando apaga volumes locais, incluindo a sessão persistida do WhatsApp.

## Atualizar Schema Supabase

Use estes comandos quando aparecerem erros como tabela ausente no schema cache, coluna `trigger_source` ausente ou anomalias indisponíveis.

Instalação nova:

```text
1. Abrir Supabase > SQL Editor.
2. Copiar e executar o conteúdo de sql/001_initial_schema.sql.
3. Copiar e executar o conteúdo de sql/002_collector_runtime_schema.sql.
4. Reiniciar os containers.
```

Correção de ambiente existente:

```text
1. Abrir Supabase > SQL Editor.
2. Copiar e executar somente o conteúdo de sql/002_collector_runtime_schema.sql.
3. Reiniciar os containers.
```

Abrir a migration localmente:

```bash
cd /caminho/onde/voce/clonou/JA
sed -n '1,260p' sql/002_collector_runtime_schema.sql
```

Reiniciar após aplicar o SQL:

```bash
docker compose up -d --build
docker compose ps
```

Validar schema em uso:

```bash
curl http://127.0.0.1:8000/api/collector/status
curl "http://127.0.0.1:8000/api/collector/runs?limit=5"
curl "http://127.0.0.1:8000/api/collector/anomalies?limit=5&status=open"
```

## Validações Rápidas

Backend:

```bash
python -m compileall api
```

WhatsApp:

```bash
cd whatsapp
npm run typecheck
npm run build
```

Frontend:

```bash
cd Frontend/JA-IA-ELETROFRIO
npm run typecheck
npm run build
```

Docker:

```bash
docker compose config
docker compose build
```
