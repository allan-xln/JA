-- Runtime schema for collector automation, anomaly tracking and operational status.
-- Safe to run multiple times in Supabase SQL Editor.

create extension if not exists pgcrypto;

create or replace function public.set_eletrofrio_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create table if not exists public.eletrofrio_collector_settings (
  id text primary key default 'default',
  is_enabled boolean not null default true,
  enabled boolean not null default false,
  interval_minutes integer not null default 5,
  alert_cooldown_minutes integer not null default 60,
  running boolean not null default false,
  last_run_at timestamptz,
  next_run_at timestamptz,
  last_status text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint eletrofrio_collector_settings_singleton check (id = 'default')
);

alter table public.eletrofrio_collector_settings add column if not exists is_enabled boolean not null default true;
alter table public.eletrofrio_collector_settings add column if not exists enabled boolean not null default false;
alter table public.eletrofrio_collector_settings add column if not exists interval_minutes integer not null default 5;
alter table public.eletrofrio_collector_settings add column if not exists alert_cooldown_minutes integer not null default 60;
alter table public.eletrofrio_collector_settings add column if not exists running boolean not null default false;
alter table public.eletrofrio_collector_settings add column if not exists last_run_at timestamptz;
alter table public.eletrofrio_collector_settings add column if not exists next_run_at timestamptz;
alter table public.eletrofrio_collector_settings add column if not exists last_status text;
alter table public.eletrofrio_collector_settings add column if not exists last_error text;
alter table public.eletrofrio_collector_settings add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_collector_settings add column if not exists updated_at timestamptz not null default now();

insert into public.eletrofrio_collector_settings (id)
values ('default')
on conflict (id) do nothing;

update public.eletrofrio_collector_settings
set
  enabled = coalesce(enabled, is_enabled, false),
  is_enabled = coalesce(is_enabled, enabled, true),
  interval_minutes = greatest(5, coalesce(interval_minutes, 5)),
  alert_cooldown_minutes = greatest(5, coalesce(alert_cooldown_minutes, 60)),
  updated_at = now()
where id = 'default';

drop trigger if exists trg_eletrofrio_collector_settings_updated_at on public.eletrofrio_collector_settings;
create trigger trg_eletrofrio_collector_settings_updated_at
before update on public.eletrofrio_collector_settings
for each row execute function public.set_eletrofrio_updated_at();

