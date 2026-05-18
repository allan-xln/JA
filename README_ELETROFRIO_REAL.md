# Eletrofrio Real - Base de Coleta, Analise e IA

Esta base transforma o piloto academico em um pipeline real usando os endpoints oficiais da Eletrofrio, Supabase e OpenAI.

## 1. Configurar ambiente

Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

Preencha no `.env`:

```env
ELETROFRIO_API_BASE_URL=https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon
ELETROFRIO_TEAM_NAME=Nome da Sua Equipe
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_SERVICE_ROLE_KEY=SUA_SERVICE_ROLE_KEY
OPENAI_API_KEY=SUA_OPENAI_KEY
OPENAI_MODEL=gpt-4o-mini
COLLECTOR_INTERVAL_MINUTES=5
WHATSAPP_ENABLED=false
AUTO_OPEN_TICKETS=false
```

Nao coloque chaves reais no repositorio.

## 2. Criar tabelas no Supabase

Abra o SQL editor do Supabase e rode:

```text
sql/001_initial_schema.sql
```

Tabelas criadas:

- `eletrofrio_units`
- `eletrofrio_devices`
- `eletrofrio_alarms`
- `eletrofrio_telemetry`
- `eletrofrio_ai_insights`
- `eletrofrio_collector_runs`

Todas as coletas salvam `raw_payload` para preservar os dados originais.

## 3. Instalar dependencias Python

Com Conda:

```bash
conda env create -f environment.yml
conda activate eletrofrio-ai
```

Ou, se o ambiente ja existe:

```bash
conda activate eletrofrio-ai
```

## 4. Rodar API

```bash
uvicorn api.main:app --reload
```

Testes:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/eletrofrio/health
curl http://127.0.0.1:8000/api/eletrofrio/overview
```

## 5. Rodar coletor manualmente

Executa uma coleta completa:

```bash
python -m api.collector
```

O coletor:

- busca unidades;
- busca alarmes;
- descobre dispositivos quando possivel;
- busca telemetria dos dispositivos conhecidos;
- salva tudo no Supabase;
- evita duplicidade com `external_hash`;
- gera insights por regras, metricas e GPT quando configurado;
- registra execucao em `eletrofrio_collector_runs`.

## 6. Rodar coletor em loop

Executa a cada `COLLECTOR_INTERVAL_MINUTES`, por padrao 5 minutos:

```bash
python -m api.scheduler
```

## 7. Endpoints internos reais

Novos endpoints:

- `GET /api/eletrofrio/health`
- `GET /api/eletrofrio/overview`
- `GET /api/eletrofrio/units`
- `GET /api/eletrofrio/devices`
- `GET /api/eletrofrio/alarms`
- `GET /api/eletrofrio/telemetry`
- `GET /api/eletrofrio/insights`
- `POST /api/eletrofrio/run-collector`

Os endpoints antigos do piloto continuam existindo para compatibilidade.

## 8. OpenAI/GPT

O modulo `api/ai/openai_analyzer.py` envia apenas contexto estruturado para o GPT.

Regra interna:

> Voce e um assistente tecnico de monitoramento de refrigeracao. Responda somente com base nos dados fornecidos. Se faltar evidencia, diga que nao ha dados suficientes. Nao invente valores, nomes, sensores, lojas, alarmes ou diagnosticos.

Se `OPENAI_API_KEY` nao estiver configurada, o sistema gera uma explicacao fallback baseada em regras.

## 9. WhatsApp

O WhatsApp roda como um servico Node isolado em `whatsapp/`. Ele usa Baileys, salva sessao local e nao depende do LanChat em runtime.

Instalar dependencias:

```bash
cd whatsapp
npm install
```

Configurar no `.env` da raiz do projeto:

```env
WHATSAPP_ENABLED=true
WHATSAPP_SESSION_DIR=./whatsapp/sessions/eletrofrio
WHATSAPP_DEFAULT_COUNTRY_CODE=55
WHATSAPP_ALLOWED_RECIPIENTS=5541999999999
WHATSAPP_DRY_RUN=true
WHATSAPP_MIN_INTERVAL_MINUTES_PER_DEVICE=30
WHATSAPP_MIN_INTERVAL_MINUTES_PER_STORE=60
WHATSAPP_SERVICE_PORT=8091
WHATSAPP_SERVICE_URL=http://127.0.0.1:8091
```

Rodar o servico:

```bash
cd whatsapp
npm run dev
```

Se `WHATSAPP_ENABLED=true`, o QR Code aparece no terminal. Escaneie com o celular que deve enviar os alertas.

A sessao fica em:

```text
whatsapp/sessions/eletrofrio
```

Essa pasta esta protegida por `whatsapp/.gitignore` e nao deve ser versionada.

Para testar status:

```bash
curl http://127.0.0.1:8091/status
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
```

Para iniciar pelo backend:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start
```

Para enviar mensagem de teste:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/send-test \
  -H "Content-Type: application/json" \
  -d '{"phone":"5541999999999","message":"Teste Eletrofrio IA"}'
```

Enquanto `WHATSAPP_DRY_RUN=true`, nada e enviado de verdade; o servico apenas registra no terminal.

Para processar insights pendentes:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

O notificador so envia insights com `severity` `warning` ou `critical`, sem `whatsapp_sent_at`, com evidencia suficiente e respeitando:

- `WHATSAPP_MIN_INTERVAL_MINUTES_PER_DEVICE`
- `WHATSAPP_MIN_INTERVAL_MINUTES_PER_STORE`

Para resetar a sessao, pare o servico e remova somente a pasta de sessao:

```bash
rm -rf whatsapp/sessions/eletrofrio
```

Depois rode `npm run dev` novamente e escaneie o novo QR Code.

## 10. Abertura automatica de chamado

Por seguranca, vem desligada:

```env
AUTO_OPEN_TICKETS=false
```

Quando ativada, a abertura automatica so acontece se:

- insight tiver severidade `critical`;
- houver evidencia suficiente;
- existir `dispositivo_id`;
- nao houver chamado recente registrado para o mesmo dispositivo.

## 11. Frontend

O dashboard atual pode continuar rodando:

```bash
cd Frontend/JA-IA-ELETROFRIO
npm install
npm run dev
```

Ele ainda consome o endpoint antigo `/api/dashboard`. A proxima etapa e evoluir o frontend para consumir `/api/eletrofrio/overview` e `/api/eletrofrio/insights`.
