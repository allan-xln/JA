export type Severity = "info" | "warning" | "critical" | string;

export type ApiListResponse<T> = {
  items: T[];
};

export type AuthUser = {
  username: string;
  role: "admin" | "client" | string;
  customer_id: string | null;
  customer_name: string | null;
  scope_label?: string;
  allowed_loja_ids?: number[];
  allowed_dispositivo_ids?: number[];
};

export type AuthLoginResponse = {
  token: string;
  user: AuthUser;
};

export type EletrofrioHealth = {
  status: string;
  supabase_configured: boolean;
  openai_configured: boolean;
  collector_interval_minutes: number;
  whatsapp_enabled: boolean;
  auto_open_tickets: boolean;
};

export type EletrofrioUnit = {
  id?: string;
  loja_id: number | null;
  loja_nome: string | null;
  raw_payload?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type EletrofrioDevice = {
  id?: string;
  loja_id: number | null;
  dispositivo_id: number | null;
  tag: string | null;
  raw_payload?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type EletrofrioAlarm = {
  id?: string;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  alarm_type: string | null;
  alarm_message: string | null;
  started_at: string | null;
  ended_at: string | null;
  raw_payload?: Record<string, unknown>;
  created_at?: string;
};

export type EletrofrioTelemetry = {
  id?: string;
  loja_id: number | null;
  dispositivo_id: number | null;
  tag: string | null;
  measured_at: string | null;
  temperature: number | string | null;
  raw_payload?: Record<string, unknown>;
  created_at?: string;
};

export type EletrofrioInsight = {
  id: string;
  insight_type: string;
  severity: Severity;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  title: string;
  summary: string;
  technical_reason: string | null;
  recommended_action: string | null;
  evidence_json: Record<string, unknown> | null;
  gpt_model?: string | null;
  created_at: string;
  whatsapp_sent_at: string | null;
  ticket_opened_at: string | null;
};

export type OperationalRule = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  scope_type: string;
  scope_value: string | null;
  priority: number;
  severity_when_triggered: string;
  equipment_type: string | null;
  measurement_type: string | null;
  condition_type: string;
  threshold_min: number | null;
  threshold_max: number | null;
  duration_minutes: number | null;
  recurrence_count: number | null;
  recurrence_window_minutes: number | null;
  alarm_text_pattern: string | null;
  explanation_template: string | null;
  recommended_action_template: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type RuleEvaluation = {
  id?: string;
  rule_id: string | null;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  matched: boolean;
  severity: string | null;
  score: number | null;
  evidence_json: Record<string, unknown>;
  explanation: string | null;
  recommended_action: string | null;
  evaluated_at: string;
};

export type RulesResponse = {
  schema_applied?: boolean;
  using_defaults?: boolean;
  message?: string;
  items: OperationalRule[];
};

export type RuleEvaluationsResponse = {
  schema_applied?: boolean;
  message?: string;
  items: RuleEvaluation[];
};

export type DeviceMetric = {
  dispositivo_id: number | null;
  tag: string | null;
  loja_id: number | null;
  loja_nome: string | null;
  temperature_current: number | null;
  temperature_avg: number | null;
  temperature_min: number | null;
  temperature_max: number | null;
  temperature_trend: string;
  telemetry_count: number;
  alarm_count: number;
};

export type StoreMetric = {
  loja_id: number | null;
  loja_nome: string | null;
  alarm_count: number;
  device_count?: number;
};

export type EletrofrioOverview = {
  totals: {
    units: number;
    devices: number;
    alarms: number;
    alarms_last_30_days: number;
    telemetry: number;
    insights_candidates: number;
    insights?: number;
  };
  alarms_by_type: Record<string, number>;
  device_metrics: DeviceMetric[];
  store_metrics: StoreMetric[];
  most_problematic_devices: DeviceMetric[];
  most_critical_stores: StoreMetric[];
  top_critical_devices: DeviceMetric[];
  top_critical_stores: StoreMetric[];
  latest_insights?: EletrofrioInsight[];
  scope?: AuthUser;
};

export type WhatsappStatus = {
  enabled: boolean;
  dryRun?: boolean;
  status?: string;
  connected: boolean;
  hasQr: boolean;
  lastQrAt?: string | null;
  lastConnectionAt: string | null;
  lastDisconnectReason?: string | null;
  phone: string | null;
  sessionDir: string;
  allowedRecipients?: number;
};

export type WhatsappQr = {
  hasQr: boolean;
  qr: string | null;
  dataUrl: string | null;
  lastQrAt: string | null;
  connected: boolean;
};

export type CollectorRunResult = {
  status: string;
  units?: number;
  alarms?: number;
  telemetry?: number;
  insights_count?: number;
  anomalies_count?: number;
  whatsapp_alerts_count?: number;
  warnings?: string[];
};

export type OperationalSummaryItem = {
  id?: string;
  source?: string;
  loja_nome?: string | null;
  tag?: string | null;
  severity?: string;
  reason?: string;
};

export type OperationalSummaryResult = {
  ok: boolean;
  dry_run: boolean;
  message: string;
  selected_count: number;
  sent_count: number;
  recipients?: number;
  recipient_source?: string;
  items: OperationalSummaryItem[];
  preview?: string;
};

export type CommunicationLog = {
  id: string;
  type: string;
  direction: string;
  phone: string | null;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  message_preview: string | null;
  payload_json: Record<string, unknown>;
  status: string;
  source: string;
  created_at: string;
  timeline_source?: string;
};

export type RagQueryLog = {
  id: string;
  question: string;
  answer_preview: string | null;
  answer_full: string | null;
  confidence: number | null;
  confidence_label: string | null;
  used_ai: boolean;
  sources_json: Array<Record<string, unknown>>;
  warnings_json: string[];
  customer_id?: string | null;
  customer_name?: string | null;
  response_time_ms: number | null;
  created_at: string;
};

export type WhatsappMessageLog = {
  id: string;
  phone: string | null;
  direction: string;
  type: string;
  message_preview: string | null;
  message_full: string | null;
  dry_run: boolean;
  delivery_status: string;
  customer_id?: string | null;
  customer_name?: string | null;
  created_at: string;
};

export type NotificationRecipient = {
  id: string;
  customer_id: string | null;
  role: string;
  name: string | null;
  phone: string;
  channel: string;
  enabled: boolean;
  receive_critical: boolean;
  receive_warning_recurrent: boolean;
  cooldown_minutes: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type NotificationEvent = {
  id: string;
  customer_id: string | null;
  customer_name?: string | null;
  anomaly_id: string | null;
  insight_id: string | null;
  recipient_id: string | null;
  phone: string | null;
  channel: string;
  severity: string | null;
  title: string | null;
  message_preview: string | null;
  message_full: string | null;
  status: "skipped" | "dry_run" | "sent" | "failed" | string;
  skip_reason: string | null;
  error_message: string | null;
  created_at: string;
  sent_at: string | null;
};

export type NotificationStatus = {
  schema_applied?: boolean;
  message?: string;
  dry_run: boolean;
  ai_enrichment: boolean;
  recipients: number;
  whatsapp: {
    enabled?: boolean;
    connected?: boolean;
    dryRun?: boolean;
    error?: string;
  };
  events_today: Record<string, number>;
  recent: Record<string, number>;
};

export type NotificationProcessResult = {
  schema_applied?: boolean;
  message?: string;
  checked: number;
  sent: number;
  dry_run: number;
  skipped: number;
  failed: number;
  recipients: number;
  whatsapp?: NotificationStatus["whatsapp"];
  ai_calls_used?: number;
  ai_enriched?: number;
  elapsed_ms: number;
};

export type CommunicationResponse<T> = {
  schema_applied?: boolean;
  message?: string;
  items: T[];
};

export type CollectorSettings = {
  enabled: boolean;
  intervalMinutes: number;
  alertCooldownMinutes: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  running: boolean;
  lastStatus: "success" | "error" | "running" | "never_run" | string;
  lastError: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  latestRun?: CollectorRun | null;
  lastGoodRun?: CollectorRun | null;
};

export type CollectorRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  units_count: number;
  alarms_count: number;
  telemetry_count: number;
  anomalies_count?: number;
  whatsapp_alerts_count?: number;
  trigger_source?: string | null;
  error_message: string | null;
};

export type EletrofrioAnomaly = {
  id: string;
  anomaly_key: string;
  sensor_id: string | null;
  equipment_id: number | null;
  loja_id: number | null;
  loja_nome: string | null;
  tag: string | null;
  type: string;
  severity: string;
  value: number | null;
  expected_range: Record<string, unknown> | null;
  message: string;
  technical_reason?: string | null;
  recommended_action?: string | null;
  evidence_json?: Record<string, unknown> | null;
  detected_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  status: "open" | "resolved" | "ignored" | string;
  source: string;
  metadata: Record<string, unknown>;
  whatsapp_sent_at: string | null;
  whatsapp_status: string | null;
  whatsapp_error: string | null;
};

export type AssistantAnswer = {
  answer: string;
  intent: string;
  intent_label?: string;
  confidence: number;
  confidence_label?: string;
  confidence_reason?: string;
  summary?: string;
  key_findings?: string[];
  recommended_actions?: string[];
  bullet_points?: string[];
  sources: Array<{
    type: string;
    id?: string | null;
    label: string;
    loja_nome?: string | null;
    tag?: string | null;
    timestamp?: string | null;
    relevance_reason?: string | null;
  }>;
  warnings: string[];
  model: string | null;
  used_ai: boolean;
  used_openai: boolean;
  question: string;
  scope?: AuthUser;
};
