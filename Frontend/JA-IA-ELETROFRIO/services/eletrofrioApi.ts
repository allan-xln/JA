import type {
  ApiListResponse,
  AuthLoginResponse,
  AuthUser,
  AssistantAnswer,
  CommunicationLog,
  CommunicationResponse,
  CollectorRunResult,
  CollectorRun,
  CollectorSettings,
  EletrofrioAlarm,
  EletrofrioAnomaly,
  EletrofrioDevice,
  EletrofrioHealth,
  EletrofrioInsight,
  EletrofrioOverview,
  EletrofrioTelemetry,
  EletrofrioUnit,
  NotificationEvent,
  NotificationProcessResult,
  NotificationRecipient,
  NotificationStatus,
  OperationalRule,
  OperationalSummaryResult,
  RagQueryLog,
  RuleEvaluationsResponse,
  RulesResponse,
  WhatsappMessageLog,
  WhatsappQr,
  WhatsappStatus,
} from "@/types/eletrofrio";

const AUTH_TOKEN_KEY = "eletrofrio.authToken";

const PUBLIC_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "";

function isLocalBackendUrl(url: string) {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(url);
}

function getApiBaseUrl() {
  if (typeof window !== "undefined") {
    return isLocalBackendUrl(PUBLIC_API_BASE_URL) ? "" : PUBLIC_API_BASE_URL;
  }

  return (
    process.env.SERVER_API_URL?.replace(/\/$/, "") ||
    process.env.ELETROFRIO_API_URL?.replace(/\/$/, "") ||
    PUBLIC_API_BASE_URL ||
    "http://localhost:8000"
  );
}

type RequestOptions = RequestInit & {
  next?: {
    revalidate?: number;
    tags?: string[];
  };
};

