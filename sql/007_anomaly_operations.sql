-- Operational workflow for Eletrofrio anomalies.
-- Safe to run multiple times in Supabase SQL Editor.

do $$
begin
  if to_regprocedure('gen_random_uuid()') is null then
    raise exception 'gen_random_uuid() is unavailable. Enable pgcrypto separately before migration 007.';
  end if;
  if to_regclass('public.eletrofrio_anomalies') is null then
    raise exception 'Migration 007 requires public.eletrofrio_anomalies. Apply the base and runtime schemas first.';
  end if;
end $$;

create or replace function public.set_eletrofrio_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

alter table public.eletrofrio_anomalies add column if not exists customer_id uuid;
alter table public.eletrofrio_anomalies add column if not exists acknowledged_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists reopened_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists ignored_until timestamptz;
alter table public.eletrofrio_anomalies add column if not exists recurrence_count integer not null default 0;
alter table public.eletrofrio_anomalies add column if not exists priority_score numeric not null default 0;
alter table public.eletrofrio_anomalies add column if not exists last_solution_hash text;
alter table public.eletrofrio_anomalies add column if not exists last_solution_at timestamptz;
alter table public.eletrofrio_anomalies add column if not exists last_solution_json jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomalies add column if not exists related_anomaly_id uuid;

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public'
      and table_name = 'eletrofrio_customers'
  ) and not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.eletrofrio_anomalies'::regclass
      and conname = 'eletrofrio_anomalies_customer_id_fkey'
  ) then
    alter table public.eletrofrio_anomalies
      add constraint eletrofrio_anomalies_customer_id_fkey
      foreign key (customer_id) references public.eletrofrio_customers(id)
      on delete set null;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.eletrofrio_anomalies'::regclass
      and conname = 'eletrofrio_anomalies_related_anomaly_id_fkey'
  ) then
    alter table public.eletrofrio_anomalies
      add constraint eletrofrio_anomalies_related_anomaly_id_fkey
      foreign key (related_anomaly_id) references public.eletrofrio_anomalies(id)
      on delete set null;
  end if;
end $$;

