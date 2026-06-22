-- Conservative cleanup for presentation/demo recovery.
-- Use when Supabase needs space, but storage is already expanded and useful history should remain available.
--
-- This script keeps a wider operational window:
-- - telemetry: last 30 days
-- - alarms: last 120 days
-- - insights/notifications/communications/RAG/WhatsApp logs: last 180 days
-- - collector runs: last 90 days
-- - resolved/ignored anomalies: last 365 days
-- - active anomalies: preserved
--
-- It does not touch users, customers, rules, recipients, WhatsApp sessions or auth tables.
-- Safe to run multiple times.

do $$
declare
  v_deleted integer;
begin
  if to_regclass('public.eletrofrio_telemetry') is not null then
    delete from public.eletrofrio_telemetry
    where coalesce(measured_at, created_at) < now() - interval '30 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_telemetry deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_alarms') is not null then
    delete from public.eletrofrio_alarms
    where coalesce(started_at, created_at) < now() - interval '120 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_alarms deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_ai_insights') is not null then
    delete from public.eletrofrio_ai_insights
    where created_at < now() - interval '180 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_ai_insights deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_notification_events') is not null then
    delete from public.eletrofrio_notification_events
    where created_at < now() - interval '180 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_notification_events deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_communication_logs') is not null then
    delete from public.eletrofrio_communication_logs
    where created_at < now() - interval '180 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_communication_logs deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_rag_queries') is not null then
    delete from public.eletrofrio_rag_queries
    where created_at < now() - interval '180 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_rag_queries deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_whatsapp_messages') is not null then
    delete from public.eletrofrio_whatsapp_messages
    where created_at < now() - interval '180 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_whatsapp_messages deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_collector_runs') is not null then
    delete from public.eletrofrio_collector_runs
    where coalesce(finished_at, started_at) < now() - interval '90 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_collector_runs deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomalies') is not null then
    delete from public.eletrofrio_anomalies
    where status in ('resolved', 'ignored')
      and coalesce(resolved_at, updated_at, created_at) < now() - interval '365 days';
    get diagnostics v_deleted = row_count;
    raise notice 'eletrofrio_anomalies resolved/ignored deleted: %', v_deleted;

    raise notice 'eletrofrio_anomalies active rows preserved.';
  end if;
end $$;

-- After this cleanup succeeds, run these separately if the SQL Editor accepts them:
-- vacuum analyze public.eletrofrio_telemetry;
-- vacuum analyze public.eletrofrio_alarms;
-- vacuum analyze public.eletrofrio_anomalies;
-- vacuum analyze public.eletrofrio_ai_insights;
-- vacuum analyze public.eletrofrio_notification_events;
