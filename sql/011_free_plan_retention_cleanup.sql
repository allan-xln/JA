-- Free-plan retention and cleanup for Eletrofrio/JA.
-- Use when Supabase is back on the free plan and storage/CPU must stay small.
--
-- Keeps a short operational window:
-- - telemetry: last 3 days
-- - alarms: last 14 days
-- - AI insights / notifications / communication logs / WhatsApp logs: last 30 days
-- - RAG query logs: last 14 days
-- - collector runs and retention run logs: last 14 days
-- - resolved/ignored anomalies: last 30 days
-- - active anomalies: preserved, but capped to the newest 300 active rows
--
-- It does not touch users, customers, rules, recipients, auth tables or WhatsApp sessions.
-- Safe to run multiple times. Deletes are bounded to avoid long locks.

do $$
declare
  v_deleted integer;
  v_total integer := 0;
  v_batch_limit integer := 15000;
begin
  if to_regclass('public.eletrofrio_telemetry') is not null then
    delete from public.eletrofrio_telemetry target
    where target.id in (
      select id
      from public.eletrofrio_telemetry
      where coalesce(measured_at, created_at) < now() - interval '3 days'
      order by coalesce(measured_at, created_at) asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_telemetry deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_alarms') is not null then
    delete from public.eletrofrio_alarms target
    where target.id in (
      select id
      from public.eletrofrio_alarms
      where coalesce(started_at, created_at) < now() - interval '14 days'
      order by coalesce(started_at, created_at) asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_alarms deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_ai_insights') is not null then
    delete from public.eletrofrio_ai_insights target
    where target.id in (
      select id
      from public.eletrofrio_ai_insights
      where created_at < now() - interval '30 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_ai_insights deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_notification_events') is not null then
    delete from public.eletrofrio_notification_events target
    where target.id in (
      select id
      from public.eletrofrio_notification_events
      where created_at < now() - interval '30 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_notification_events deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_communication_logs') is not null then
    delete from public.eletrofrio_communication_logs target
    where target.id in (
      select id
      from public.eletrofrio_communication_logs
      where created_at < now() - interval '30 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_communication_logs deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_rag_queries') is not null then
    delete from public.eletrofrio_rag_queries target
    where target.id in (
      select id
      from public.eletrofrio_rag_queries
      where created_at < now() - interval '14 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_rag_queries deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_whatsapp_messages') is not null then
    delete from public.eletrofrio_whatsapp_messages target
    where target.id in (
      select id
      from public.eletrofrio_whatsapp_messages
      where created_at < now() - interval '30 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_whatsapp_messages deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_collector_runs') is not null then
    delete from public.eletrofrio_collector_runs target
    where target.id in (
      select id
      from public.eletrofrio_collector_runs
      where coalesce(finished_at, started_at) < now() - interval '14 days'
      order by coalesce(finished_at, started_at) asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_collector_runs deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_retention_runs') is not null then
    delete from public.eletrofrio_retention_runs target
    where target.id in (
      select id
      from public.eletrofrio_retention_runs
      where created_at < now() - interval '14 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_retention_runs deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomaly_ai_solutions') is not null then
    delete from public.eletrofrio_anomaly_ai_solutions target
    where target.id in (
      select id
      from public.eletrofrio_anomaly_ai_solutions
      where created_at < now() - interval '30 days'
      order by created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomaly_ai_solutions deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomaly_events') is not null then
    delete from public.eletrofrio_anomaly_events target
    where target.id in (
      select event.id
      from public.eletrofrio_anomaly_events event
      left join public.eletrofrio_anomalies anomaly on anomaly.id = event.anomaly_id
      where event.created_at < now() - interval '30 days'
        and coalesce(anomaly.status, 'resolved') in ('resolved', 'ignored')
      order by event.created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomaly_events resolved/ignored deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomaly_notes') is not null then
    delete from public.eletrofrio_anomaly_notes target
    where target.id in (
      select note.id
      from public.eletrofrio_anomaly_notes note
      left join public.eletrofrio_anomalies anomaly on anomaly.id = note.anomaly_id
      where note.created_at < now() - interval '30 days'
        and coalesce(anomaly.status, 'resolved') in ('resolved', 'ignored')
      order by note.created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomaly_notes resolved/ignored deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomaly_tickets') is not null then
    delete from public.eletrofrio_anomaly_tickets target
    where target.id in (
      select ticket.id
      from public.eletrofrio_anomaly_tickets ticket
      left join public.eletrofrio_anomalies anomaly on anomaly.id = ticket.anomaly_id
      where ticket.created_at < now() - interval '30 days'
        and coalesce(anomaly.status, 'resolved') in ('resolved', 'ignored')
      order by ticket.created_at asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomaly_tickets resolved/ignored deleted: %', v_deleted;
  end if;

  if to_regclass('public.eletrofrio_anomalies') is not null then
    delete from public.eletrofrio_anomalies target
    where target.id in (
      select id
      from public.eletrofrio_anomalies
      where coalesce(status, 'open') in ('resolved', 'ignored')
        and coalesce(resolved_at, updated_at, created_at) < now() - interval '30 days'
      order by coalesce(resolved_at, updated_at, created_at) asc nulls first
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomalies resolved/ignored deleted: %', v_deleted;

    delete from public.eletrofrio_anomalies target
    where target.id in (
      select id
      from (
        select
          id,
          row_number() over (
            order by
              case when severity = 'critical' then 0 when severity = 'warning' then 1 else 2 end,
              coalesce(updated_at, last_seen_at, detected_at, created_at) desc
          ) as rn
        from public.eletrofrio_anomalies
        where coalesce(status, 'open') not in ('resolved', 'ignored')
      ) ranked
      where ranked.rn > 300
      limit v_batch_limit
    );
    get diagnostics v_deleted = row_count;
    v_total := v_total + v_deleted;
    raise notice 'eletrofrio_anomalies active cap deleted: %', v_deleted;
  end if;

  raise notice 'free-plan cleanup finished. Total deleted in this run: %', v_total;
end $$;

-- Optional after the cleanup succeeds. Run separately if the SQL Editor accepts it:
-- vacuum analyze public.eletrofrio_telemetry;
-- vacuum analyze public.eletrofrio_alarms;
-- vacuum analyze public.eletrofrio_anomalies;
-- vacuum analyze public.eletrofrio_ai_insights;
-- vacuum analyze public.eletrofrio_notification_events;
