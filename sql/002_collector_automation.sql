-- Automation layer for the Eletrofrio collector.
-- Run this file in Supabase SQL editor after 001_initial_schema.sql.

create extension if not exists pgcrypto;

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

alter table eletrofrio_collector_runs add column if not exists trigger_source text;
alter table eletrofrio_collector_runs add column if not exists anomalies_count integer not null default 0;
alter table eletrofrio_collector_runs add column if not exists whatsapp_alerts_count integer not null default 0;

create index if not exists idx_eletrofrio_anomalies_status on eletrofrio_anomalies(status);
create index if not exists idx_eletrofrio_anomalies_detected_at on eletrofrio_anomalies(detected_at desc);
create index if not exists idx_eletrofrio_anomalies_equipment on eletrofrio_anomalies(equipment_id);
create index if not exists idx_eletrofrio_collector_runs_status on eletrofrio_collector_runs(status);

drop trigger if exists trg_eletrofrio_collector_settings_updated_at on eletrofrio_collector_settings;
create trigger trg_eletrofrio_collector_settings_updated_at
before update on eletrofrio_collector_settings
for each row execute function set_eletrofrio_updated_at();

drop trigger if exists trg_eletrofrio_anomalies_updated_at on eletrofrio_anomalies;
create trigger trg_eletrofrio_anomalies_updated_at
before update on eletrofrio_anomalies
for each row execute function set_eletrofrio_updated_at();
