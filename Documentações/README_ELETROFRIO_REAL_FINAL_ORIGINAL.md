# Eletrofrio IA - Projeto Real

## Visao Geral

Este projeto evolui o piloto academico da Eletrofrio para uma base real de monitoramento inteligente de refrigeracao.

O sistema coleta dados oficiais da Eletrofrio, salva os dados brutos no Supabase, calcula metricas operacionais, gera insights por regras/estatistica e usa GPT/OpenAI apenas para explicar evidencias ja estruturadas. O WhatsApp e um servico isolado, criado dentro deste projeto, para enviar alertas inteligentes sem depender do LanChat em runtime.

O piloto antigo com simulador, JSONL e dashboard legado foi preservado.

## Arquitetura

```text
Endpoints oficiais Eletrofrio
  -> Coletor FastAPI/Python
  -> Normalizacao segura
  -> Supabase: dados brutos
  -> Motor de metricas/regras
  -> GPT controlado por evidence_json
  -> Supabase: insights
  -> API interna /api/eletrofrio/*
  -> Dashboard Next.js
  -> Servico WhatsApp Baileys isolado
```

## Fluxo De Dados

1. `api.collector` busca unidades, alarmes e telemetria.
2. Dados sao normalizados sem descartar `raw_payload`.
3. Registros sao gravados no Supabase com deduplicacao.
4. `api.analysis` calcula metricas e severidade por regras.
5. `api.ai.openai_analyzer` usa GPT somente para texto explicativo controlado.
6. `api.decision.alert_engine` salva insights.
7. `whatsapp/` envia insights pendentes quando permitido.

## Endpoints Oficiais Usados

Base:

```env
ELETROFRIO_API_BASE_URL=https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon
```

Rotas:

- `route=alarmes`
- `route=unidades`
- `route=telemetria&dispositivoId=ID_DO_DISPOSITIVO`
- `route=abrir-chamado`

Endpoints antigos/bugados devem ser ignorados.

## Tabelas Supabase

Rode no SQL editor:

```text
sql/001_initial_schema.sql
```

Tabelas:

- `eletrofrio_units`
- `eletrofrio_devices`
- `eletrofrio_alarms`
- `eletrofrio_telemetry`
- `eletrofrio_ai_insights`
- `eletrofrio_collector_runs`

Deduplicacao:

- unidades por `loja_id`
- dispositivos por `dispositivo_id`
- alarmes por `external_hash`
- telemetria por `external_hash`
- insights por `insight_hash`

Todos os payloads originais ficam em `raw_payload`.

## Variaveis De Ambiente

Crie:

```bash
cp .env.example .env
```

Preencha:

```env
ELETROFRIO_API_BASE_URL=https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon
ELETROFRIO_TEAM_NAME=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
COLLECTOR_INTERVAL_MINUTES=5
AUTO_OPEN_TICKETS=false
WHATSAPP_ENABLED=false
WHATSAPP_DRY_RUN=true
WHATSAPP_SESSION_DIR=./whatsapp/sessions/eletrofrio
WHATSAPP_DEFAULT_COUNTRY_CODE=55
WHATSAPP_ALLOWED_RECIPIENTS=
WHATSAPP_MIN_INTERVAL_MINUTES_PER_DEVICE=30
WHATSAPP_MIN_INTERVAL_MINUTES_PER_STORE=60
WHATSAPP_SERVICE_PORT=8091
WHATSAPP_SERVICE_URL=http://127.0.0.1:8091
HTTP_TIMEOUT_SECONDS=30
```

Nao coloque keys reais no repositorio.

## Configurar Supabase

1. Crie um projeto no Supabase.
2. Copie `SUPABASE_URL`.
3. Copie `SUPABASE_SERVICE_ROLE_KEY`.
4. Rode `sql/001_initial_schema.sql`.
5. Coloque as credenciais no `.env` da raiz de `ELETROFRIO/JA`.

A service role deve ficar somente no backend/servicos locais, nunca no frontend.

## Configurar OpenAI

