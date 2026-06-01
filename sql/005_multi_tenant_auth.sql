-- Controle multi-cliente Eletrofrio/JA.
-- Idempotente: pode ser executado mais de uma vez no Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.eletrofrio_customers (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.eletrofrio_users (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  password_hash text not null,
  role text not null default 'client',
  customer_id uuid references public.eletrofrio_customers(id),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint eletrofrio_users_role_check check (role in ('admin', 'client'))
);

create table if not exists public.eletrofrio_customer_units (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references public.eletrofrio_customers(id) on delete cascade,
  loja_id integer not null,
  loja_nome text,
  created_at timestamptz not null default now(),
  unique(customer_id, loja_id)
);

create table if not exists public.eletrofrio_customer_devices (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references public.eletrofrio_customers(id) on delete cascade,
  dispositivo_id integer not null,
  tag text,
  loja_id integer,
  created_at timestamptz not null default now(),
  unique(customer_id, dispositivo_id)
);

create table if not exists public.eletrofrio_sessions (
  id uuid primary key default gen_random_uuid(),
  token_hash text unique not null,
  user_id uuid references public.eletrofrio_users(id) on delete cascade,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

alter table if exists public.eletrofrio_communication_logs add column if not exists customer_id uuid references public.eletrofrio_customers(id);
alter table if exists public.eletrofrio_communication_logs add column if not exists customer_name text;
alter table if exists public.eletrofrio_rag_queries add column if not exists customer_id uuid references public.eletrofrio_customers(id);
alter table if exists public.eletrofrio_rag_queries add column if not exists customer_name text;
alter table if exists public.eletrofrio_whatsapp_messages add column if not exists customer_id uuid references public.eletrofrio_customers(id);
alter table if exists public.eletrofrio_whatsapp_messages add column if not exists customer_name text;

create index if not exists idx_eletrofrio_customers_slug on public.eletrofrio_customers(slug);
create index if not exists idx_eletrofrio_users_username on public.eletrofrio_users(username);
create index if not exists idx_eletrofrio_users_customer_id on public.eletrofrio_users(customer_id);
create index if not exists idx_eletrofrio_customer_units_customer_id on public.eletrofrio_customer_units(customer_id);
create index if not exists idx_eletrofrio_customer_units_loja_id on public.eletrofrio_customer_units(loja_id);
create index if not exists idx_eletrofrio_customer_devices_customer_id on public.eletrofrio_customer_devices(customer_id);
create index if not exists idx_eletrofrio_customer_devices_dispositivo_id on public.eletrofrio_customer_devices(dispositivo_id);
create index if not exists idx_eletrofrio_sessions_token_hash on public.eletrofrio_sessions(token_hash);
create index if not exists idx_eletrofrio_sessions_expires_at on public.eletrofrio_sessions(expires_at);

do $$
begin
  if to_regclass('public.eletrofrio_communication_logs') is not null then
    create index if not exists idx_eletrofrio_comm_logs_customer_id on public.eletrofrio_communication_logs(customer_id);
  end if;
  if to_regclass('public.eletrofrio_rag_queries') is not null then
    create index if not exists idx_eletrofrio_rag_queries_customer_id on public.eletrofrio_rag_queries(customer_id);
  end if;
  if to_regclass('public.eletrofrio_whatsapp_messages') is not null then
    create index if not exists idx_eletrofrio_whatsapp_messages_customer_id on public.eletrofrio_whatsapp_messages(customer_id);
  end if;
end $$;

create or replace function public.set_eletrofrio_tenant_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_eletrofrio_customers_updated_at on public.eletrofrio_customers;
create trigger trg_eletrofrio_customers_updated_at
before update on public.eletrofrio_customers
for each row execute function public.set_eletrofrio_tenant_updated_at();

drop trigger if exists trg_eletrofrio_users_updated_at on public.eletrofrio_users;
create trigger trg_eletrofrio_users_updated_at
before update on public.eletrofrio_users
for each row execute function public.set_eletrofrio_tenant_updated_at();
