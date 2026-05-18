-- Eletrofrio real data foundation.
-- Run this file in the Supabase SQL editor before starting the collector.

create extension if not exists pgcrypto;

create table if not exists eletrofrio_units (
  id uuid primary key default gen_random_uuid(),
  loja_id bigint unique not null,
  loja_nome text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists eletrofrio_devices (
  id uuid primary key default gen_random_uuid(),
  loja_id bigint,
  dispositivo_id bigint unique not null,
  tag text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists eletrofrio_alarms (
  id uuid primary key default gen_random_uuid(),
  external_hash text unique not null,
  loja_id bigint,
  loja_nome text,
  dispositivo_id bigint,
  tag text,
  alarm_type text,
  alarm_message text,
  started_at timestamptz,
  ended_at timestamptz,
  raw_payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists eletrofrio_telemetry (
  id uuid primary key default gen_random_uuid(),
  external_hash text unique not null,
  loja_id bigint,
  dispositivo_id bigint,
  tag text,
  measured_at timestamptz,
  temperature numeric,
  raw_payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists eletrofrio_ai_insights (
  id uuid primary key default gen_random_uuid(),
  insight_hash text unique,
  insight_type text not null,
  severity text not null,
  loja_id bigint,
  loja_nome text,
  dispositivo_id bigint,
  tag text,
  title text not null,
  summary text not null,
  technical_reason text,
  recommended_action text,
  evidence_json jsonb not null,
  gpt_model text,
  created_at timestamptz not null default now(),
  whatsapp_sent_at timestamptz,
  ticket_opened_at timestamptz
);

create table if not exists eletrofrio_collector_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  units_count integer not null default 0,
  alarms_count integer not null default 0,
  telemetry_count integer not null default 0,
  error_message text,
  trigger_source text,
  anomalies_count integer not null default 0,
  whatsapp_alerts_count integer not null default 0
);

create table if not exists eletrofrio_collector_settings (
  id text primary key default 'default',
  enabled boolean not null default false,
  interval_minutes integer not null default 5 check (interval_minutes >= 5),
  alert_cooldown_minutes integer not null default 60 check (alert_cooldown_minutes >= 5),
  last_run_at timestamptz,
  next_run_at timestamptz,
  running boolean not null default false,
  last_status text not null default 'never_run',
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint eletrofrio_collector_settings_singleton check (id = 'default')
);

insert into eletrofrio_collector_settings (id, enabled, interval_minutes, alert_cooldown_minutes)
values ('default', false, 5, 60)
on conflict (id) do nothing;

create table if not exists eletrofrio_anomalies (
  id uuid primary key default gen_random_uuid(),
  anomaly_key text unique not null,
  sensor_id text,
  equipment_id bigint,
  loja_id bigint,
  loja_nome text,
  tag text,
  type text not null,
  severity text not null,
  value numeric,
  expected_range jsonb,
  message text not null,
  detected_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  resolved_at timestamptz,
  status text not null default 'open',
  source text not null default 'automatic_collector',
  metadata jsonb not null default '{}'::jsonb,
  whatsapp_sent_at timestamptz,
  whatsapp_status text,
  whatsapp_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_eletrofrio_units_loja_id on eletrofrio_units(loja_id);
create index if not exists idx_eletrofrio_devices_loja_id on eletrofrio_devices(loja_id);
create index if not exists idx_eletrofrio_devices_dispositivo_id on eletrofrio_devices(dispositivo_id);
create index if not exists idx_eletrofrio_alarms_created_at on eletrofrio_alarms(created_at desc);
create index if not exists idx_eletrofrio_alarms_device on eletrofrio_alarms(dispositivo_id);
create index if not exists idx_eletrofrio_alarms_loja on eletrofrio_alarms(loja_id);
create index if not exists idx_eletrofrio_telemetry_measured_at on eletrofrio_telemetry(measured_at desc);
create index if not exists idx_eletrofrio_telemetry_device on eletrofrio_telemetry(dispositivo_id);
create index if not exists idx_eletrofrio_ai_insights_created_at on eletrofrio_ai_insights(created_at desc);
create index if not exists idx_eletrofrio_ai_insights_device on eletrofrio_ai_insights(dispositivo_id);
alter table eletrofrio_ai_insights add column if not exists insight_hash text;
create unique index if not exists idx_eletrofrio_ai_insights_hash on eletrofrio_ai_insights(insight_hash);
create index if not exists idx_eletrofrio_collector_runs_started_at on eletrofrio_collector_runs(started_at desc);
create index if not exists idx_eletrofrio_collector_runs_status on eletrofrio_collector_runs(status);
create index if not exists idx_eletrofrio_anomalies_status on eletrofrio_anomalies(status);
create index if not exists idx_eletrofrio_anomalies_detected_at on eletrofrio_anomalies(detected_at desc);
create index if not exists idx_eletrofrio_anomalies_equipment on eletrofrio_anomalies(equipment_id);

create or replace function set_eletrofrio_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_eletrofrio_units_updated_at on eletrofrio_units;
create trigger trg_eletrofrio_units_updated_at
before update on eletrofrio_units
for each row execute function set_eletrofrio_updated_at();

drop trigger if exists trg_eletrofrio_devices_updated_at on eletrofrio_devices;
create trigger trg_eletrofrio_devices_updated_at
before update on eletrofrio_devices
for each row execute function set_eletrofrio_updated_at();

drop trigger if exists trg_eletrofrio_collector_settings_updated_at on eletrofrio_collector_settings;
create trigger trg_eletrofrio_collector_settings_updated_at
before update on eletrofrio_collector_settings
for each row execute function set_eletrofrio_updated_at();

drop trigger if exists trg_eletrofrio_anomalies_updated_at on eletrofrio_anomalies;
create trigger trg_eletrofrio_anomalies_updated_at
before update on eletrofrio_anomalies
for each row execute function set_eletrofrio_updated_at();