export function getAuthToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const apiBaseUrl = getApiBaseUrl();
  const url = `${apiBaseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const token = getAuthToken();

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
      cache: options.cache ?? "no-store",
    });
  } catch {
    throw new Error("Não foi possível conectar ao backend operacional. Verifique se a API está ativa e tente novamente.");
  }

  if (!response.ok) {
    let message = `Erro ${response.status} ao acessar ${endpoint}`;
    if (response.status === 401 && token) {
      setAuthToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("eletrofrio-auth-expired"));
      }
    }

    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (body?.detail?.error) {
        message = body.detail.error;
      } else if (body?.message) {
        message = body.message;
      }
    } catch {
      // Mantem a mensagem padrao quando o backend nao retorna JSON.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const eletrofrioApi = {
  login: (username: string, password: string) =>
    apiFetch<AuthLoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => apiFetch<{ user: AuthUser }>("/api/auth/me"),
  logout: () =>
    apiFetch<{ ok: boolean }>("/api/auth/logout", {
      method: "POST",
    }),
  health: () => apiFetch<EletrofrioHealth>("/api/eletrofrio/health"),
  overview: () => apiFetch<EletrofrioOverview>("/api/eletrofrio/overview"),
  units: () => apiFetch<ApiListResponse<EletrofrioUnit>>("/api/eletrofrio/units"),
  devices: () =>
    apiFetch<ApiListResponse<EletrofrioDevice>>("/api/eletrofrio/devices"),
  alarms: (limit = 120) =>
    apiFetch<ApiListResponse<EletrofrioAlarm>>(
      `/api/eletrofrio/alarms?limit=${limit}`
    ),
  telemetry: (limit = 120) =>
    apiFetch<ApiListResponse<EletrofrioTelemetry>>(
      `/api/eletrofrio/telemetry?limit=${limit}`
    ),
  insights: (limit = 80) =>
    apiFetch<ApiListResponse<EletrofrioInsight>>(
      `/api/eletrofrio/insights?limit=${limit}`
    ),
  rules: () => apiFetch<RulesResponse>("/api/eletrofrio/rules"),
  ruleEvaluations: (limit = 50) =>
    apiFetch<RuleEvaluationsResponse>(`/api/eletrofrio/rule-evaluations?limit=${limit}`),
  ruleDefaultsPreview: () =>
    apiFetch<ApiListResponse<OperationalRule>>("/api/eletrofrio/rules/defaults/preview"),
  applyRuleDefaults: () =>
    apiFetch<Record<string, unknown>>("/api/eletrofrio/rules/defaults/apply", {
      method: "POST",
    }),
  evaluateRules: () =>
    apiFetch<Record<string, unknown>>("/api/eletrofrio/rules/evaluate", {
      method: "POST",
    }),
  createRule: (payload: OperationalRule) =>
    apiFetch<OperationalRule>("/api/eletrofrio/rules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateRule: (id: string, payload: OperationalRule) =>
    apiFetch<OperationalRule>(`/api/eletrofrio/rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  toggleRule: (id: string) =>
    apiFetch<OperationalRule>(`/api/eletrofrio/rules/${id}/toggle`, {
      method: "PATCH",
    }),
  deleteRule: (id: string) =>
    apiFetch<{ deleted: boolean; rule: OperationalRule }>(`/api/eletrofrio/rules/${id}`, {
      method: "DELETE",
    }),
  assistantQuery: (question: string) =>
    apiFetch<AssistantAnswer>("/api/eletrofrio/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question, origin: "panel" }),
    }),
  assistantSuggestions: () =>
    apiFetch<ApiListResponse<string>>("/api/eletrofrio/assistant/suggestions"),
  runCollector: () =>
    apiFetch<CollectorRunResult>("/api/eletrofrio/run-collector", {
      method: "POST",
    }),
  whatsappStatus: () =>
    apiFetch<WhatsappStatus>("/api/eletrofrio/whatsapp/status"),
  whatsappQr: () => apiFetch<WhatsappQr>("/api/eletrofrio/whatsapp/qr"),
  whatsappStart: () =>
    apiFetch<WhatsappStatus>("/api/eletrofrio/whatsapp/start", {
      method: "POST",
    }),
  whatsappLogout: () =>
    apiFetch<WhatsappStatus>("/api/eletrofrio/whatsapp/logout", {
      method: "POST",
    }),
  whatsappSendTest: (phone: string, message: string) =>
    apiFetch<{ sent: boolean; dryRun: boolean; jid: string }>(
      "/api/eletrofrio/whatsapp/send-test",
      {
        method: "POST",
        body: JSON.stringify({ phone, message }),
      }
    ),
  whatsappProcessInsights: () =>
    apiFetch<Record<string, unknown>>(
      "/api/eletrofrio/whatsapp/process-insights",
      {
        method: "POST",
      }
    ),
  whatsappSendOperationalSummary: () =>
    apiFetch<OperationalSummaryResult>(
      "/api/eletrofrio/whatsapp/send-operational-summary",
      {
        method: "POST",
      }
    ),
  communications: (params: { limit?: number; offset?: number; type?: string; status?: string; search?: string } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    if (params.offset) query.set("offset", String(params.offset));
    if (params.type) query.set("type", params.type);
    if (params.status) query.set("status", params.status);
    if (params.search) query.set("search", params.search);
    return apiFetch<CommunicationResponse<CommunicationLog>>(`/api/eletrofrio/communications?${query.toString()}`);
  },
  communicationTimeline: (limit = 50) =>
    apiFetch<CommunicationResponse<CommunicationLog>>(`/api/eletrofrio/communications/timeline?limit=${limit}`),
  ragHistory: (params: { limit?: number; offset?: number; search?: string } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    if (params.offset) query.set("offset", String(params.offset));
    if (params.search) query.set("search", params.search);
    return apiFetch<CommunicationResponse<RagQueryLog>>(`/api/eletrofrio/rag/history?${query.toString()}`);
  },
  whatsappMessages: (params: { limit?: number; offset?: number; type?: string; status?: string } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    if (params.offset) query.set("offset", String(params.offset));
    if (params.type) query.set("type", params.type);
    if (params.status) query.set("status", params.status);
    return apiFetch<CommunicationResponse<WhatsappMessageLog>>(`/api/eletrofrio/whatsapp/messages?${query.toString()}`);
  },
  notificationStatus: () =>
    apiFetch<NotificationStatus>("/api/eletrofrio/notifications/status"),
  notificationProcess: () =>
    apiFetch<NotificationProcessResult>("/api/eletrofrio/notifications/process", {
      method: "POST",
    }),
  notificationEvents: (params: { limit?: number; offset?: number; status?: string } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    if (params.offset) query.set("offset", String(params.offset));
    if (params.status) query.set("status", params.status);
    return apiFetch<CommunicationResponse<NotificationEvent>>(`/api/eletrofrio/notifications/events?${query.toString()}`);
  },
  notificationRecipients: () =>
    apiFetch<CommunicationResponse<NotificationRecipient>>("/api/eletrofrio/notifications/recipients"),
  notificationCreateRecipient: (payload: Partial<NotificationRecipient> & { phone: string }) =>
    apiFetch<NotificationRecipient>("/api/eletrofrio/notifications/recipients", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  notificationUpdateRecipient: (id: string, payload: Partial<NotificationRecipient>) =>
    apiFetch<NotificationRecipient>(`/api/eletrofrio/notifications/recipients/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  notificationDeleteRecipient: (id: string) =>
    apiFetch<Record<string, unknown>>(`/api/eletrofrio/notifications/recipients/${id}`, {
      method: "DELETE",
    }),
  notificationTest: (payload: { phone?: string; recipient_id?: string; message: string; dry_run?: boolean }) =>
    apiFetch<Record<string, unknown>>("/api/eletrofrio/notifications/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  collectorSettings: () =>
    apiFetch<CollectorSettings>("/api/collector/settings"),
  collectorStatus: () =>
    apiFetch<CollectorSettings>("/api/collector/status"),
  updateCollectorSettings: (payload: {
    enabled: boolean;
    intervalMinutes: number;
    alertCooldownMinutes?: number;
  }) =>
    apiFetch<CollectorSettings>("/api/collector/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  collectorRunNow: () =>
    apiFetch<CollectorRunResult>("/api/collector/run-now", {
      method: "POST",
    }),
  collectorRuns: (limit = 20) =>
    apiFetch<ApiListResponse<CollectorRun>>(`/api/collector/runs?limit=${limit}`),
  collectorAnomalies: (limit = 50, status?: string) =>
    apiFetch<ApiListResponse<EletrofrioAnomaly>>(
      `/api/collector/anomalies?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`
    ),
  resolveAnomaly: (id: string) =>
    apiFetch<EletrofrioAnomaly>(`/api/collector/anomalies/${id}/resolve`, {
      method: "POST",
    }),
  ignoreAnomaly: (id: string) =>
    apiFetch<EletrofrioAnomaly>(`/api/collector/anomalies/${id}/ignore`, {
      method: "POST",
    }),
};
