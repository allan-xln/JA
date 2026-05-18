# Docker - Eletrofrio JA

Este projeto sobe a plataforma Eletrofrio JA com quatro containers: API FastAPI, scheduler/coletor, frontend Next.js e WhatsApp Baileys. O banco continua sendo o Supabase remoto; nao ha Postgres local.

## Containers

- `api`: FastAPI em `http://localhost:8000`.
- `scheduler`: executa `python -m api.scheduler` usando a mesma imagem da API.
- `frontend`: Next.js em `http://localhost:3000`.
- `whatsapp`: servico Baileys em `http://localhost:8091`.

## Rede

Todos os containers entram na rede bridge `eletrofrio-net`.

- API chama WhatsApp por `http://whatsapp:8091`.
- WhatsApp chama API por `http://api:8000`.
- Browser chama API por `http://localhost:8000`.
- Browser abre frontend por `http://localhost:3000`.

## Volumes

- `whatsapp-sessions`: persiste a sessao do Baileys e evita novo QR a cada restart.
- `api-logs`: reservado para logs da API.
- `api-data`: reservado para dados locais auxiliares.

Nao existe volume de banco porque os dados reais ficam no Supabase.

## Configurar Ambiente

Prepare o `.env` Docker a partir do exemplo:

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA
cp .env.docker.example .env
nano .env
```

Preencha pelo menos:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ELETROFRIO_TEAM_NAME`, se exigido pela API oficial
- `OPENAI_API_KEY`, se quiser sintese GPT
- `WHATSAPP_ALLOWED_RECIPIENTS`, para limitar destinatarios

No Docker, mantenha:

```env
WHATSAPP_SERVICE_URL=http://whatsapp:8091
ELETROFRIO_API_URL=http://api:8000
NEXT_PUBLIC_API_URL=http://localhost:8000
ELETROFRIO_START_INTERNAL_SCHEDULER=false
```

No modo manual local, use:

```env
WHATSAPP_SERVICE_URL=http://127.0.0.1:8091
ELETROFRIO_API_URL=http://127.0.0.1:8000
```

## Rodar Localmente em 4 Terminais

Backend:

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA
conda activate eletrofrio-ai
uvicorn api.main:app --reload
```

Collector ou scheduler:

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA
conda activate eletrofrio-ai
python -m api.collector
# ou
python -m api.scheduler
```

Frontend:

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA/Frontend/JA-IA-ELETROFRIO
npm run dev
```

WhatsApp:

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA/whatsapp
npm run dev
```

## Subir Tudo

```bash
docker compose up --build
```

Em background:

```bash
docker compose up -d --build
```

## Parar

```bash
docker compose down
```

Para limpar volumes:

```bash
docker compose down -v
```

Aviso: `down -v` apaga a sessao persistida do WhatsApp e dados locais dos volumes Docker.

## Logs

Todos os logs:

```bash
docker compose logs -f
```

API:

```bash
docker compose logs -f api
```

WhatsApp:

```bash
docker compose logs -f whatsapp
```

## Collector Manual

```bash
docker compose exec api python -m api.collector
```

O container `scheduler` ja roda separado. A API fica com `ELETROFRIO_START_INTERNAL_SCHEDULER=false` para evitar duplicidade.

## Testar API

```bash
curl http://127.0.0.1:8000/api/eletrofrio/health
curl http://127.0.0.1:8000/api/eletrofrio/overview
```

## Testar Frontend

Abra:

```text
http://localhost:3000
```

A tela usa `NEXT_PUBLIC_API_URL=http://localhost:8000`, pois as chamadas partem do browser.

## Testar WhatsApp

Status direto do servico:

```bash
curl http://127.0.0.1:8091/status
```

Status via API:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/status
```

Iniciar sessao e gerar QR:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/start
curl http://127.0.0.1:8000/api/eletrofrio/whatsapp/qr
```

Escaneie o QR retornado pelo endpoint ou acompanhe os logs:

```bash
docker compose logs -f whatsapp
```

Processar insights pendentes:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/whatsapp/process-insights
```

## Testar Diagnóstico Operacional

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Me dá um resumo da operação agora"}'
```

Sugestões:

```bash
curl http://127.0.0.1:8000/api/eletrofrio/assistant/suggestions
```

## Troubleshooting

- `Supabase não configurado`: confira `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
- Frontend sem dados: confirme `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- API nao chama WhatsApp: confirme `WHATSAPP_SERVICE_URL=http://whatsapp:8091`.
- WhatsApp nao consulta IA: confirme `ELETROFRIO_API_URL=http://api:8000`.
- QR nao aparece: rode `docker compose logs -f whatsapp` e confira `WHATSAPP_ENABLED=true`.
- Mensagens nao enviam: se `WHATSAPP_DRY_RUN=true`, o envio e apenas simulado nos logs.
- Scheduler duplicado: mantenha `ELETROFRIO_START_INTERNAL_SCHEDULER=false` no Docker.
