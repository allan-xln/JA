# Checklist de Apresentacao - Eletrofrio JA

Use este checklist antes da demo para reduzir risco operacional e deixar o roteiro previsivel.

## Antes da Demo

- [ ] Confirmar que `.env` esta preenchido com `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
- [ ] Confirmar se `OPENAI_API_KEY` esta configurada ou se o fallback local sera usado.
- [ ] Confirmar `WHATSAPP_DRY_RUN=true` para evitar envio real durante testes.
- [ ] Confirmar `WHATSAPP_ALLOWED_RECIPIENTS` se houver envio para numeros reais.
- [ ] Fechar processos antigos nas portas `8000`, `3000` e `8091`.
- [ ] Abrir Supabase e deixar as tabelas principais visiveis para validacao.

## Subir Backend

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
uvicorn api.main:app --reload
```

Validar:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
curl http://127.0.0.1:8000/api/eletrofrio/overview
```

## Subir Scheduler ou Rodar Collector

Collector manual:

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
python -m api.collector
```

Scheduler:

```bash
cd /caminho/onde/voce/clonou/JA
conda activate eletrofrio-ai
python -m api.scheduler
```

Validar no Supabase:

- [ ] `eletrofrio_collector_runs` recebeu execucao.
- [ ] `eletrofrio_units` tem unidades.
- [ ] `eletrofrio_devices` tem dispositivos.
- [ ] `eletrofrio_alarms` tem alarmes.
- [ ] `eletrofrio_telemetry` tem telemetria quando disponivel.
- [ ] `eletrofrio_ai_insights` tem insights.

## Subir WhatsApp

```bash
cd /caminho/onde/voce/clonou/JA/whatsapp
npm run dev
```

Validar:

```bash
curl http://127.0.0.1:8091/status
curl http://127.0.0.1:8091/qr
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/qr
```

- [ ] QR aparece no terminal ou endpoint.
- [ ] Sessao conecta depois do scan.
- [ ] `send-test` respeita `WHATSAPP_DRY_RUN`.
- [ ] `process-insights` respeita `WHATSAPP_DRY_RUN`.

## Subir Frontend

```bash
cd /caminho/onde/voce/clonou/JA/Frontend/JA-IA-ELETROFRIO
npm run dev
```

Abrir:

```text
http://localhost:3000
```

Conferir telas:

- [ ] Dashboard.
- [ ] Ativos/Dispositivos.
- [ ] Alertas/Analises.
- [ ] Operacao/Criterios.
- [ ] WhatsApp/Notificacoes.
- [ ] IA Consultiva/Assistente Operacional.

## Confirmar Supabase e Dados

- [ ] `/api/eletrofrio/overview` retorna totais reais.
- [ ] `/api/eletrofrio/units` retorna lojas.
- [ ] `/api/eletrofrio/devices` retorna dispositivos.
- [ ] `/api/eletrofrio/alarms` retorna alarmes.
- [ ] `/api/eletrofrio/insights` retorna insights.

## Confirmar IA Consultiva

Perguntas prontas:

- "Me dá um resumo da operação agora"
- "Como está a loja Sítio Cercado?"
- "Quais equipamentos estão offline?"
- "Teve alguma anomalia hoje?"
- "Quais lojas estão críticas?"

Comando:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Me dá um resumo da operação agora"}'
```

Conferir:

- [ ] Resposta nao inventa sensor ou valor.
- [ ] Mostra fontes.
- [ ] Mostra avisos quando falta evidencia.
- [ ] Fallback local responde se OpenAI falhar.

## Roteiro Rapido de Apresentacao

1. Abrir Dashboard e mostrar visao executiva da operacao.
2. Entrar em Ativos para mostrar lojas/dispositivos monitorados.
3. Entrar em Alertas para mostrar insights e evidencias.
4. Abrir IA Consultiva e fazer uma pergunta sobre operacao.
5. Abrir WhatsApp e mostrar QR/status do canal.
6. Explicar collector/scheduler como automacao de coleta e analise.
7. Fechar com Docker: `docker compose up --build` sobe a plataforma completa.

## Problemas Comuns e Solucao

- API nao sobe: confirmar `conda activate eletrofrio-ai` e `.env`.
- Supabase nao responde: validar `SUPABASE_URL` e service role.
- Frontend sem dados: confirmar API em `http://127.0.0.1:8000`.
- WhatsApp sem QR: chamar `/api/eletrofrio/whatsapp/start` e ver logs.
- IA sem GPT: confirmar `OPENAI_API_KEY`; fallback local deve continuar respondendo.
- Docker sem build: confirmar Docker instalado e daemon ativo.
- Scheduler duplicado: no Docker manter `ELETROFRIO_START_INTERNAL_SCHEDULER=false`.