create table if not exists public.eletrofrio_anomalies (
  id uuid primary key default gen_random_uuid(),
  anomaly_hash text unique,
  anomaly_key text unique,
  status text not null default 'open',
  severity text,
  loja_id integer,
  loja_nome text,
  dispositivo_id integer,
  equipment_id integer,
  sensor_id text,
  tag text,
  type text,
  title text,
  summary text,
  message text,
  technical_reason text,
  recommended_action text,
  value numeric,
  expected_range jsonb not null default '{}'::jsonb,
  evidence_json jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  source text,
  detected_at timestamptz not null default now(),
  last_seen_at timestamptz,
  resolved_at timestamptz,
  whatsapp_sent_at timestamptz,
  whatsapp_status text,
  whatsapp_error text,
  ticket_opened_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.eletrofrio_anomalies add column if not exists anomaly_hash text;
alter table public.eletrofrio_anomalies add column if not exists anomaly_key text;
alter table public.eletrofrio_anomalies add column if not exists status text not null default 'open';
alter table public.eletrofrio_anomalies add column if not exists severity text;
alter table public.eletrofrio_anomalies add column if not exists loja_id integer;
alter table public.eletrofrio_anomalies add column if not exists loja_nome text;
alter table public.eletrofrio_anomalies add column if not exists dispositivo_id integer;
alter table public.eletrofrio_anomalies add column if not exists equipment_id integer;
alter table public.eletrofrio_anomalies add column if not exists sensor_id text;
alter table public.eletrofrio_anomalies add column if not exists tag text;
alter table public.eletrofrio_anomalies add column if not exists type text;
alter table public.eletrofrio_anomalies add column if not exists title text;
alter table public.eletrofrio_anomalies add column if not exists summary text;
alter table public.eletrofrio_anomalies add column if not exists message text;
alter table public.eletrofrio_anomalies add column if not exists technical_reason text;
alter table public.eletrofrio_anomalies add column if not exists recommended_action text;
alter table public.eletrofrio_anomalies add column if not exists value numeric;
alter table public.eletrofrio_anomalies add column if not exists expected_range jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomalies add column if not exists evidence_json jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomalies add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomalies add column if not exists source text;
alter table public.eletrofrio_anomalies add column if not exists detected_at timestamptz not null default now();
alter table public.eletrofrio_anomalies add column if not exists last_seen_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists resolved_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists whatsapp_sent_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists whatsapp_status text;
alter table public.eletrofrio_anomalies add column if not exists whatsapp_error text;
alter table public.eletrofrio_anomalies add column if not exists ticket_opened_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_anomalies add column if not exists updated_at timestamptz not null default now();

update public.eletrofrio_anomalies
set
  anomaly_hash = coalesce(anomaly_hash, anomaly_key),
  dispositivo_id = coalesce(dispositivo_id, equipment_id),
  equipment_id = coalesce(equipment_id, dispositivo_id),
  evidence_json = case when evidence_json = '{}'::jsonb then coalesce(metadata, '{}'::jsonb) else evidence_json end,
  metadata = coalesce(metadata, evidence_json, '{}'::jsonb),
  updated_at = now();

create unique index if not exists idx_eletrofrio_anomalies_anomaly_hash
on public.eletrofrio_anomalies(anomaly_hash)
where anomaly_hash is not null;

create unique index if not exists idx_eletrofrio_anomalies_anomaly_key
on public.eletrofrio_anomalies(anomaly_key)
where anomaly_key is not null;

create index if not exists idx_eletrofrio_anomalies_status on public.eletrofrio_anomalies(status);
create index if not exists idx_eletrofrio_anomalies_severity on public.eletrofrio_anomalies(severity);
create index if not exists idx_eletrofrio_anomalies_loja_id on public.eletrofrio_anomalies(loja_id);
create index if not exists idx_eletrofrio_anomalies_dispositivo_id on public.eletrofrio_anomalies(dispositivo_id);
create index if not exists idx_eletrofrio_anomalies_equipment on public.eletrofrio_anomalies(equipment_id);
create index if not exists idx_eletrofrio_anomalies_detected_at on public.eletrofrio_anomalies(detected_at desc);

drop trigger if exists trg_eletrofrio_anomalies_updated_at on public.eletrofrio_anomalies;
create trigger trg_eletrofrio_anomalies_updated_at
before update on public.eletrofrio_anomalies
for each row execute function public.set_eletrofrio_updated_at();

create table if not exists public.eletrofrio_collector_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  units_count integer not null default 0,
  alarms_count integer not null default 0,
  telemetry_count integer not null default 0,
  insights_count integer not null default 0,
  anomalies_count integer not null default 0,
  whatsapp_alerts_count integer not null default 0,
  trigger_source text,
  source text,
  error_message text
);

alter table public.eletrofrio_collector_runs add column if not exists started_at timestamptz not null default now();
alter table public.eletrofrio_collector_runs add column if not exists finished_at timestamptz;
alter table public.eletrofrio_collector_runs add column if not exists status text not null default 'running';
alter table public.eletrofrio_collector_runs add column if not exists units_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists alarms_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists telemetry_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists insights_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists anomalies_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists whatsapp_alerts_count integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists trigger_source text;
alter table public.eletrofrio_collector_runs add column if not exists source text;
alter table public.eletrofrio_collector_runs add column if not exists error_message text;

create index if not exists idx_eletrofrio_collector_runs_started_at on public.eletrofrio_collector_runs(started_at desc);
create index if not exists idx_eletrofrio_collector_runs_status on public.eletrofrio_collector_runs(status);
create index if not exists idx_eletrofrio_collector_runs_trigger_source on public.eletrofrio_collector_runs(trigger_source);
