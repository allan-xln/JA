-- Retention and bounded cleanup for Eletrofrio operational data.
-- Safe to run multiple times in Supabase SQL Editor.
-- The cleanup function deletes in bounded batches to avoid long locks.

create table if not exists public.eletrofrio_retention_runs (
  id bigserial primary key,
  dry_run boolean not null default true,
  telemetry_days integer not null,
  alarm_days integer not null,
  insight_days integer not null,
  communication_days integer not null,
  collector_run_days integer not null,
  resolved_anomaly_days integer not null,
  batch_limit integer not null,
  result_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_eletrofrio_retention_runs_created_at
on public.eletrofrio_retention_runs(created_at desc);

create or replace function public.prune_eletrofrio_retention_bucket(
  p_table regclass,
  p_age_expression text,
  p_days integer,
  p_batch_limit integer,
  p_dry_run boolean
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer := 0;
begin
  if p_days is null or p_days <= 0 or p_batch_limit is null or p_batch_limit <= 0 then
    return 0;
  end if;

  if p_dry_run then
    execute format(
      'select count(*) from (select id from %s where %s < now() - ($1 * interval ''1 day'') limit $2) rows',
      p_table,
      p_age_expression
    )
    using p_days, p_batch_limit
    into v_count;
    return coalesce(v_count, 0);
  end if;

  execute format(
    'with doomed as (
       select id from %s
       where %s < now() - ($1 * interval ''1 day'')
       order by %s asc nulls first
       limit $2
     )
     delete from %s target
     using doomed
     where target.id = doomed.id',
    p_table,
    p_age_expression,
    p_age_expression,
    p_table
  )
  using p_days, p_batch_limit;

  get diagnostics v_count = row_count;
  return coalesce(v_count, 0);
end;
$$;

create or replace function public.prune_eletrofrio_operational_data(
  p_dry_run boolean default true,
  p_telemetry_days integer default 60,
  p_alarm_days integer default 180,
  p_insight_days integer default 365,
  p_communication_days integer default 365,
  p_collector_run_days integer default 90,
  p_resolved_anomaly_days integer default 365,
  p_batch_limit integer default 10000
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_result jsonb := '{}'::jsonb;
  v_count integer;
begin
  if to_regclass('public.eletrofrio_telemetry') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_telemetry'::regclass,
      'coalesce(measured_at, created_at)',
      p_telemetry_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('telemetry', v_count);
  end if;

  if to_regclass('public.eletrofrio_alarms') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_alarms'::regclass,
      'coalesce(started_at, created_at)',
      p_alarm_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('alarms', v_count);
  end if;

  if to_regclass('public.eletrofrio_ai_insights') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_ai_insights'::regclass,
      'created_at',
      p_insight_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('ai_insights', v_count);
  end if;

  if to_regclass('public.eletrofrio_collector_runs') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_collector_runs'::regclass,
      'started_at',
      p_collector_run_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('collector_runs', v_count);
  end if;

  if to_regclass('public.eletrofrio_notification_events') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_notification_events'::regclass,
      'created_at',
      p_communication_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('notification_events', v_count);
  end if;

  if to_regclass('public.eletrofrio_communication_logs') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_communication_logs'::regclass,
      'created_at',
      p_communication_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('communication_logs', v_count);
  end if;

  if to_regclass('public.eletrofrio_rag_queries') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_rag_queries'::regclass,
      'created_at',
      p_communication_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('rag_queries', v_count);
  end if;

  if to_regclass('public.eletrofrio_whatsapp_messages') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_whatsapp_messages'::regclass,
      'created_at',
      p_communication_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('whatsapp_messages', v_count);
  end if;

  if to_regclass('public.eletrofrio_anomaly_ai_solutions') is not null then
    v_count := public.prune_eletrofrio_retention_bucket(
      'public.eletrofrio_anomaly_ai_solutions'::regclass,
      'created_at',
      p_resolved_anomaly_days,
      p_batch_limit,
      p_dry_run
    );
    v_result := v_result || jsonb_build_object('anomaly_ai_solutions', v_count);
  end if;

  if to_regclass('public.eletrofrio_anomalies') is not null and p_resolved_anomaly_days > 0 then
    if p_dry_run then
      select count(*) into v_count
      from (
        select id
        from public.eletrofrio_anomalies
        where status in ('resolved', 'ignored')
          and coalesce(resolved_at, updated_at, created_at) < now() - (p_resolved_anomaly_days * interval '1 day')
        limit p_batch_limit
      ) rows;
    else
      with doomed as (
        select id
        from public.eletrofrio_anomalies
        where status in ('resolved', 'ignored')
          and coalesce(resolved_at, updated_at, created_at) < now() - (p_resolved_anomaly_days * interval '1 day')
        order by coalesce(resolved_at, updated_at, created_at) asc nulls first
        limit p_batch_limit
      )
      delete from public.eletrofrio_anomalies target
      using doomed
      where target.id = doomed.id;
      get diagnostics v_count = row_count;
    end if;
    v_result := v_result || jsonb_build_object('resolved_anomalies', coalesce(v_count, 0));
  else
    v_result := v_result || jsonb_build_object('resolved_anomalies', 0);
  end if;

  v_result := jsonb_build_object(
    'dry_run', p_dry_run,
    'batch_limit', p_batch_limit,
    'retention_days', jsonb_build_object(
      'telemetry', p_telemetry_days,
      'alarms', p_alarm_days,
      'ai_insights', p_insight_days,
      'communication', p_communication_days,
      'collector_runs', p_collector_run_days,
      'resolved_anomalies', p_resolved_anomaly_days
    ),
    'deleted_or_matching_rows', v_result
  );

  insert into public.eletrofrio_retention_runs (
    dry_run,
    telemetry_days,
    alarm_days,
    insight_days,
    communication_days,
    collector_run_days,
    resolved_anomaly_days,
    batch_limit,
    result_json
  )
  values (
    p_dry_run,
    p_telemetry_days,
    p_alarm_days,
    p_insight_days,
    p_communication_days,
    p_collector_run_days,
    p_resolved_anomaly_days,
    p_batch_limit,
    v_result
  );

  return v_result;
end;
$$;

revoke all on function public.prune_eletrofrio_retention_bucket(regclass, text, integer, integer, boolean) from public, anon, authenticated;
revoke all on function public.prune_eletrofrio_operational_data(boolean, integer, integer, integer, integer, integer, integer, integer) from public, anon, authenticated;
grant execute on function public.prune_eletrofrio_operational_data(boolean, integer, integer, integer, integer, integer, integer, integer) to service_role;
