# Multi-cliente Eletrofrio/JA

## Objetivo

O projeto passou a ter autenticação com dois perfis:

- `admin`: visão administrativa completa.
- `client`: visão filtrada pelo cliente/tenant.

O isolamento é aplicado no backend. O frontend envia `Authorization: Bearer TOKEN`, mas a regra de segurança não depende apenas da tela.

## Modelo de dados

A migration `sql/005_multi_tenant_auth.sql` cria:

- `eletrofrio_customers`: clientes/tenants.
- `eletrofrio_users`: usuários com senha em hash.
- `eletrofrio_customer_units`: vínculo cliente -> loja.
- `eletrofrio_customer_devices`: vínculo cliente -> dispositivo.
- `eletrofrio_sessions`: sessões por token hash.

Também adiciona `customer_id` e `customer_name` em logs de comunicação, RAG e WhatsApp.

## Como aplicar a migration

No Supabase SQL Editor, execute:

```sql
-- arquivo do repositório
sql/005_multi_tenant_auth.sql
```

Ela é idempotente e pode ser rodada mais de uma vez.

## Como seedar clientes

Depois de aplicar a migration:

```bash
python -m api.scripts.seed_tenants
```

No Docker/VPS:

```bash
docker compose exec api python -m api.scripts.seed_tenants
```

O seed:

- cria `admin / admin`;
- detecta clientes a partir de `contaNm` no payload da loja, quando existir;
- se não houver conta, cria cliente por loja;
- vincula lojas e dispositivos;
- salva senhas com hash;
- grava `data/demo_users_generated.txt` e `data/demo_users_generated.json` para demo local.

`data/` já fica fora do Git.

## Isolamento

O admin não recebe filtro.

O cliente recebe filtro automático por:

- `loja_id` vinculado em `eletrofrio_customer_units`;
- `dispositivo_id` vinculado em `eletrofrio_customer_devices`.

Se um registro não tiver loja nem dispositivo vinculável, ele não aparece para cliente.

Endpoints filtrados:

- overview, lojas, dispositivos, alarmes, telemetria e insights;
- anomalias do collector;
- regras e avaliações;
- histórico de comunicação;
- histórico RAG;
- mensagens WhatsApp.

Operações administrativas como coleta, QR/logout WhatsApp e alteração de regras ficam restritas ao admin.

## RAG protegido

O RAG recebe o escopo do usuário autenticado:

- `role`;
- `customer_id`;
- `customer_name`;
- lojas permitidas;
- dispositivos permitidos.

As fontes usadas pelo RAG já chegam filtradas. Para cliente, perguntas sobre loja fora do ambiente retornam que a loja não foi encontrada no ambiente do cliente.

## WhatsApp e logs

Admin vê todos os logs.

Cliente vê apenas logs vinculados por:

- `customer_id`;
- `loja_id`;
- `dispositivo_id`;
- fontes filtradas do RAG.

Envios e ações administrativas do WhatsApp continuam restritos ao admin.

## Fallback de demo

Se `sql/005_multi_tenant_auth.sql` ainda não estiver aplicada, o backend usa o arquivo local `data/demo_users_generated.json` criado pelo seed como fallback de demonstração. Isso mantém a demo funcional, mas o modo recomendado é aplicar a migration no Supabase.

## Testes recomendados

Backend:

```bash
python -m compileall api
python -m api.scripts.seed_tenants
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
docker compose up -d --build
```

Teste funcional:

- login admin;
- login cliente gerado;
- comparar totais do overview;
- testar RAG com cliente;
- testar logout;
- confirmar que cliente não acessa coleta nem QR WhatsApp.