No `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

O prompt interno obriga:

> Voce e um assistente tecnico de monitoramento de refrigeracao. Responda somente com base nos dados fornecidos. Se faltar evidencia, diga que nao ha dados suficientes. Nao invente valores, nomes, sensores, lojas, alarmes ou diagnosticos.

Se a key nao estiver configurada, o sistema usa fallback por regras.

## IA Consultiva / RAG Operacional

Endpoint:

```http
POST /api/eletrofrio/assistant/ask
```

Compatibilidade: `POST /api/eletrofrio/assistant/query` continua funcionando como alias.

Payload:

```json
{
  "question": "Quais equipamentos exigem atencao agora?"
}
```

A consulta recupera contexto real do Supabase:

- unidades;
- dispositivos;
- alarmes recentes;
- telemetria recente;
- insights recentes;
- agregacoes de severidade, tipo de alarme e lojas com maior volume.

Com `OPENAI_API_KEY` configurada, o backend chama `OPENAI_MODEL` e responde apenas com base no contexto recuperado. Sem key, retorna fallback controlado por regras e deixa claro que a resposta nao veio do GPT.

## Configurar WhatsApp

O WhatsApp fica em:

```text
whatsapp/
```

Instale:

```bash
cd whatsapp
npm install
```

Ative no `.env`:

```env
WHATSAPP_ENABLED=true
WHATSAPP_DRY_RUN=true
WHATSAPP_ALLOWED_RECIPIENTS=5541999999999
```

Rodar:

```bash
cd whatsapp
npm run dev
```

Com `WHATSAPP_ENABLED=true`, o QR Code aparece no terminal.

Sessao:

```text
whatsapp/sessions/eletrofrio
```

Essa pasta e ignorada pelo Git.

## Rodar Backend/API

Instalar ambiente:

```bash
conda env create -f environment.yml
conda activate eletrofrio-ai
```

Rodar API:

```bash
uvicorn api.main:app --reload
```

## Rodar Collector Manual

```bash
python -m api.collector
```

## Rodar Collector Em Loop

Roda a cada `COLLECTOR_INTERVAL_MINUTES`:

```bash
python -m api.scheduler
```

## Rodar Com Docker

Crie `.env` a partir de `.env.example` e preencha as credenciais localmente, sem versionar keys reais:

```bash
cp .env.example .env
```

Subir tudo:

```bash
docker compose up --build
```

Servicos expostos:

- Backend/API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`
- WhatsApp: `http://127.0.0.1:8091`

No Docker, a API sobe com `ELETROFRIO_START_INTERNAL_SCHEDULER=false` e o container `scheduler` executa `python -m api.scheduler`, evitando duas coletas concorrentes. Fora do Docker, o padrao continua `true`, mantendo o comportamento atual do backend local.

## Rodar Frontend

```bash
cd Frontend/JA-IA-ELETROFRIO
npm install
npm run dev
```

O frontend atual ainda consome o endpoint legado `/api/dashboard`, baseado no JSONL do piloto. Proxima etapa: apontar o dashboard para `/api/eletrofrio/overview`, `/api/eletrofrio/alarms`, `/api/eletrofrio/telemetry`, `/api/eletrofrio/insights` e `/api/eletrofrio/whatsapp/status`.

## Testar APIs

Health antigo:

```bash
curl http://127.0.0.1:8000/health
```

Health real:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
```

Overview:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/overview
```

Listas:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/units
curl http://127.0.0.1:8000/api/eletrofrio/devices
curl http://127.0.0.1:8000/api/eletrofrio/alarms
curl http://127.0.0.1:8000/api/eletrofrio/telemetry
curl http://127.0.0.1:8000/api/eletrofrio/insights
```

Rodar coleta pela API:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/run-collector
```

## Testar WhatsApp

Status direto:

```bash
curl http://127.0.0.1:8091/status
```

Status via FastAPI:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
```

Iniciar:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start
```

Enviar teste:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/send-test \
  -H "Content-Type: application/json" \
  -d '{"phone":"5541999999999","message":"Teste Eletrofrio IA"}'
