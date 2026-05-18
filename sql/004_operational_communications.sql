create extension if not exists pgcrypto;

create table if not exists eletrofrio_communication_logs (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  direction text not null default 'system',
  phone text,
  loja_id integer,
  loja_nome text,
  dispositivo_id integer,
  tag text,
  message_preview text,
  payload_json jsonb not null default '{}'::jsonb,
  status text not null default 'received',
  source text not null default 'sistema',
  created_at timestamptz not null default now()
);

alter table eletrofrio_communication_logs add column if not exists type text not null default 'system_event';
alter table eletrofrio_communication_logs add column if not exists direction text not null default 'system';
alter table eletrofrio_communication_logs add column if not exists phone text;
alter table eletrofrio_communication_logs add column if not exists loja_id integer;
alter table eletrofrio_communication_logs add column if not exists loja_nome text;
alter table eletrofrio_communication_logs add column if not exists dispositivo_id integer;
alter table eletrofrio_communication_logs add column if not exists tag text;
alter table eletrofrio_communication_logs add column if not exists message_preview text;
alter table eletrofrio_communication_logs add column if not exists payload_json jsonb not null default '{}'::jsonb;
alter table eletrofrio_communication_logs add column if not exists status text not null default 'received';
alter table eletrofrio_communication_logs add column if not exists source text not null default 'sistema';
alter table eletrofrio_communication_logs add column if not exists created_at timestamptz not null default now();

create table if not exists eletrofrio_rag_queries (
  id uuid primary key default gen_random_uuid(),
  question text not null,
  answer_preview text,
  answer_full text,
  confidence numeric,
  confidence_label text,
  used_ai boolean not null default false,
  sources_json jsonb not null default '[]'::jsonb,
  warnings_json jsonb not null default '[]'::jsonb,
  response_time_ms integer,
  created_at timestamptz not null default now()
);

alter table eletrofrio_rag_queries add column if not exists question text not null default '';
alter table eletrofrio_rag_queries add column if not exists answer_preview text;
alter table eletrofrio_rag_queries add column if not exists answer_full text;
alter table eletrofrio_rag_queries add column if not exists confidence numeric;
alter table eletrofrio_rag_queries add column if not exists confidence_label text;
alter table eletrofrio_rag_queries add column if not exists used_ai boolean not null default false;
alter table eletrofrio_rag_queries add column if not exists sources_json jsonb not null default '[]'::jsonb;
alter table eletrofrio_rag_queries add column if not exists warnings_json jsonb not null default '[]'::jsonb;
alter table eletrofrio_rag_queries add column if not exists response_time_ms integer;
alter table eletrofrio_rag_queries add column if not exists created_at timestamptz not null default now();

create table if not exists eletrofrio_whatsapp_messages (
  id uuid primary key default gen_random_uuid(),
  phone text,
  direction text not null default 'outgoing',
  type text not null default 'manual_message',
  message_preview text,
  message_full text,
  dry_run boolean not null default false,
  delivery_status text not null default 'pending',
  created_at timestamptz not null default now()
);

alter table eletrofrio_whatsapp_messages add column if not exists phone text;
alter table eletrofrio_whatsapp_messages add column if not exists direction text not null default 'outgoing';
alter table eletrofrio_whatsapp_messages add column if not exists type text not null default 'manual_message';
alter table eletrofrio_whatsapp_messages add column if not exists message_preview text;
alter table eletrofrio_whatsapp_messages add column if not exists message_full text;
alter table eletrofrio_whatsapp_messages add column if not exists dry_run boolean not null default false;
alter table eletrofrio_whatsapp_messages add column if not exists delivery_status text not null default 'pending';
alter table eletrofrio_whatsapp_messages add column if not exists created_at timestamptz not null default now();

create index if not exists idx_eletrofrio_comm_logs_created_at on eletrofrio_communication_logs (created_at desc);
create index if not exists idx_eletrofrio_comm_logs_type on eletrofrio_communication_logs (type);
create index if not exists idx_eletrofrio_comm_logs_status on eletrofrio_communication_logs (status);
create index if not exists idx_eletrofrio_comm_logs_phone on eletrofrio_communication_logs (phone);
create index if not exists idx_eletrofrio_comm_logs_loja on eletrofrio_communication_logs (loja_id);

create index if not exists idx_eletrofrio_rag_queries_created_at on eletrofrio_rag_queries (created_at desc);
create index if not exists idx_eletrofrio_rag_queries_confidence on eletrofrio_rag_queries (confidence);

create index if not exists idx_eletrofrio_whatsapp_messages_created_at on eletrofrio_whatsapp_messages (created_at desc);
create index if not exists idx_eletrofrio_whatsapp_messages_type on eletrofrio_whatsapp_messages (type);
create index if not exists idx_eletrofrio_whatsapp_messages_status on eletrofrio_whatsapp_messages (delivery_status);
create index if not exists idx_eletrofrio_whatsapp_messages_phone on eletrofrio_whatsapp_messages (phone);