create table if not exists public.eletrofrio_anomaly_events (
  id uuid primary key default gen_random_uuid(),
  anomaly_id uuid not null references public.eletrofrio_anomalies(id) on delete cascade,
  customer_id uuid,
  user_id text,
  event_type text not null,
  old_status text,
  new_status text,
  title text not null,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.eletrofrio_anomaly_tickets (
  id uuid primary key default gen_random_uuid(),
  anomaly_id uuid not null references public.eletrofrio_anomalies(id) on delete cascade,
  customer_id uuid,
  title text not null,
  description text not null,
  priority text not null default 'medium',
  status text not null default 'open',
  assigned_to text,
  external_ticket_id text,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.eletrofrio_anomaly_notes (
  id uuid primary key default gen_random_uuid(),
  anomaly_id uuid not null references public.eletrofrio_anomalies(id) on delete cascade,
  customer_id uuid,
  user_id text,
  author_name text,
  note text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.eletrofrio_anomaly_ai_solutions (
  id uuid primary key default gen_random_uuid(),
  anomaly_id uuid not null references public.eletrofrio_anomalies(id) on delete cascade,
  customer_id uuid,
  user_id text,
  solution_hash text not null,
  model text,
  used_ai boolean not null default false,
  cached boolean not null default false,
  prompt_context jsonb not null default '{}'::jsonb,
  solution_json jsonb not null default '{}'::jsonb,
  solution_text text,
  error_message text,
  created_at timestamptz not null default now()
);

alter table public.eletrofrio_anomaly_events add column if not exists anomaly_id uuid;
alter table public.eletrofrio_anomaly_events add column if not exists customer_id uuid;
alter table public.eletrofrio_anomaly_events add column if not exists user_id text;
alter table public.eletrofrio_anomaly_events add column if not exists event_type text;
alter table public.eletrofrio_anomaly_events add column if not exists old_status text;
alter table public.eletrofrio_anomaly_events add column if not exists new_status text;
alter table public.eletrofrio_anomaly_events add column if not exists title text;
alter table public.eletrofrio_anomaly_events add column if not exists description text;
alter table public.eletrofrio_anomaly_events add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomaly_events add column if not exists created_at timestamptz not null default now();

alter table public.eletrofrio_anomaly_tickets add column if not exists anomaly_id uuid;
alter table public.eletrofrio_anomaly_tickets add column if not exists customer_id uuid;
alter table public.eletrofrio_anomaly_tickets add column if not exists title text;
alter table public.eletrofrio_anomaly_tickets add column if not exists description text;
alter table public.eletrofrio_anomaly_tickets add column if not exists priority text not null default 'medium';
alter table public.eletrofrio_anomaly_tickets add column if not exists status text not null default 'open';
alter table public.eletrofrio_anomaly_tickets add column if not exists assigned_to text;
alter table public.eletrofrio_anomaly_tickets add column if not exists external_ticket_id text;
alter table public.eletrofrio_anomaly_tickets add column if not exists created_by text;
alter table public.eletrofrio_anomaly_tickets add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_anomaly_tickets add column if not exists updated_at timestamptz not null default now();

alter table public.eletrofrio_anomaly_notes add column if not exists anomaly_id uuid;
alter table public.eletrofrio_anomaly_notes add column if not exists customer_id uuid;
alter table public.eletrofrio_anomaly_notes add column if not exists user_id text;
alter table public.eletrofrio_anomaly_notes add column if not exists author_name text;
alter table public.eletrofrio_anomaly_notes add column if not exists note text;
alter table public.eletrofrio_anomaly_notes add column if not exists created_at timestamptz not null default now();

alter table public.eletrofrio_anomaly_ai_solutions add column if not exists anomaly_id uuid;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists customer_id uuid;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists user_id text;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists solution_hash text;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists model text;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists used_ai boolean not null default false;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists cached boolean not null default false;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists prompt_context jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists solution_json jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists solution_text text;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists error_message text;
alter table public.eletrofrio_anomaly_ai_solutions add column if not exists created_at timestamptz not null default now();

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public'
      and table_name = 'eletrofrio_customers'
  ) then
    if not exists (
      select 1 from pg_constraint
      where conrelid = 'public.eletrofrio_anomaly_events'::regclass
        and conname = 'eletrofrio_anomaly_events_customer_id_fkey'
    ) then
      alter table public.eletrofrio_anomaly_events
        add constraint eletrofrio_anomaly_events_customer_id_fkey
        foreign key (customer_id) references public.eletrofrio_customers(id)
        on delete set null;
    end if;

    if not exists (
      select 1 from pg_constraint
      where conrelid = 'public.eletrofrio_anomaly_tickets'::regclass
        and conname = 'eletrofrio_anomaly_tickets_customer_id_fkey'
    ) then
      alter table public.eletrofrio_anomaly_tickets
        add constraint eletrofrio_anomaly_tickets_customer_id_fkey
        foreign key (customer_id) references public.eletrofrio_customers(id)
        on delete set null;
    end if;

    if not exists (
      select 1 from pg_constraint
      where conrelid = 'public.eletrofrio_anomaly_notes'::regclass
        and conname = 'eletrofrio_anomaly_notes_customer_id_fkey'
    ) then
      alter table public.eletrofrio_anomaly_notes
        add constraint eletrofrio_anomaly_notes_customer_id_fkey
        foreign key (customer_id) references public.eletrofrio_customers(id)
        on delete set null;
    end if;

    if not exists (
      select 1 from pg_constraint
      where conrelid = 'public.eletrofrio_anomaly_ai_solutions'::regclass
        and conname = 'eletrofrio_anomaly_ai_solutions_customer_id_fkey'
    ) then
      alter table public.eletrofrio_anomaly_ai_solutions
        add constraint eletrofrio_anomaly_ai_solutions_customer_id_fkey
        foreign key (customer_id) references public.eletrofrio_customers(id)
        on delete set null;
    end if;
  end if;
end $$;

create index if not exists idx_eletrofrio_anomalies_customer_id on public.eletrofrio_anomalies(customer_id);
create index if not exists idx_eletrofrio_anomalies_status_updated_at on public.eletrofrio_anomalies(status, updated_at desc);
create index if not exists idx_eletrofrio_anomalies_severity_updated_at on public.eletrofrio_anomalies(severity, updated_at desc);
create index if not exists idx_eletrofrio_anomalies_resolved_at on public.eletrofrio_anomalies(resolved_at);
create index if not exists idx_eletrofrio_anomalies_reopened_at on public.eletrofrio_anomalies(reopened_at);
create index if not exists idx_eletrofrio_anomalies_priority_score on public.eletrofrio_anomalies(priority_score desc);
create index if not exists idx_eletrofrio_anomalies_loja_status on public.eletrofrio_anomalies(loja_id, status);
create index if not exists idx_eletrofrio_anomalies_device_status on public.eletrofrio_anomalies(dispositivo_id, status);

create index if not exists idx_eletrofrio_anomaly_events_anomaly_id on public.eletrofrio_anomaly_events(anomaly_id);
create index if not exists idx_eletrofrio_anomaly_events_customer_id on public.eletrofrio_anomaly_events(customer_id);
create index if not exists idx_eletrofrio_anomaly_events_event_type on public.eletrofrio_anomaly_events(event_type);
create index if not exists idx_eletrofrio_anomaly_events_created_at on public.eletrofrio_anomaly_events(created_at desc);

create index if not exists idx_eletrofrio_anomaly_tickets_anomaly_id on public.eletrofrio_anomaly_tickets(anomaly_id);
create index if not exists idx_eletrofrio_anomaly_tickets_customer_id on public.eletrofrio_anomaly_tickets(customer_id);
create index if not exists idx_eletrofrio_anomaly_tickets_status on public.eletrofrio_anomaly_tickets(status);
create index if not exists idx_eletrofrio_anomaly_tickets_created_at on public.eletrofrio_anomaly_tickets(created_at desc);

create index if not exists idx_eletrofrio_anomaly_notes_anomaly_id on public.eletrofrio_anomaly_notes(anomaly_id);
create index if not exists idx_eletrofrio_anomaly_notes_customer_id on public.eletrofrio_anomaly_notes(customer_id);
create index if not exists idx_eletrofrio_anomaly_notes_created_at on public.eletrofrio_anomaly_notes(created_at desc);

create index if not exists idx_eletrofrio_anomaly_ai_solutions_anomaly_hash
on public.eletrofrio_anomaly_ai_solutions(anomaly_id, solution_hash, created_at desc);
create index if not exists idx_eletrofrio_anomaly_ai_solutions_customer_created
on public.eletrofrio_anomaly_ai_solutions(customer_id, created_at desc);
create index if not exists idx_eletrofrio_anomaly_ai_solutions_user_created
on public.eletrofrio_anomaly_ai_solutions(user_id, created_at desc);

drop trigger if exists trg_eletrofrio_anomaly_tickets_updated_at on public.eletrofrio_anomaly_tickets;
create trigger trg_eletrofrio_anomaly_tickets_updated_at
before update on public.eletrofrio_anomaly_tickets
for each row execute function public.set_eletrofrio_updated_at();