```

Processar insights pendentes:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

## Dry-Run

Com:

```env
WHATSAPP_DRY_RUN=true
```

O sistema nao envia mensagem real, apenas loga no terminal.

Para enviar de verdade:

```env
WHATSAPP_DRY_RUN=false
```

## Evitar Spam

Configuracoes:

```env
WHATSAPP_MIN_INTERVAL_MINUTES_PER_DEVICE=30
WHATSAPP_MIN_INTERVAL_MINUTES_PER_STORE=60
```

O notificador so envia insights:

- ainda sem `whatsapp_sent_at`;
- severidade `warning` ou `critical`;
- com evidencia suficiente;
- respeitando intervalo por dispositivo e loja.

## Abertura De Chamados

Por padrao:

```env
AUTO_OPEN_TICKETS=false
```

Quando ativar futuramente, so abre chamado se:

- insight for `critical`;
- houver evidencia suficiente;
- existir `dispositivo_id`;
- nao houver chamado recente para o mesmo dispositivo;
- `motivoIA` vier do insight.

## Arquivos Principais

- `api/eletrofrio_client.py`: cliente dos endpoints oficiais.
- `api/collector.py`: coleta e persistencia.
- `api/normalizers.py`: mapeamento seguro dos campos reais.
- `api/analysis/metrics.py`: metricas por loja/dispositivo.
- `api/analysis/rules.py`: severidade deterministica.
- `api/ai/openai_analyzer.py`: GPT controlado.
- `api/decision/alert_engine.py`: geracao de insights.
- `api/tickets.py`: abertura controlada de chamados.
- `api/routes/eletrofrio.py`: endpoints internos.
- `whatsapp/src/whatsappClient.ts`: conexao Baileys.
- `whatsapp/src/messageSender.ts`: envio e normalizacao.
- `whatsapp/src/insightNotifier.ts`: envio de insights.
- `sql/001_initial_schema.sql`: schema Supabase.

## Rodando Com Docker

Prepare o ambiente Docker sem chaves reais no repositorio:

```bash
cd /caminho/onde/voce/clonou/JA
cp .env.docker.example .env
nano .env
```

Suba todos os servicos:

```bash
docker compose up --build
```

Ou em background:

```bash
docker compose up -d --build
```

Servicos publicados:

- API: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- WhatsApp: `http://localhost:8091`
- Scheduler: container separado usando a mesma imagem da API

Comandos uteis:

```bash
docker compose logs -f
docker compose logs -f whatsapp
docker compose exec api python -m api.collector
docker compose down
```

Documentacao completa: `docs/DOCKER.md`.

## Pendencias Conhecidas

1. Configurar `.env` real com Supabase e OpenAI.
2. Rodar SQL no Supabase.
3. Executar uma coleta real e conferir nomes reais dos campos em `raw_payload`.
4. Ajustar normalizadores se a API oficial retornar campos inesperados.
5. Evoluir dashboard para consumir `/api/eletrofrio/*`.
6. Definir destinatarios reais em `WHATSAPP_ALLOWED_RECIPIENTS`.
7. Fazer teste com `WHATSAPP_DRY_RUN=true` antes de enviar mensagens reais.
8. So ativar `AUTO_OPEN_TICKETS=true` depois de validar severidade/insights com a Eletrofrio.

## Checklist De Entrega Para A Eletrofrio

- [ ] `.env` preenchido com Supabase, OpenAI e equipe.
- [ ] SQL executado no Supabase.
- [ ] `uvicorn api.main:app --reload` sobe sem erro.
- [ ] `/api/eletrofrio/health` retorna Supabase/OpenAI configurados.
- [ ] `python -m api.collector` salva unidades, alarmes e telemetria.
- [ ] `eletrofrio_collector_runs` registra sucesso.
- [ ] `eletrofrio_ai_insights` recebe insights com evidencias.
- [ ] WhatsApp conecta via QR Code.
- [ ] `WHATSAPP_DRY_RUN=true` testado com mensagem.
- [ ] Destinatarios autorizados conferidos.
- [ ] Dashboard legado continua funcionando.
- [ ] Plano de evolucao do dashboard real apresentado.
- [ ] Abertura automatica de chamados permanece desligada ate validacao.
