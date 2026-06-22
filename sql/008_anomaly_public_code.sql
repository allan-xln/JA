-- Public, stable and traceable codes for Eletrofrio operational anomalies.
-- Safe to run multiple times in Supabase SQL Editor.

do $$
begin
  if to_regclass('public.eletrofrio_anomalies') is null then
    raise exception 'Migration 008 requires public.eletrofrio_anomalies. Apply the base schema and migration 007 first.';
  end if;
end $$;

alter table public.eletrofrio_anomalies add column if not exists public_code text;
alter table public.eletrofrio_anomalies add column if not exists public_code_created_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists related_public_code text;

do $$
begin
  if to_regclass('public.eletrofrio_anomaly_events') is not null then
    alter table public.eletrofrio_anomaly_events add column if not exists public_code text;
  end if;
  if to_regclass('public.eletrofrio_anomaly_tickets') is not null then
    alter table public.eletrofrio_anomaly_tickets add column if not exists public_code text;
  end if;
  if to_regclass('public.eletrofrio_notification_events') is not null then
    alter table public.eletrofrio_notification_events add column if not exists public_code text;
  end if;
end $$;

create table if not exists public.eletrofrio_anomaly_code_counters (
  code_date date primary key,
  last_value bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_anomalies_public_code
on public.eletrofrio_anomalies(public_code)
where public_code is not null;

do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomalies' and column_name = 'customer_id'
  ) then
    create index if not exists idx_anomalies_customer_public_code
      on public.eletrofrio_anomalies(customer_id, public_code);
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomalies' and column_name = 'status'
  ) then
    create index if not exists idx_anomalies_public_code_status
      on public.eletrofrio_anomalies(public_code, status);
    create index if not exists idx_anomalies_status_public_code
      on public.eletrofrio_anomalies(status, public_code);
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomalies' and column_name = 'severity'
  ) then
    create index if not exists idx_anomalies_severity_public_code
      on public.eletrofrio_anomalies(severity, public_code);
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomalies' and column_name = 'created_at'
  ) then
    create index if not exists idx_anomalies_created_at_public_code
      on public.eletrofrio_anomalies(created_at desc, public_code);
  end if;

  if to_regclass('public.eletrofrio_anomaly_events') is not null and exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomaly_events' and column_name = 'created_at'
  ) then
    create index if not exists idx_anomaly_events_public_code
      on public.eletrofrio_anomaly_events(public_code, created_at desc);
  end if;
  if to_regclass('public.eletrofrio_anomaly_tickets') is not null and exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_anomaly_tickets' and column_name = 'created_at'
  ) then
    create index if not exists idx_anomaly_tickets_public_code
      on public.eletrofrio_anomaly_tickets(public_code, created_at desc);
  end if;
  if to_regclass('public.eletrofrio_notification_events') is not null and exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'eletrofrio_notification_events' and column_name = 'created_at'
  ) then
    create index if not exists idx_notification_events_public_code
      on public.eletrofrio_notification_events(public_code, created_at desc);
  end if;
end $$;

insert into public.eletrofrio_anomaly_code_counters (code_date, last_value)
select
  to_date(substring(public_code from 4 for 8), 'YYYYMMDD') as code_date,
  max((regexp_match(public_code, '^OC-[0-9]{8}-([0-9]+)$'))[1]::bigint) as last_value
from public.eletrofrio_anomalies
where public_code ~ '^OC-[0-9]{8}-[0-9]+$'
group by to_date(substring(public_code from 4 for 8), 'YYYYMMDD')
on conflict (code_date) do update
set
  last_value = greatest(public.eletrofrio_anomaly_code_counters.last_value, excluded.last_value),
  updated_at = now();

create or replace function public.next_eletrofrio_anomaly_public_code(p_code_date date)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_sequence bigint;
begin
  insert into public.eletrofrio_anomaly_code_counters as counters (code_date, last_value)
  values (coalesce(p_code_date, current_date), 1)
  on conflict (code_date) do update
  set
    last_value = counters.last_value + 1,
    updated_at = now()
  returning last_value into v_sequence;

  return format(
    'OC-%s-%s',
    to_char(coalesce(p_code_date, current_date), 'YYYYMMDD'),
    lpad(v_sequence::text, 4, '0')
  );
end;
$$;

create or replace function public.assign_eletrofrio_anomaly_public_code()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code_date date;
  v_row_json jsonb;
  v_event_at timestamptz;
begin
  if new.public_code is not null and btrim(new.public_code) <> '' then
    new.public_code := upper(btrim(new.public_code));
    new.public_code_created_at := coalesce(new.public_code_created_at, now());
    return new;
  end if;

  v_row_json := to_jsonb(new);
  v_event_at := coalesce(
    nullif(v_row_json ->> 'detected_at', '')::timestamptz,
    nullif(v_row_json ->> 'created_at', '')::timestamptz,
    now()
  );
  v_code_date := timezone('America/Sao_Paulo', v_event_at)::date;
  new.public_code := public.next_eletrofrio_anomaly_public_code(v_code_date);
  new.public_code_created_at := now();
  return new;
end;
$$;

drop trigger if exists trg_eletrofrio_anomaly_public_code on public.eletrofrio_anomalies;
create trigger trg_eletrofrio_anomaly_public_code
before insert on public.eletrofrio_anomalies
for each row execute function public.assign_eletrofrio_anomaly_public_code();

create or replace function public.ensure_eletrofrio_anomaly_public_code(p_anomaly_id uuid)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.eletrofrio_anomalies%rowtype;
  v_code_date date;
  v_public_code text;
  v_row_json jsonb;
  v_event_at timestamptz;
  v_related_anomaly_id uuid;
begin
  select * into v_row
  from public.eletrofrio_anomalies
  where id = p_anomaly_id
  for update;

  if not found then
    raise exception 'Anomalia não encontrada: %', p_anomaly_id;
  end if;

  if v_row.public_code is not null and btrim(v_row.public_code) <> '' then
    return upper(btrim(v_row.public_code));
  end if;

  v_row_json := to_jsonb(v_row);
  v_event_at := coalesce(
    nullif(v_row_json ->> 'detected_at', '')::timestamptz,
    nullif(v_row_json ->> 'created_at', '')::timestamptz,
    now()
  );
  v_related_anomaly_id := nullif(v_row_json ->> 'related_anomaly_id', '')::uuid;
  v_code_date := timezone('America/Sao_Paulo', v_event_at)::date;
  v_public_code := public.next_eletrofrio_anomaly_public_code(v_code_date);

  update public.eletrofrio_anomalies
  set
    public_code = v_public_code,
    public_code_created_at = now(),
    related_public_code = coalesce(
      related_public_code,
      (select parent.public_code from public.eletrofrio_anomalies parent where parent.id = v_related_anomaly_id)
    )
  where id = p_anomaly_id;

  return v_public_code;
end;
$$;

revoke all on function public.next_eletrofrio_anomaly_public_code(date) from public, anon, authenticated;
revoke all on function public.ensure_eletrofrio_anomaly_public_code(uuid) from public, anon, authenticated;
grant execute on function public.next_eletrofrio_anomaly_public_code(date) to service_role;
grant execute on function public.ensure_eletrofrio_anomaly_public_code(uuid) to service_role;
