# Migrations de anomalias, notificacoes, codigos e retencao

Este documento descreve a aplicacao segura das migrations do Eletrofrio/JA.
As migrations normais nao executam `CREATE EXTENSION`.

## Antes de comecar

O banco precisa aceitar escrita. No SQL Editor do Supabase, execute:

```sql
select
  pg_is_in_recovery() as in_recovery,
  current_setting('transaction_read_only') as transaction_read_only;
```

Continue somente quando o resultado for `false` e `off`.

Valide tambem a funcao usada nos defaults UUID:

```sql
select gen_random_uuid();
```

No Supabase atual, `gen_random_uuid()` normalmente ja esta disponivel. Se nao
estiver, execute separadamente, com uma role autorizada, o arquivo opcional
`sql/000_optional_enable_extensions.sql`. Ele nao faz parte da sequencia
normal.

## Ordem correta

Em uma base nova, aplique:

1. `sql/001_initial_schema.sql`
2. `sql/002_collector_runtime_schema.sql`
3. `sql/003_operational_rules.sql`
4. `sql/004_operational_communications.sql`
5. `sql/005_multi_tenant_auth.sql`
6. `sql/006_notifications_and_performance.sql`
7. `sql/007_anomaly_operations.sql`
8. `sql/008_anomaly_public_code.sql`
9. `sql/009_data_retention_and_cleanup.sql`

Em uma base que ja possui o schema operacional ate a migration 005, aplique
somente 006, 007, 008 e 009, nessa ordem.

A migration 008 depende das tabelas criadas pelas migrations 006 e 007. Ela
verifica as tabelas dependentes antes de altera-las e pode ser executada
novamente com seguranca.

A migration 009 cria a funcao de limpeza operacional controlada. Ela nao apaga
nada so por ser aplicada; a limpeza acontece apenas quando a funcao ou o script
de prune e executado.

## Limpeza e plano free

Existem dois SQLs operacionais de limpeza manual:

- `sql/010_presentation_emergency_cleanup.sql`: limpeza conservadora para
  apresentacao, mantendo mais historico.
- `sql/011_free_plan_retention_cleanup.sql`: limpeza curta para Supabase no
  plano free, mantendo o banco leve.

Use o 011 quando a prioridade for reduzir armazenamento e CPU:

```text
sql/011_free_plan_retention_cleanup.sql
```

Ele preserva usuarios, clientes, regras, destinatarios, auth e sessao do
WhatsApp. Ele remove dados operacionais antigos em lote e pode ser executado
varias vezes. Se algum notice mostrar exatamente `15000` linhas apagadas, rode o
011 novamente ate os numeros baixarem.

Depois de uma limpeza grande, se o SQL Editor aceitar, rode separadamente:

```sql
vacuum analyze public.eletrofrio_telemetry;
vacuum analyze public.eletrofrio_alarms;
vacuum analyze public.eletrofrio_anomalies;
vacuum analyze public.eletrofrio_ai_insights;
vacuum analyze public.eletrofrio_notification_events;
```

## Validacao apos 007 e 008

```sql
select to_regclass('public.eletrofrio_anomalies');
select to_regclass('public.eletrofrio_anomaly_events');
select to_regclass('public.eletrofrio_anomaly_tickets');
select to_regclass('public.eletrofrio_notification_events');
select to_regclass('public.eletrofrio_retention_runs');
```

Nao use `next_eletrofrio_anomaly_public_code()` apenas para inspecao em
producao, pois a chamada incrementa o contador diario.

Para validar e preencher uma anomalia ainda sem codigo:

```sql
select id, public.ensure_eletrofrio_anomaly_public_code(id)
from public.eletrofrio_anomalies
where public_code is null
limit 1;
```

## Backfill

Depois de aplicar 006, 007 e 008:

```bash
docker compose exec -T api python -m api.scripts.backfill_anomaly_public_codes
```

O script nao altera codigos existentes. Ele informa registros analisados,
atualizados, previamente codificados, relacoes atualizadas e erros.

## Codigo publico

O formato e `OC-AAAAMMDD-NNNN`, por exemplo
`OC-20260621-0001`. O codigo:

- e gerado localmente pelo banco, sem IA;
- permanece igual quando a mesma anomalia e reaberta;
- aparece na lista, no modal, no historico e no chamado;
- pode ser pesquisado no painel;
- e incluido nas mensagens operacionais do WhatsApp;
- respeita o mesmo isolamento multi-tenant da anomalia.

## Endpoints operacionais principais

Depois das migrations de anomalias, o frontend usa estes endpoints:

- `GET /api/eletrofrio/anomalies`
- `GET /api/eletrofrio/anomalies/{id}`
- `GET /api/eletrofrio/anomalies/by-code/{public_code}`
- `GET /api/eletrofrio/anomalies/search?code=OC-...`
- `POST /api/eletrofrio/anomalies/{id}/suggest-solution`
- `POST /api/eletrofrio/anomalies/{id}/send-whatsapp`
- `POST /api/eletrofrio/anomalies/{id}/resolve`
- `POST /api/eletrofrio/anomalies/{id}/reopen`
- `POST /api/eletrofrio/anomalies/{id}/notes`
- `POST /api/eletrofrio/anomalies/{id}/ticket`

Todos respeitam autenticacao e multi-tenant: admin ve tudo; cliente ve apenas o
proprio ambiente.

## Supabase em recovery/read-only

Erros `57P03`, `PGRST002` ou `25006 read-only transaction` indicam que o
banco nao esta pronto para migrations. Nessa condicao, nao tente contornar o
erro removendo DDL nem execute o backfill. Aguarde a recuperacao do primario ou
solicite ao suporte do Supabase a restauracao da disponibilidade de escrita.
