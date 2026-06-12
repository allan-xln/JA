-- Notifications and performance layer for Eletrofrio/JA.
-- Safe to run multiple times in Supabase SQL Editor.

create extension if not exists pgcrypto;

create or replace function public.set_eletrofrio_notifications_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create table if not exists public.eletrofrio_notification_recipients (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references public.eletrofrio_customers(id) on delete cascade,
  role text not null default 'client',
  name text,
  phone text not null,
  channel text not null default 'whatsapp',
  enabled boolean not null default true,
  receive_critical boolean not null default true,
  receive_warning_recurrent boolean not null default true,
  cooldown_minutes integer not null default 60,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.eletrofrio_notification_recipients add column if not exists customer_id uuid references public.eletrofrio_customers(id) on delete cascade;
alter table public.eletrofrio_notification_recipients add column if not exists role text not null default 'client';
alter table public.eletrofrio_notification_recipients add column if not exists name text;
alter table public.eletrofrio_notification_recipients add column if not exists phone text;
alter table public.eletrofrio_notification_recipients add column if not exists channel text not null default 'whatsapp';
alter table public.eletrofrio_notification_recipients add column if not exists enabled boolean not null default true;
alter table public.eletrofrio_notification_recipients add column if not exists receive_critical boolean not null default true;
alter table public.eletrofrio_notification_recipients add column if not exists receive_warning_recurrent boolean not null default true;
alter table public.eletrofrio_notification_recipients add column if not exists cooldown_minutes integer not null default 60;
alter table public.eletrofrio_notification_recipients add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_notification_recipients add column if not exists updated_at timestamptz not null default now();

create table if not exists public.eletrofrio_notification_events (
  id uuid primary key default gen_random_uuid(),
  notification_hash text unique,
  customer_id uuid references public.eletrofrio_customers(id) on delete set null,
  anomaly_id uuid references public.eletrofrio_anomalies(id) on delete set null,
  insight_id uuid references public.eletrofrio_ai_insights(id) on delete set null,
  recipient_id uuid references public.eletrofrio_notification_recipients(id) on delete set null,
  phone text,
  channel text not null default 'whatsapp',
  severity text,
  title text,
  message_preview text,
  message_full text,
  status text not null default 'skipped',
  skip_reason text,
  provider_message_id text,
  error_message text,
  created_at timestamptz not null default now(),
  sent_at timestamptz
);

alter table public.eletrofrio_notification_events add column if not exists notification_hash text;
alter table public.eletrofrio_notification_events add column if not exists customer_id uuid references public.eletrofrio_customers(id) on delete set null;
alter table public.eletrofrio_notification_events add column if not exists anomaly_id uuid references public.eletrofrio_anomalies(id) on delete set null;
alter table public.eletrofrio_notification_events add column if not exists insight_id uuid references public.eletrofrio_ai_insights(id) on delete set null;
alter table public.eletrofrio_notification_events add column if not exists recipient_id uuid references public.eletrofrio_notification_recipients(id) on delete set null;
alter table public.eletrofrio_notification_events add column if not exists phone text;
alter table public.eletrofrio_notification_events add column if not exists channel text not null default 'whatsapp';
alter table public.eletrofrio_notification_events add column if not exists severity text;
alter table public.eletrofrio_notification_events add column if not exists title text;
alter table public.eletrofrio_notification_events add column if not exists message_preview text;
alter table public.eletrofrio_notification_events add column if not exists message_full text;
alter table public.eletrofrio_notification_events add column if not exists status text not null default 'skipped';
alter table public.eletrofrio_notification_events add column if not exists skip_reason text;
alter table public.eletrofrio_notification_events add column if not exists provider_message_id text;
alter table public.eletrofrio_notification_events add column if not exists error_message text;
alter table public.eletrofrio_notification_events add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_notification_events add column if not exists sent_at timestamptz;

alter table public.eletrofrio_collector_runs add column if not exists duration_seconds numeric;
alter table public.eletrofrio_collector_runs add column if not exists units_duration numeric;
alter table public.eletrofrio_collector_runs add column if not exists alarms_duration numeric;
alter table public.eletrofrio_collector_runs add column if not exists telemetry_duration numeric;
alter table public.eletrofrio_collector_runs add column if not exists analysis_duration numeric;
alter table public.eletrofrio_collector_runs add column if not exists notification_duration numeric;
alter table public.eletrofrio_collector_runs add column if not exists devices_requested integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists devices_skipped_cache integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists devices_failed integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists telemetry_rows_saved integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists notifications_checked integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists notifications_sent integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists notifications_skipped integer not null default 0;
alter table public.eletrofrio_collector_runs add column if not exists notifications_failed integer not null default 0;

drop index if exists public.idx_eletrofrio_notification_events_hash;
create unique index if not exists idx_eletrofrio_notification_events_hash
on public.eletrofrio_notification_events(notification_hash)
where notification_hash is not null and status = 'sent';

drop index if exists public.idx_eletrofrio_notification_events_anomaly_recipient_channel;
create unique index if not exists idx_eletrofrio_notification_events_anomaly_recipient_channel
on public.eletrofrio_notification_events(anomaly_id, recipient_id, channel)
where anomaly_id is not null and recipient_id is not null and status = 'sent';

drop index if exists public.idx_eletrofrio_notification_events_insight_recipient_channel;
create unique index if not exists idx_eletrofrio_notification_events_insight_recipient_channel
on public.eletrofrio_notification_events(insight_id, recipient_id, channel)
where insight_id is not null and recipient_id is not null and status = 'sent';

create index if not exists idx_eletrofrio_notification_recipients_customer_id on public.eletrofrio_notification_recipients(customer_id);
create index if not exists idx_eletrofrio_notification_recipients_enabled on public.eletrofrio_notification_recipients(enabled);
create index if not exists idx_eletrofrio_notification_events_customer_id on public.eletrofrio_notification_events(customer_id);
create index if not exists idx_eletrofrio_notification_events_anomaly_id on public.eletrofrio_notification_events(anomaly_id);
create index if not exists idx_eletrofrio_notification_events_insight_id on public.eletrofrio_notification_events(insight_id);
create index if not exists idx_eletrofrio_notification_events_status on public.eletrofrio_notification_events(status);
create index if not exists idx_eletrofrio_notification_events_created_at on public.eletrofrio_notification_events(created_at desc);
create index if not exists idx_eletrofrio_notification_events_phone_created_at on public.eletrofrio_notification_events(phone, created_at desc);

create index if not exists idx_eletrofrio_alarms_loja_created_at on public.eletrofrio_alarms(loja_id, created_at desc);
create index if not exists idx_eletrofrio_alarms_dispositivo_created_at on public.eletrofrio_alarms(dispositivo_id, created_at desc);
create index if not exists idx_eletrofrio_alarms_started_at on public.eletrofrio_alarms(started_at desc);
create index if not exists idx_eletrofrio_telemetry_dispositivo_measured_at on public.eletrofrio_telemetry(dispositivo_id, measured_at desc);
create index if not exists idx_eletrofrio_telemetry_loja_measured_at on public.eletrofrio_telemetry(loja_id, measured_at desc);
create index if not exists idx_eletrofrio_ai_insights_loja_created_at on public.eletrofrio_ai_insights(loja_id, created_at desc);
create index if not exists idx_eletrofrio_ai_insights_dispositivo_created_at on public.eletrofrio_ai_insights(dispositivo_id, created_at desc);
create index if not exists idx_eletrofrio_ai_insights_severity_created_at on public.eletrofrio_ai_insights(severity, created_at desc);
create index if not exists idx_eletrofrio_anomalies_status_created_at on public.eletrofrio_anomalies(status, created_at desc);
create index if not exists idx_eletrofrio_anomalies_severity_created_at on public.eletrofrio_anomalies(severity, created_at desc);
create index if not exists idx_eletrofrio_anomalies_loja_created_at on public.eletrofrio_anomalies(loja_id, created_at desc);
create index if not exists idx_eletrofrio_anomalies_dispositivo_id_created_at on public.eletrofrio_anomalies(dispositivo_id, created_at desc);
create index if not exists idx_eletrofrio_anomalies_dispositivo_created_at on public.eletrofrio_anomalies(equipment_id, created_at desc);

drop trigger if exists trg_eletrofrio_notification_recipients_updated_at on public.eletrofrio_notification_recipients;
create trigger trg_eletrofrio_notification_recipients_updated_at
before update on public.eletrofrio_notification_recipients
for each row execute function public.set_eletrofrio_notifications_updated_at();
