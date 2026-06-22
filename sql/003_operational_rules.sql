-- Motor de regras operacionais Eletrofrio
-- Idempotente: pode ser executado mais de uma vez no Supabase SQL Editor.

create table if not exists public.eletrofrio_operational_rules (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  enabled boolean not null default true,
  scope_type text not null default 'global',
  scope_value text,
  priority integer not null default 100,
  severity_when_triggered text not null default 'warning',
  equipment_type text,
  measurement_type text,
  condition_type text not null,
  threshold_min numeric,
  threshold_max numeric,
  duration_minutes integer,
  recurrence_count integer,
  recurrence_window_minutes integer,
  alarm_text_pattern text,
  explanation_template text,
  recommended_action_template text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.eletrofrio_operational_rules add column if not exists name text;
alter table public.eletrofrio_operational_rules add column if not exists description text;
alter table public.eletrofrio_operational_rules add column if not exists enabled boolean not null default true;
alter table public.eletrofrio_operational_rules add column if not exists scope_type text not null default 'global';
alter table public.eletrofrio_operational_rules add column if not exists scope_value text;
alter table public.eletrofrio_operational_rules add column if not exists priority integer not null default 100;
alter table public.eletrofrio_operational_rules add column if not exists severity_when_triggered text not null default 'warning';
alter table public.eletrofrio_operational_rules add column if not exists equipment_type text;
alter table public.eletrofrio_operational_rules add column if not exists measurement_type text;
alter table public.eletrofrio_operational_rules add column if not exists condition_type text not null default 'contains_text';
alter table public.eletrofrio_operational_rules add column if not exists threshold_min numeric;
alter table public.eletrofrio_operational_rules add column if not exists threshold_max numeric;
alter table public.eletrofrio_operational_rules add column if not exists duration_minutes integer;
alter table public.eletrofrio_operational_rules add column if not exists recurrence_count integer;
alter table public.eletrofrio_operational_rules add column if not exists recurrence_window_minutes integer;
alter table public.eletrofrio_operational_rules add column if not exists alarm_text_pattern text;
alter table public.eletrofrio_operational_rules add column if not exists explanation_template text;
alter table public.eletrofrio_operational_rules add column if not exists recommended_action_template text;
alter table public.eletrofrio_operational_rules add column if not exists created_at timestamptz not null default now();
alter table public.eletrofrio_operational_rules add column if not exists updated_at timestamptz not null default now();

create unique index if not exists idx_eletrofrio_operational_rules_name_unique
  on public.eletrofrio_operational_rules (name);

create index if not exists idx_eletrofrio_operational_rules_enabled
  on public.eletrofrio_operational_rules(enabled);
create index if not exists idx_eletrofrio_operational_rules_scope
  on public.eletrofrio_operational_rules(scope_type, scope_value);
create index if not exists idx_eletrofrio_operational_rules_priority
  on public.eletrofrio_operational_rules(priority);

create table if not exists public.eletrofrio_rule_evaluations (
  id uuid primary key default gen_random_uuid(),
  rule_id uuid references public.eletrofrio_operational_rules(id),
  insight_id uuid,
  alarm_id uuid,
  telemetry_id uuid,
  loja_id integer,
  loja_nome text,
  dispositivo_id integer,
  tag text,
  matched boolean not null default false,
  severity text,
  score numeric,
  evidence_json jsonb not null default '{}'::jsonb,
  explanation text,
  recommended_action text,
  evaluated_at timestamptz not null default now()
);

alter table public.eletrofrio_rule_evaluations add column if not exists rule_id uuid references public.eletrofrio_operational_rules(id);
alter table public.eletrofrio_rule_evaluations add column if not exists insight_id uuid;
alter table public.eletrofrio_rule_evaluations add column if not exists alarm_id uuid;
alter table public.eletrofrio_rule_evaluations add column if not exists telemetry_id uuid;
alter table public.eletrofrio_rule_evaluations add column if not exists loja_id integer;
alter table public.eletrofrio_rule_evaluations add column if not exists loja_nome text;
alter table public.eletrofrio_rule_evaluations add column if not exists dispositivo_id integer;
alter table public.eletrofrio_rule_evaluations add column if not exists tag text;
alter table public.eletrofrio_rule_evaluations add column if not exists matched boolean not null default false;
alter table public.eletrofrio_rule_evaluations add column if not exists severity text;
alter table public.eletrofrio_rule_evaluations add column if not exists score numeric;
alter table public.eletrofrio_rule_evaluations add column if not exists evidence_json jsonb not null default '{}'::jsonb;
alter table public.eletrofrio_rule_evaluations add column if not exists explanation text;
alter table public.eletrofrio_rule_evaluations add column if not exists recommended_action text;
alter table public.eletrofrio_rule_evaluations add column if not exists evaluated_at timestamptz not null default now();

create index if not exists idx_eletrofrio_rule_evaluations_rule_id
  on public.eletrofrio_rule_evaluations(rule_id);
create index if not exists idx_eletrofrio_rule_evaluations_dispositivo_id
  on public.eletrofrio_rule_evaluations(dispositivo_id);
create index if not exists idx_eletrofrio_rule_evaluations_loja_id
  on public.eletrofrio_rule_evaluations(loja_id);
create index if not exists idx_eletrofrio_rule_evaluations_evaluated_at
  on public.eletrofrio_rule_evaluations(evaluated_at desc);

insert into public.eletrofrio_operational_rules
  (name, description, enabled, scope_type, scope_value, priority, severity_when_triggered, equipment_type, measurement_type, condition_type, threshold_min, threshold_max, recurrence_count, recurrence_window_minutes, alarm_text_pattern, explanation_template, recommended_action_template)
values
  ('Alta temperatura em congelados', 'Protege equipamentos de congelados contra operação acima do limite esperado.', true, 'equipment_type', 'frozen', 10, 'critical', 'frozen', 'temperature', 'above', null, -12, null, null, 'alta temperatura|temperatura alta|ambiente', 'Regra violada: Alta temperatura em congelados. O alarme ou leitura indica temperatura acima do limite esperado para equipamento de congelados.', 'Verificar porta, carga térmica, evaporador, degelo, vedação e condição do sistema de refrigeração. Confirmar leitura local antes de acionar manutenção.'),
  ('Alta temperatura em resfriados', 'Identifica temperatura elevada em balcões, ilhas ou ambientes resfriados.', true, 'equipment_type', 'chilled', 20, 'warning', 'chilled', 'temperature', 'above', null, 8, null, null, 'alta temperatura|temperatura alta|ambiente', 'Regra violada: Alta temperatura em resfriados. O ativo resfriado está acima da referência operacional configurada.', 'Verificar porta, exposição, carga térmica, ventilação, sensor e condição de refrigeração.'),
  ('Faixa câmara fria resfriada', 'Valida câmara fria resfriada entre 0 C e 5 C.', true, 'equipment_type', 'cold_room_chilled', 25, 'warning', 'cold_room_chilled', 'temperature', 'outside_range', 0, 5, null, null, 'câmara fria|camara fria|resfriad', 'Regra violada: Câmara fria resfriada fora da faixa esperada de 0 C a 5 C.', 'Validar setpoint, sensor, porta, circulação de ar e condição do evaporador.'),
  ('Faixa câmara congelada', 'Valida câmara ou equipamento congelado entre -25 C e -15 C.', true, 'equipment_type', 'cold_room_frozen', 15, 'critical', 'cold_room_frozen', 'temperature', 'outside_range', -25, -15, null, null, 'câmara|camara|congelad|cf|c.f.', 'Regra violada: Câmara congelada fora da faixa esperada de -25 C a -15 C.', 'Verificar porta, vedação, degelo, evaporador, carga térmica e leitura local.'),
  ('Baixa temperatura operacional', 'Sinaliza leituras abaixo da faixa esperada e possível configuração incorreta.', true, 'global', null, 55, 'warning', null, 'temperature', 'below', -30, null, null, null, 'baixa temperatura|temperatura baixa', 'Regra violada: Baixa temperatura operacional. A leitura ou alarme aponta condição abaixo do limite de referência.', 'Verificar setpoint, sensor, controlador e risco de congelamento indevido.'),
  ('Comunicação ou equipamento offline', 'Detecta ausência de comunicação ou status offline.', true, 'alarm_group', 'communication', 30, 'warning', null, 'communication', 'contains_text', null, null, null, null, 'offline|comunicação|sem comunicação|sinal|sem sinal', 'Regra violada: Comunicação ou equipamento offline. O alarme indica perda de comunicação ou indisponibilidade do controlador.', 'Verificar alimentação, rede, sinal, comunicação e disponibilidade do controlador.'),
  ('Falha de compressor', 'Prioriza alarmes relacionados a compressor e proteção térmica.', true, 'alarm_group', 'compressor', 5, 'critical', null, 'compressor', 'contains_text', null, null, null, null, 'compressor|térmico compressor|termico compressor|falha int compressor|falha compressor', 'Regra violada: Falha de compressor. O texto do alarme indica risco em componente crítico do sistema de refrigeração.', 'Verificar compressor, proteção térmica, corrente, pressão e condição elétrica antes de liberar operação.'),
  ('Baixa pressão ou glicol', 'Sinaliza baixa pressão, pressão de sucção ou circuito de glicol.', true, 'alarm_group', 'pressure_glycol', 8, 'critical', null, 'pressure', 'contains_text', null, null, null, null, 'baixa pressão|baixa pressao|pressão sucção|pressao succao|glicol', 'Regra violada: Baixa pressão ou glicol. O alarme aponta risco no circuito de refrigeração ou circulação.', 'Verificar circuito de refrigeração, fluido, bomba, válvulas e pressão de sucção.'),
  ('MOP ou alta evaporação', 'Indica condição de evaporação elevada ou atuação MOP.', true, 'alarm_group', 'evaporation', 45, 'warning', null, 'pressure', 'contains_text', null, null, null, null, 'mop|alta temperatura de evaporação|alta temperatura de evaporacao', 'Regra violada: MOP ou alta evaporação. A operação pode estar fora do ponto de controle esperado.', 'Verificar válvula, carga térmica, evaporação e condição de operação.'),
  ('Recorrência de evento', 'Prioriza equipamentos com repetição de ocorrências em janela curta.', true, 'global', null, 12, 'critical', null, null, 'repeated_event', null, null, 3, 120, null, 'Regra violada: Recorrência de evento. O equipamento ou loja apresenta repetição de alarmes em janela operacional curta.', 'Priorizar análise técnica e acompanhar até estabilização da ocorrência.'),
  ('Telemetria ausente', 'Sinaliza ausência de leitura suficiente sem confirmar falha de equipamento.', true, 'global', null, 80, 'info', null, 'communication', 'missing_telemetry', null, null, null, null, null, 'Regra observada: Telemetria ausente. Não há leitura suficiente para confirmar condição operacional.', 'Validar comunicação do sensor antes de concluir falha no equipamento.')
on conflict (name) do nothing;
