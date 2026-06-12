"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  BellRing,
  ChevronDown,
  CheckCircle2,
  Clock3,
  Loader2,
  MessageCircle,
  Play,
  Plus,
  Power,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Sidebar, type ViewId } from "@/components/layout/sidebar";
import { useEletrofrioInsights } from "@/hooks/useEletrofrioInsights";
import { useEletrofrioOverview } from "@/hooks/useEletrofrioOverview";
import { useWhatsappStatus } from "@/hooks/useWhatsappStatus";
import { eletrofrioApi, getAuthToken, setAuthToken } from "@/services/eletrofrioApi";
import type {
  AuthUser,
  AssistantAnswer,
  CommunicationLog,
  CollectorRun,
  CollectorRunResult,
  CollectorSettings,
  DeviceMetric,
  EletrofrioAlarm,
  EletrofrioDevice,
  EletrofrioInsight,
  EletrofrioOverview,
  EletrofrioTelemetry,
  NotificationEvent,
  NotificationRecipient,
  NotificationStatus,
  OperationalRule,
  OperationalSummaryResult,
  RagQueryLog,
  RuleEvaluation,
  StoreMetric,
  WhatsappMessageLog,
} from "@/types/eletrofrio";

type WhatsappController = ReturnType<typeof useWhatsappStatus>;

const VIEW_IDS = ["dashboard", "ativos", "alertas", "inteligentes", "operacao", "regras", "whatsapp"] as const satisfies readonly ViewId[];
const VIEW_STORAGE_KEY = "eletrofrio.activeView";

const severityTone: Record<string, string> = {
  critical: "border-red-400/30 bg-red-400/10 text-red-100",
  warning: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  info: "border-sky-400/25 bg-sky-400/10 text-sky-100",
};

function isViewId(value: string | null | undefined): value is ViewId {
  return VIEW_IDS.includes(value as ViewId);
}

function viewHash(view: ViewId) {
  return `#/${view}`;
}

function viewFromBrowser(): ViewId {
  if (typeof window === "undefined") return "dashboard";
  const hashView = window.location.hash.replace(/^#\/?/, "");
  if (isViewId(hashView)) return hashView;

  const storedView = window.localStorage.getItem(VIEW_STORAGE_KEY);
  if (isViewId(storedView)) return storedView;

  return "dashboard";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("pt-BR");
}

function temperatureLabel(value: number | string | null | undefined) {
  if (value == null || value === "") return "-";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(1)} C` : "-";
}

function assistantIntentLabel(answer: AssistantAnswer) {
  return answer.intent_label || answer.intent.replaceAll("_", " ");
}

function confidenceTone(label?: string) {
  if (label === "Alta") return "border-emerald-400/25 bg-emerald-400/[0.09] text-emerald-100";
  if (label === "Média") return "border-amber-400/25 bg-amber-400/[0.09] text-amber-100";
  return "border-sky-400/25 bg-sky-400/[0.09] text-sky-100";
}

function severityLabel(value: string | null | undefined) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["critical", "critico", "crítico", "c"].includes(normalized)) return "Crítica";
  if (["high", "alta", "a"].includes(normalized)) return "Alta prioridade";
  if (["medium", "media", "média", "warning", "m"].includes(normalized)) return "Atenção";
  if (["low", "baixa", "b"].includes(normalized)) return "Monitoramento";
  return "Informativo";
}

const ALARM_PRIORITY_BUCKETS = [
  {
    action: "Atender agora",
    label: "Risco alto",
    helper: "Pode impactar produto, temperatura segura ou operação.",
    sourceLabel: "Origem: alarmes críticos ou de alta prioridade.",
    codes: ["A", "C"],
    includeUnknown: false,
    bar: "bg-red-300",
  },
  {
    action: "Validar hoje",
    label: "Requer atenção",
    helper: "Precisa de conferência operacional no mesmo turno.",
    sourceLabel: "Origem: alarmes que exigem validação no turno.",
    codes: ["M"],
    includeUnknown: false,
    bar: "bg-amber-300",
  },
  {
    action: "Acompanhar",
    label: "Monitoramento",
    helper: "Observar recorrência antes de acionar manutenção.",
    sourceLabel: "Origem: alarmes para acompanhamento operacional.",
    codes: ["B"],
    includeUnknown: false,
    bar: "bg-sky-300",
  },
  {
    action: "Registrar",
    label: "Informativo",
    helper: "Sem ação imediata, mas útil para histórico.",
    sourceLabel: "Origem: registros informativos ou sem prioridade explícita.",
    codes: ["I"],
    includeUnknown: true,
    bar: "bg-slate-300",
  },
] as const;

const KNOWN_ALARM_TYPE_CODES: ReadonlySet<string> = new Set(ALARM_PRIORITY_BUCKETS.flatMap((bucket) => bucket.codes));

function alarmPriorityBreakdown(alarmsByType: Record<string, number>) {
  const normalized: Record<string, number> = Object.fromEntries(
    Object.entries(alarmsByType).map(([type, count]) => [type.trim().toUpperCase(), Number(count || 0)]),
  );
  const unknownCodes = Object.keys(normalized).filter((code) => code && !KNOWN_ALARM_TYPE_CODES.has(code));

  return ALARM_PRIORITY_BUCKETS.map((bucket) => {
    const sourceCodes = bucket.includeUnknown ? [...bucket.codes, ...unknownCodes] : [...bucket.codes];
    const count = sourceCodes.reduce((sum, code) => sum + (normalized[code] || 0), 0);

    return {
      ...bucket,
      sourceCodes,
      count,
    };
  });
}

function evidencePreview(evidence: Record<string, unknown> | null) {
  if (!evidence) return "Sem evidências estruturadas disponíveis.";
  if (evidence.rule_name) {
    return `Regra: ${String(evidence.rule_name)} | evidência ${evidenceLevelLabel(String(evidence.evidence_level || ""))}`;
  }
  const source = String(evidence.evidence_source || "dados operacionais");
  const enough = evidence.sufficient_evidence === false ? "evidência parcial" : "evidência suficiente";
  return `${source} | ${enough}`;
}

function evidenceString(evidence: Record<string, unknown> | null, key: string, fallback = "-") {
  const value = evidence?.[key];
  return value == null || value === "" ? fallback : String(value);
}

function evidenceNumber(evidence: Record<string, unknown> | null, key: string) {
  const value = Number(evidence?.[key]);
  return Number.isFinite(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function equipmentTypeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    frozen: "Equipamento de congelados",
    cold_room_frozen: "Câmara congelada",
    chilled: "Equipamento resfriado",
    cold_room_chilled: "Câmara resfriada",
    refrigeration_system: "Sistema de refrigeração",
    preparation_area: "Área de preparo",
    glycol_system: "Sistema de glicol",
    unknown: "Não classificado",
  };
  return labels[String(value || "unknown")] || "Não classificado";
}

function evidenceLevelLabel(value?: string | null) {
  const labels: Record<string, string> = {
    weak: "Fraca",
    medium: "Média",
    strong: "Forte",
  };
  return labels[String(value || "").toLowerCase()] || "Operacional";
}

function operationalPriorityView(value: number | null) {
  if (value == null) {
    return {
      label: "Sem urgência definida",
      helper: "Ainda não há dados suficientes para ordenar essa ocorrência.",
      scoreText: "-",
      percent: 0,
      tone: "border-slate-200 bg-slate-100 text-slate-600",
      bar: "bg-slate-300",
    };
  }

  const score = Math.max(0, Math.min(100, Math.round(value)));

  if (score >= 80) {
    return {
      label: "Atender primeiro",
      helper: "Risco alto ou evidência forte. Priorize essa ocorrência.",
      scoreText: `Urgência ${score}/100`,
      percent: score,
      tone: "border-red-300/25 bg-red-300/10 text-red-100",
      bar: "bg-red-300",
    };
  }

  if (score >= 55) {
    return {
      label: "Acompanhar hoje",
      helper: "Existe sinal relevante. Valide no turno atual.",
      scoreText: `Urgência ${score}/100`,
      percent: score,
      tone: "border-amber-300/25 bg-amber-300/10 text-amber-100",
      bar: "bg-amber-300",
    };
  }

  return {
    label: "Monitorar",
    helper: "Baixo risco no recorte atual. Mantenha em observação.",
    scoreText: `Urgência ${score}/100`,
    percent: score,
    tone: "border-sky-300/20 bg-sky-300/10 text-sky-100",
    bar: "bg-sky-300",
  };
}

function operationalSummaryText(insight: EletrofrioInsight) {
  const summary = insight.summary || "";
  if (!summary.toLowerCase().includes("análise gerada por regras determinísticas")) {
    return summary || "Ocorrência operacional identificada no recorte monitorado.";
  }

  const evidence = insight.evidence_json || {};
  const alarm = evidence.alarm as Record<string, unknown> | undefined;
  const deviceSummary = evidence.device_alarm_summary as Record<string, unknown> | undefined;
  const storeMetrics = evidence.store_metrics as Record<string, unknown> | undefined;
  const alarmMessage = String(alarm?.alarm_message || alarm?.alarm_type || "");
  const tag = insight.tag || String(alarm?.tag || deviceSummary?.tag || "");
  const loja = insight.loja_nome || String(alarm?.loja_nome || storeMetrics?.loja_nome || "");

  if (alarmMessage) {
    return `Evidência operacional registrada: ${alarmMessage}${tag ? ` no equipamento ${tag}` : ""}${loja ? ` da loja ${loja}` : ""}.`;
  }
  if (tag) {
    return `Equipamento ${tag} apresenta recorrência ou comportamento que exige acompanhamento${loja ? ` na loja ${loja}` : ""}.`;
  }
  if (loja) {
    return `Loja ${loja} concentra ocorrências no recorte analisado.`;
  }
  return "Ocorrência operacional identificada no recorte monitorado.";
}

function cleanOperationalText(value: string | null | undefined, fallback: string) {
  const text = String(value || "").trim();
  if (!text) return fallback;
  return text
    .replace(/não há confirmação automática de causa raiz\.?/gi, "")
    .replace(/evidências estruturadas indicam severidade\s+\w+\.?/gi, "")
    .replace(/evidência suficiente\.?/gi, "evidência operacional")
    .replace(/\s{2,}/g, " ")
    .trim() || fallback;
}

function firstKnownString(...values: unknown[]) {
  for (const value of values) {
    if (value != null && String(value).trim()) return String(value).trim();
  }
  return "";
}

function firstKnownNumber(...values: unknown[]) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function occurrenceExpectedRangeByType(ruleName: string, equipmentType: string, title: string) {
  const text = `${ruleName} ${equipmentType} ${title}`.toLowerCase();
  if (text.includes("câmara congelada") || text.includes("camara congelada") || text.includes("cold_room_frozen")) {
    return { min: -25, max: -15, label: "-25 C até -15 C" };
  }
  if (text.includes("congel")) {
    return { min: null, max: -12, label: "até -12 C" };
  }
  if (text.includes("câmara fria") || text.includes("camara fria") || text.includes("cold_room_chilled")) {
    return { min: 0, max: 5, label: "0 C até 5 C" };
  }
  if (text.includes("resfriad") || text.includes("chilled")) {
    return { min: null, max: 8, label: "até 8 C" };
  }
  if (text.includes("baixa temperatura")) {
    return { min: -30, max: null, label: "acima de -30 C" };
  }
  return { min: null, max: null, label: "Definida pela regra operacional" };
}

function occurrenceDeviationLabel(value: number | null, min: number | null, max: number | null) {
  if (value == null) return "Confirmado por alarme, recorrência ou regra textual.";
  if (min != null && value < min) return `${(min - value).toFixed(1)} C abaixo do limite mínimo operacional.`;
  if (max != null && value > max) return `${(value - max).toFixed(1)} C acima do limite máximo operacional.`;
  return "Sem desvio numérico no recorte; prioridade sustentada por alarme ou recorrência.";
}

function occurrenceConfidenceLabel(score: number | null, evidenceLevel: string) {
  const normalized = evidenceLevel.toLowerCase();
  if (normalized === "strong" || normalized === "forte" || (score != null && score >= 78)) return "Alta";
  if (normalized === "medium" || normalized === "média" || normalized === "media" || (score != null && score >= 58)) return "Média";
  return "Baixa";
}

function occurrenceRiskText(title: string, ruleName: string, equipmentType: string, deviation: string) {
  const text = `${title} ${ruleName} ${equipmentType}`.toLowerCase();
  if (text.includes("compressor")) return "Possível atuação de proteção térmica, desgaste prematuro ou parada do conjunto de refrigeração.";
  if (text.includes("offline") || text.includes("comunica")) return "Perda de visibilidade remota do equipamento até validar alimentação, rede ou controlador.";
  if (text.includes("press") || text.includes("glicol")) return "Risco de instabilidade no circuito de refrigeração, circulação ou pressão de sucção.";
  if (deviation.includes("abaixo")) return "Possível congelamento indevido, sensor descalibrado ou setpoint fora do padrão operacional.";
  if (text.includes("congel")) return "Risco de produto congelado fora da condição segura se a ocorrência persistir.";
  if (text.includes("temperatura")) return "Risco de conservação fora da faixa esperada e necessidade de validação local da leitura.";
  return "Prioridade operacional definida por regra técnica e histórico recente do ativo.";
}

function occurrencePriorityBoost(insight: EletrofrioInsight) {
  const evidence = insight.evidence_json || {};
  const context = asRecord(evidence.context);
  const storeMetrics = asRecord(evidence.store_metrics);
  const deviceMetrics = asRecord(evidence.device_alarm_summary || evidence.device_metrics);
  return (
    (evidenceNumber(evidence, "operational_score") ?? 0) +
    (firstKnownNumber(context.recurrence_count, evidence.recurrence_count, deviceMetrics.alarm_count) ?? 0) * 8 +
    (firstKnownNumber(storeMetrics.alarm_count) ?? 0) * 2
  );
}

function occurrenceAnalysis(insight: EletrofrioInsight) {
  const evidence = insight.evidence_json || {};
  const analysis = asRecord(evidence.operational_analysis);
  const expected = asRecord(analysis.expected_range);
  const deviation = asRecord(analysis.deviation);
  const alarm = asRecord(evidence.alarm);
  const telemetry = asRecord(evidence.telemetry);
  const context = asRecord(evidence.context);
  const ruleName = evidenceString(evidence, "rule_name", "");
  const equipmentType = evidenceString(evidence, "inferred_equipment_type", "unknown");
  const expectedFallback = occurrenceExpectedRangeByType(ruleName, equipmentType, insight.title);
  const currentValue = firstKnownNumber(
    analysis.current_value,
    context.telemetry_value,
    telemetry.temperature,
    evidence.value,
  );
  const minValue = firstKnownNumber(expected.min, expectedFallback.min);
  const maxValue = firstKnownNumber(expected.max, expectedFallback.max);
  const expectedLabel = firstKnownString(analysis.expected_range_label, expected.label, expectedFallback.label);
  const deviationLabel = firstKnownString(
    analysis.deviation_label,
    deviation.label,
    occurrenceDeviationLabel(currentValue, minValue, maxValue),
  );
  const score = evidenceNumber(evidence, "operational_score");
  const evidenceLevel = evidenceString(evidence, "evidence_level", "");
  const originLabel = firstKnownString(
    analysis.origin_label,
    insight.insight_type === "telemetry" ? "telemetria + regras operacionais" : "",
    alarm.alarm_message || alarm.alarm_type ? "alarmes + regras operacionais" : "",
    "regras operacionais",
  );
  const sensor = firstKnownString(
    analysis.sensor,
    telemetry.sensor_id,
    alarm.sensor_id,
    currentValue != null ? `TEMP_${insight.dispositivo_id ?? "OPERACIONAL"}` : `ALARME_${insight.dispositivo_id ?? insight.loja_id ?? "OPERACIONAL"}`,
  );
  const problemType = firstKnownString(analysis.problem_type, ruleName, insight.title);
  const technicalReason = cleanOperationalText(
    firstKnownString(analysis.technical_reason, insight.technical_reason, evidenceString(evidence, "rule_based_reason", "")),
    `${problemType}: ocorrência comparada com regra técnica e histórico recente.`,
  );
  const operationalEvidence = cleanOperationalText(
    firstKnownString(analysis.operational_evidence, operationalSummaryText(insight)),
    "Dados recentes sustentam a prioridade operacional.",
  );
  const risk = firstKnownString(analysis.risk, occurrenceRiskText(insight.title, ruleName, equipmentType, deviationLabel));
  const currentValueLabel = firstKnownString(
    analysis.current_value_label,
    currentValue == null ? "Sem leitura numérica vinculada" : `${currentValue.toFixed(1)} C`,
  );

  return {
    problemType,
    sensor,
    currentValueLabel,
    expectedLabel,
    deviationLabel,
    technicalReason,
    operationalEvidence,
    risk,
    action: cleanOperationalText(insight.recommended_action, "Validar leitura local, condição do equipamento e histórico antes de acionar manutenção."),
    confidence: firstKnownString(analysis.confidence_label, occurrenceConfidenceLabel(score, evidenceLevel)),
    originLabel,
    equipmentTypeLabel: equipmentTypeLabel(equipmentType),
    score,
    ruleName: ruleName || "Regra operacional",
  };
}

function phoneFromWhatsappJid(value?: string | null) {
  if (!value) return "";
  return value.split("@", 1)[0].split(":", 1)[0].replace(/\D/g, "");
}

type RecipientFormState = {
  name: string;
  phone: string;
  role: string;
  customer_id: string;
  enabled: boolean;
  receive_critical: boolean;
  receive_warning_recurrent: boolean;
  cooldown_minutes: number;
};

const emptyRecipientForm: RecipientFormState = {
  name: "",
  phone: "",
  role: "client",
  customer_id: "",
  enabled: true,
  receive_critical: true,
  receive_warning_recurrent: true,
  cooldown_minutes: 60,
};

function recipientPayload(form: RecipientFormState) {
  return {
    name: form.name.trim() || null,
    phone: form.phone.trim(),
    role: form.role || "client",
    customer_id: form.customer_id.trim() || null,
    enabled: form.enabled,
    receive_critical: form.receive_critical,
    receive_warning_recurrent: form.receive_warning_recurrent,
    cooldown_minutes: Math.max(5, Number(form.cooldown_minutes) || 60),
    channel: "whatsapp",
  };
}

function minutesUntil(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const minutes = Math.ceil((date.getTime() - Date.now()) / 60000);
  if (minutes <= 0) return "agora";
  if (minutes === 1) return "em 1 minuto";
  return `em ${minutes} minutos`;
}

function minutesSince(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.floor((Date.now() - date.getTime()) / 60000);
}

function isStaleRunningRun(run?: CollectorRun | null) {
  if (!run || run.status !== "running") return false;
  const age = minutesSince(run.started_at);
  return age != null && age > 60;
}

function isCollectorActuallyRunning(settings?: CollectorSettings | null) {
  if (!settings?.running) return false;
  return !isStaleRunningRun(settings.latestRun);
}

function collectorStatusLabel(settings?: CollectorSettings | null) {
  if (!settings) return "aguardando backend";
  if (isStaleRunningRun(settings.latestRun)) return "interrompida";
  if (isCollectorActuallyRunning(settings)) return "executando";
  if (settings.lastStatus === "success") return "operacional";
  if (settings.lastStatus === "partial_success") return "operacional com cache";
  if (settings.lastStatus === "error") return "atenção";
  if (settings.enabled) return "programada";
  return "desativada";
}

function collectorRunLabel(run: CollectorRun) {
  if (run.status === "success") return "Coleta concluída com sucesso";
  if (run.status === "partial_success") return "Coleta concluída com dados cacheados";
  if (run.status === "running" && isStaleRunningRun(run)) return "Coleta interrompida";
  if (run.status === "running") return "Coleta em andamento";
  return "Coleta com falha";
}

function triggerSourceLabel(value?: string | null) {
  if (value === "loop" || value === "schedule") return "automática";
  if (value === "manual_cli") return "terminal";
  return "manual";
}

function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`panel-surface rounded-xl border border-white/10 bg-white/[0.82] p-3 shadow-sm sm:p-4 ${className}`}
    >
      {children}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-white/12 bg-white/[0.55] p-8 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <section className="rounded-xl border border-red-400/25 bg-red-400/10 p-5 text-red-100 shadow-sm">
      <p className="text-sm font-semibold">Atenção operacional</p>
      <p className="mt-2 text-sm text-red-100/80">{message}</p>
    </section>
  );
}

function LoginView({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      const result = await eletrofrioApi.login(username, password);
      setAuthToken(result.token);
      onLogin(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="industrial-ui grid min-h-screen place-items-center px-4 text-slate-800">
      <form onSubmit={submit} className="login-card grid w-full max-w-sm gap-4 rounded-2xl border border-white/10 bg-white/[0.86] p-5">
        <div>
          <div className="mb-4 rounded-xl bg-white p-3 shadow-sm">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/eletrofrio-logo.png"
              alt="Eletrofrio Refrigeração"
              className="h-auto w-full object-contain"
            />
          </div>
          <h1 className="text-2xl font-semibold">Eletrofrio</h1>
          <p className="mt-1 text-sm text-white/55">Acesse seu ambiente operacional.</p>
        </div>
        {error ? <ErrorBanner message={error} /> : null}
        <label className="grid gap-2">
          <span className="text-sm text-white/60">Usuário</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm outline-none" autoComplete="username" />
        </label>
        <label className="grid gap-2">
          <span className="text-sm text-white/60">Senha</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm outline-none" autoComplete="current-password" />
        </label>
        <button type="submit" disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-400/15 disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Entrar
        </button>
      </form>
    </main>
  );
}

function operationalErrorLabel(value?: string | null) {
  if (!value) return "";
  const text = value.toLowerCase();
  if (text.includes("timeout na api eletrofrio: unidades")) {
    return "O endpoint oficial de unidades não respondeu dentro do tempo. A rotina pode continuar usando o último snapshot salvo no Supabase quando houver cache disponível.";
  }
  if (text.includes("endpoint de unidades temporariamente indisponível")) {
    return "O endpoint oficial de unidades oscilou; a coleta usou dados cacheados do Supabase para manter a operação visível.";
  }
  if (text.includes("endpoint de alarmes temporariamente indisponível")) {
    return "O endpoint oficial de alarmes oscilou; a coleta usou dados cacheados do Supabase para manter a operação visível.";
  }
  if (text.includes("read timed out") || text.includes("statement timeout")) {
    return "A sincronização excedeu o tempo limite do Supabase. A coleta parcial foi registrada; execute uma nova sincronização após alguns instantes.";
  }
  if (text.includes("supabase 500")) {
    return "O Supabase interrompeu uma consulta longa. Os dados parciais foram preservados e a próxima coleta pode continuar a rotina.";
  }
  if (text.includes("httpsconnectionpool")) {
    return "Houve instabilidade de comunicação com o Supabase durante a coleta. Tente sincronizar novamente.";
  }
  return value;
}

function MetricCard({
  label,
  value,
  helper,
  tone = "cyan",
}: {
  label: string;
  value: string | number;
  helper: string;
  tone?: "cyan" | "emerald" | "amber" | "red";
}) {
  const toneClass = {
    cyan: "text-sky-300",
    emerald: "text-emerald-300",
    amber: "text-amber-300",
    red: "text-red-300",
  }[tone];

  return (
    <article className="rounded-xl border border-white/10 bg-white/[0.82] p-3 shadow-sm sm:p-4">
      <p className="text-sm font-medium text-slate-400">{label}</p>
      <h3 className="mt-2 text-xl font-semibold sm:text-2xl">{value}</h3>
      <p className={`mt-2 text-sm ${toneClass}`}>{helper}</p>
    </article>
  );
}

function LoadingState({ text }: { text: string }) {
  return (
    <div className="loading-shell rounded-xl border border-white/10 bg-white/[0.82] p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-700">Preparando visão operacional</p>
          <p className="mt-1 text-sm text-slate-500">{text}</p>
        </div>
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="loading-step-dot" />
          <span className="loading-step-dot" />
          <span className="loading-step-dot" />
        </div>
      </div>
      <div className="mt-4 loading-meter" />
      <div className="loading-signal-grid mt-4" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((item) => (
          <span key={item} />
        ))}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {[0, 1, 2].map((item) => (
          <div key={item} className="skeleton-card h-28 rounded-xl border border-white/10 p-4">
            <span className="skeleton-line w-20" />
            <span className="skeleton-line mt-6 h-6 w-24" />
            <span className="skeleton-line mt-4 w-32" />
          </div>
        ))}
      </div>
    </div>
  );
}

function LoadingSplash({ text }: { text: string }) {
  return (
    <main className="industrial-ui grid min-h-screen place-items-center px-4 text-slate-800">
      <div className="loading-shell w-full max-w-sm rounded-xl border border-white/10 bg-white/[0.86] p-5 text-center shadow-xl">
        <div className="loading-brand-mark mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-sky-100 bg-white text-sky-700 shadow-sm">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
        <p className="mt-4 text-sm font-semibold text-slate-800">Carregando ambiente</p>
        <p className="mt-1 text-sm text-slate-500">{text}</p>
        <div className="mt-5 loading-meter" />
        <div className="loading-signal-grid mt-4" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((item) => (
            <span key={item} />
          ))}
        </div>
      </div>
    </main>
  );
}

function DashboardView({
  overview,
  loading,
  onRefresh,
  onRunCollector,
  collectorBusy,
  collectorMessage,
  whatsappConnected,
  canRunCollector,
}: {
  overview: ReturnType<typeof useEletrofrioOverview>["overview"];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onRunCollector: () => Promise<void>;
  collectorBusy: boolean;
  collectorMessage: string | null;
  whatsappConnected: boolean;
  canRunCollector: boolean;
}) {
  const totals = overview?.totals;
  const alarmsByType = overview?.alarms_by_type || {};
  const alarmPriorityRows = alarmPriorityBreakdown(alarmsByType);
  const totalTypedAlarms = alarmPriorityRows.reduce((sum, item) => sum + item.count, 0);
  const maxAlarmType = Math.max(1, ...alarmPriorityRows.map((item) => item.count));
  const topStore = overview?.most_critical_stores?.[0];
  const latestInsights = overview?.latest_insights || [];

  return (
    <div className="flex flex-col gap-4">
      <Panel className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">Visão geral</h1>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void onRefresh()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-semibold text-white/80 transition hover:bg-white/[0.08]"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
          {canRunCollector ? (
            <button
              type="button"
              onClick={() => void onRunCollector()}
              disabled={collectorBusy}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-400/20 bg-white/[0.055] px-4 py-3 text-sm font-semibold text-sky-100 transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {collectorBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Sincronizar agora
            </button>
          ) : null}
        </div>
      </Panel>

      {collectorMessage ? (
        <div className="rounded-2xl border border-emerald-400/25 bg-emerald-400/[0.09] p-4 text-sm text-emerald-100">
          {collectorMessage}
        </div>
      ) : null}

      {loading && !overview ? (
        <LoadingState text="Sincronizando dados operacionais..." />
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Unidades" value={totals?.units ?? "-"} helper="lojas monitoradas" tone="emerald" />
        <MetricCard label="Equipamentos" value={totals?.devices ?? "-"} helper="ativos monitorados" />
        <MetricCard label="Ocorrências" value={totals?.alarms ?? "-"} helper={`${totals?.alarms_last_30_days ?? 0} no recorte recente`} tone="amber" />
        <MetricCard label="Telemetria" value={totals?.telemetry ?? "-"} helper="leituras processadas" />
        <MetricCard label="Prioridades" value={totals?.insights ?? latestInsights.length ?? "-"} helper="itens acionáveis" tone="red" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_420px]">
        <Panel>
          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-xl font-semibold">Prioridade dos alarmes</h3>
            </div>
            <div className="rounded-md border border-white/10 bg-white/[0.055] px-3 py-2 text-sm font-semibold text-white/70">
              {totalTypedAlarms || totals?.alarms || 0} alarmes
            </div>
          </div>
          {totalTypedAlarms ? (
            <div className="space-y-4">
              {alarmPriorityRows.map((item) => {
                const percent = item.count > 0 ? Math.max(6, (item.count / maxAlarmType) * 100) : 0;

                return (
                  <div key={item.action}>
                    <div className="mb-2 flex items-center justify-between gap-4 text-sm">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-white">{item.action}</span>
                          <span className="rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-white/65">{item.label}</span>
                        </div>
                        <p className="mt-0.5 text-xs text-white/50">{item.helper}</p>
                        <p className="mt-0.5 text-xs text-white/35">{item.sourceLabel}</p>
                      </div>
                      <span className="shrink-0 text-base font-semibold text-white">{item.count} alarmes</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/8">
                      <div
                        className={`h-full rounded-full ${item.bar}`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState text="Sem ocorrências agregadas para exibir." />
          )}
        </Panel>

        <Panel>
          <h3 className="text-xl font-semibold">
            {topStore?.loja_nome || "Operação sem concentração relevante"}
          </h3>
          <p className="mt-3 text-sm leading-6 text-white/60">
            {topStore
              ? `${topStore.alarm_count} ocorrências associadas no recorte analisado.`
              : "Nenhuma loja aparece com concentração crítica no momento."}
          </p>
          <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <p className="text-sm text-white/55">WhatsApp</p>
            <p className={`mt-2 text-lg font-semibold ${whatsappConnected ? "text-emerald-300" : "text-amber-300"}`}>
              {whatsappConnected ? "Online" : "Aguardando QR"}
            </p>
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <TopStores stores={overview?.most_critical_stores || []} />
        <LatestInsights insights={latestInsights} />
      </section>
    </div>
  );
}

function TopStores({ stores }: { stores: StoreMetric[] }) {
  return (
    <Panel>
      <h3 className="text-xl font-semibold">Lojas com maior atenção</h3>
      <div className="mt-5 space-y-3">
        {stores.length ? (
          stores.slice(0, 6).map((store) => (
            <div key={`${store.loja_id}-${store.loja_nome}`} className="flex items-center justify-between gap-3 rounded-xl bg-white/[0.04] p-3 transition hover:bg-white/[0.06] sm:p-4">
              <div className="min-w-0">
                <p className="font-semibold text-white">{store.loja_nome || `Loja ${store.loja_id}`}</p>
                <p className="mt-1 text-sm text-white/50">ID {store.loja_id ?? "-"}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-lg font-semibold text-amber-300">{store.alarm_count}</p>
                <p className="text-xs text-white/45">ocorrências</p>
              </div>
            </div>
          ))
        ) : (
          <EmptyState text="Sem concentração crítica no momento." />
        )}
      </div>
    </Panel>
  );
}

function LatestInsights({ insights }: { insights: EletrofrioInsight[] }) {
  return (
    <Panel>
      <h3 className="text-xl font-semibold">Registros operacionais</h3>
      <div className="mt-5 space-y-3">
        {insights.length ? (
          insights.slice(0, 5).map((insight) => (
            <article key={insight.id} className={`rounded-xl border p-3 sm:p-4 ${severityTone[insight.severity] || severityTone.info}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold">{insight.title}</p>
                  <p className="mt-1 text-sm opacity-80">{insight.loja_nome || `Loja ${insight.loja_id ?? "-"}`}</p>
                </div>
                <span className="rounded-full bg-black/15 px-3 py-1 text-xs">
                  {severityLabel(insight.severity)}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 opacity-90">{insight.summary}</p>
            </article>
          ))
        ) : (
          <EmptyState text="Sem registros recentes para exibir." />
        )}
      </div>
    </Panel>
  );
}

function AssetsView({
  devices,
  alarms,
  telemetry,
  overviewDevices,
}: {
  devices: EletrofrioDevice[];
  alarms: EletrofrioAlarm[];
  telemetry: EletrofrioTelemetry[];
  overviewDevices: DeviceMetric[];
}) {
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(120);
  const alarmCountByDevice = useMemo(() => {
    const map = new Map<number, number>();
    alarms.forEach((alarm) => {
      if (alarm.dispositivo_id == null) return;
      map.set(alarm.dispositivo_id, (map.get(alarm.dispositivo_id) || 0) + 1);
    });
    return map;
  }, [alarms]);

  const latestTelemetryByDevice = useMemo(() => {
    const map = new Map<number, EletrofrioTelemetry>();
    telemetry.forEach((item) => {
      if (item.dispositivo_id == null) return;
      const current = map.get(item.dispositivo_id);
      if (!current || String(item.measured_at || "") > String(current.measured_at || "")) {
        map.set(item.dispositivo_id, item);
      }
    });
    return map;
  }, [telemetry]);

  const metricsByDevice = useMemo(() => {
    return new Map(overviewDevices.map((item) => [item.dispositivo_id, item]));
  }, [overviewDevices]);

  const filtered = devices.filter((device) => {
    const text = `${device.tag || ""} ${device.loja_id || ""} ${device.dispositivo_id || ""}`.toLowerCase();
    return text.includes(query.toLowerCase());
  });
  const visibleDevices = filtered.slice(0, visibleCount);

  useEffect(() => {
    setVisibleCount(120);
  }, [query]);

  return (
    <div className="flex flex-col gap-6">
      <Panel className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            Ativos monitorados
          </h1>
        </div>
        <label className="relative block w-full md:max-w-sm">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filtrar por loja, tag ou ID"
            className="w-full rounded-xl border border-white/10 bg-white/[0.055] py-3 pl-11 pr-4 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-sky-300/40"
          />
        </label>
      </Panel>

      <Panel>
        <div className="grid gap-3 md:hidden">
          {visibleDevices.map((device) => {
            const latest = device.dispositivo_id == null ? null : latestTelemetryByDevice.get(device.dispositivo_id);
            const metric = metricsByDevice.get(device.dispositivo_id);
            const alarmCount =
              metric?.alarm_count ||
              (device.dispositivo_id == null ? 0 : alarmCountByDevice.get(device.dispositivo_id)) ||
              0;
            return (
              <article key={`${device.dispositivo_id}-${device.tag}-mobile`} className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs text-white/45">Dispositivo {device.dispositivo_id ?? "-"}</p>
                    <h3 className="mt-1 break-words text-base font-semibold text-white">{device.tag || "-"}</h3>
                    <p className="mt-1 text-sm text-white/60">{metric?.loja_nome || device.loja_id || "-"}</p>
                  </div>
                  <span className="shrink-0 rounded-md border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-xs font-semibold text-amber-100">
                    {alarmCount} ocorr.
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <InfoTile label="Última leitura" value={formatDate(latest?.measured_at)} />
                  <InfoTile label="Temperatura" value={temperatureLabel(latest?.temperature ?? metric?.temperature_current)} />
                </div>
              </article>
            );
          })}
          {!filtered.length ? <EmptyState text="Nenhum dispositivo encontrado para o filtro atual." /> : null}
        </div>

        <div className="hidden overflow-x-auto md:block">
          <table className="min-w-full border-separate border-spacing-y-2">
            <thead>
              <tr className="text-left text-sm text-white/45">
                <th className="px-3 py-2">Dispositivo</th>
                <th className="px-3 py-2">Loja</th>
                <th className="px-3 py-2">Tag</th>
                <th className="px-3 py-2">Ocorrências</th>
                <th className="px-3 py-2">Ultima telemetria</th>
                <th className="px-3 py-2">Temperatura</th>
              </tr>
            </thead>
            <tbody>
              {visibleDevices.map((device) => {
                const latest = device.dispositivo_id == null ? null : latestTelemetryByDevice.get(device.dispositivo_id);
                const metric = metricsByDevice.get(device.dispositivo_id);
                const alarmCount =
                  metric?.alarm_count ||
                  (device.dispositivo_id == null ? 0 : alarmCountByDevice.get(device.dispositivo_id)) ||
                  0;
                return (
                  <tr key={`${device.dispositivo_id}-${device.tag}`} className="bg-white/[0.04] text-sm transition hover:bg-white/[0.06]">
                    <td className="rounded-l-xl px-3 py-4 font-semibold text-white">{device.dispositivo_id ?? "-"}</td>
                    <td className="px-3 py-4 text-white/70">{metric?.loja_nome || device.loja_id || "-"}</td>
                    <td className="px-3 py-4 text-white/70">{device.tag || "-"}</td>
                    <td className="px-3 py-4 text-amber-200">{alarmCount}</td>
                    <td className="px-3 py-4 text-white/60">{formatDate(latest?.measured_at)}</td>
                    <td className="rounded-r-xl px-3 py-4 text-white/70">{temperatureLabel(latest?.temperature ?? metric?.temperature_current)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!filtered.length ? <EmptyState text="Nenhum dispositivo encontrado para o filtro atual." /> : null}
        </div>
        {filtered.length > visibleDevices.length ? (
          <div className="mt-4 flex justify-center">
            <button
              type="button"
              onClick={() => setVisibleCount((count) => count + 120)}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-semibold text-white/75 transition hover:bg-white/[0.08]"
            >
              <ChevronDown className="h-4 w-4" />
              Carregar mais ativos ({visibleDevices.length}/{filtered.length})
            </button>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function InsightsView({ insights }: { insights: EletrofrioInsight[] }) {
  const [query, setQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [periodFilter, setPeriodFilter] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortBy, setSortBy] = useState("priority");
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryResult, setSummaryResult] = useState<OperationalSummaryResult | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const severityOptions = [
    { value: "all", label: "Todas" },
    { value: "critical", label: "Críticas" },
    { value: "warning", label: "Atenção" },
    { value: "info", label: "Informativas" },
  ];

  const now = useMemo(() => Date.now(), []);
  const filteredInsights = useMemo(() => {
    const search = query.trim().toLowerCase();
    const from = fromDate ? new Date(`${fromDate}T00:00:00`).getTime() : null;
    const to = toDate ? new Date(`${toDate}T23:59:59`).getTime() : null;
    const periodStart =
      periodFilter === "today"
        ? new Date(new Date().toDateString()).getTime()
        : periodFilter === "7d"
          ? now - 7 * 24 * 60 * 60 * 1000
          : periodFilter === "30d"
            ? now - 30 * 24 * 60 * 60 * 1000
            : null;

    return insights
      .filter((insight) => {
        const createdAt = new Date(insight.created_at).getTime();
        const evidence = insight.evidence_json || {};
        const text = [
          insight.title,
          insight.summary,
          insight.technical_reason,
          insight.recommended_action,
          insight.loja_nome,
          insight.tag,
          evidenceString(evidence, "rule_name", ""),
          equipmentTypeLabel(evidenceString(evidence, "inferred_equipment_type", "unknown")),
        ]
          .join(" ")
          .toLowerCase();

        if (severityFilter !== "all" && insight.severity !== severityFilter) return false;
        if (periodStart && (!Number.isFinite(createdAt) || createdAt < periodStart)) return false;
        if (from && (!Number.isFinite(createdAt) || createdAt < from)) return false;
        if (to && (!Number.isFinite(createdAt) || createdAt > to)) return false;
        if (search && !text.includes(search)) return false;
        return true;
      })
      .sort((a, b) => {
        const severityDiff = severityRankForUi(b.severity) - severityRankForUi(a.severity);
        if (severityDiff) return severityDiff;

        const priorityDiff = occurrencePriorityBoost(b) - occurrencePriorityBoost(a);
        if (priorityDiff) return priorityDiff;

        if (sortBy === "recent") {
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        if (sortBy === "score") {
          return (
            (evidenceNumber(b.evidence_json, "operational_score") ?? 0) -
            (evidenceNumber(a.evidence_json, "operational_score") ?? 0)
          );
        }
        return (
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
      });
  }, [fromDate, insights, now, periodFilter, query, severityFilter, sortBy, toDate]);

  const criticalCount = insights.filter((item) => item.severity === "critical").length;
  const warningCount = insights.filter((item) => item.severity === "warning").length;
  const infoCount = insights.filter((item) => item.severity === "info").length;
  const hasFilters = Boolean(query || severityFilter !== "all" || periodFilter !== "all" || fromDate || toDate);

  const clearFilters = () => {
    setQuery("");
    setSeverityFilter("all");
    setPeriodFilter("all");
    setFromDate("");
    setToDate("");
    setSortBy("priority");
  };

  const sendWhatsappSummary = async () => {
    try {
      setSummaryBusy(true);
      setSummaryError(null);
      setSummaryResult(null);
      const result = await eletrofrioApi.whatsappSendOperationalSummary();
      setSummaryResult(result);
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Não foi possível enviar o resumo para WhatsApp.");
    } finally {
      setSummaryBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl">Ocorrências</h1>
          </div>
          <div className="grid gap-3 lg:min-w-[640px]">
            <div className="grid gap-2 sm:grid-cols-4">
              <InfoTile label="Total" value={insights.length} />
              <InfoTile label="Críticas" value={criticalCount} />
              <InfoTile label="Atenção" value={warningCount} />
              <InfoTile label="Informativas" value={infoCount} />
            </div>
            <button
              type="button"
              onClick={() => void sendWhatsappSummary()}
              disabled={summaryBusy || !insights.length}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {summaryBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageCircle className="h-4 w-4" />}
              Enviar resumo para WhatsApp
            </button>
          </div>
        </div>
      </Panel>

      {summaryResult ? (
        <div className={`rounded-xl border p-4 text-sm ${summaryResult.ok ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100" : "border-amber-400/25 bg-amber-400/10 text-amber-100"}`}>
          <p className="font-semibold">
            {summaryResult.dry_run ? "Resumo simulado em modo validação." : "Resumo enviado para WhatsApp."}
          </p>
          <p className="mt-1 opacity-80">
            {summaryResult.message} Selecionados: {summaryResult.selected_count}. Enviados: {summaryResult.sent_count}.
          </p>
        </div>
      ) : null}

      {summaryError ? (
        <div className="rounded-xl border border-red-400/25 bg-red-400/10 p-4 text-sm text-red-100">
          {summaryError}
        </div>
      ) : null}

      <Panel>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1.2fr)_180px_180px_160px_160px_180px_auto]">
          <label className="grid gap-2">
            <span className="text-xs text-white/45">Buscar</span>
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.045] px-3 py-2">
              <Search className="h-4 w-4 text-white/35" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Loja, equipamento, regra..."
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none"
              />
            </div>
          </label>

          <label className="grid gap-2">
            <span className="text-xs text-white/45">Prioridade</span>
            <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none">
              {severityOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-xs text-white/45">Período</span>
            <select value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none">
              <option value="all">Todos</option>
              <option value="today">Hoje</option>
              <option value="7d">Últimos 7 dias</option>
              <option value="30d">Últimos 30 dias</option>
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-xs text-white/45">De</span>
            <input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none" />
          </label>

          <label className="grid gap-2">
            <span className="text-xs text-white/45">Até</span>
            <input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none" />
          </label>

          <label className="grid gap-2">
            <span className="text-xs text-white/45">Ordenar</span>
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none">
              <option value="priority">Prioridade</option>
              <option value="recent">Mais recentes</option>
              <option value="score">Maior urgência</option>
            </select>
          </label>

          <div className="flex items-end sm:col-span-2 xl:col-span-1">
            <button type="button" onClick={clearFilters} disabled={!hasFilters} className="w-full rounded-xl border border-white/10 bg-white/[0.045] px-4 py-2 text-sm font-semibold text-white/70 disabled:opacity-40">
              Limpar
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {severityOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setSeverityFilter(option.value)}
              className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${
                severityFilter === option.value
                  ? "border-sky-300/30 bg-sky-300/10 text-sky-100"
                  : "border-white/10 bg-white/[0.035] text-white/55"
              }`}
            >
              {option.label}
            </button>
          ))}
          <span className="w-full text-xs text-white/45 sm:ml-auto sm:w-auto">
            Mostrando {filteredInsights.length} de {insights.length}
          </span>
        </div>
      </Panel>

      <div className="grid gap-4">
        {filteredInsights.length ? (
          filteredInsights.map((insight) => {
            const analysis = occurrenceAnalysis(insight);
            const priority = operationalPriorityView(analysis.score);
            return (
              <article key={insight.id} className={`rounded-xl border p-3 sm:p-4 ${severityTone[insight.severity] || severityTone.info}`}>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs font-semibold">
                        {severityLabel(insight.severity)}
                      </span>
                      <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs">
                        Confiança {analysis.confidence}
                      </span>
                      <div className={`min-w-[220px] rounded-lg border px-3 py-2 ${priority.tone}`}>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-semibold">{priority.label}</span>
                          <span className="text-[11px] opacity-80">{priority.scoreText}</span>
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/25">
                          <div className={`h-full rounded-full ${priority.bar}`} style={{ width: `${priority.percent}%` }} />
                        </div>
                        <p className="mt-1 text-[11px] opacity-80">{priority.helper}</p>
                      </div>
                    </div>
                    <h3 className="mt-3 text-xl font-semibold">{analysis.problemType}</h3>
                    <p className="mt-2 text-sm opacity-75">
                      {insight.loja_nome || `Loja ${insight.loja_id ?? "-"}`} - {insight.tag || `Dispositivo ${insight.dispositivo_id ?? "-"}`}
                    </p>
                  </div>
                  <p className="shrink-0 text-sm opacity-70">{formatDate(insight.created_at)}</p>
                </div>

                <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-lg border border-white/10 bg-black/10 p-3">
                    <p className="text-xs opacity-55">Sensor causador</p>
                    <p className="mt-1 break-words text-sm font-semibold">{analysis.sensor}</p>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/10 p-3">
                    <p className="text-xs opacity-55">Leitura encontrada</p>
                    <p className="mt-1 text-sm font-semibold">{analysis.currentValueLabel}</p>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/10 p-3">
                    <p className="text-xs opacity-55">Faixa esperada</p>
                    <p className="mt-1 text-sm font-semibold">{analysis.expectedLabel}</p>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/10 p-3">
                    <p className="text-xs opacity-55">Desvio</p>
                    <p className="mt-1 text-sm font-semibold">{analysis.deviationLabel}</p>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-3">
                  <div>
                    <p className="text-xs opacity-55">Motivo técnico</p>
                    <p className="mt-2 text-sm leading-6 opacity-90">{compactText(analysis.technicalReason, "-", 230)}</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-55">Evidência operacional</p>
                    <p className="mt-2 text-sm leading-6 opacity-90">{compactText(analysis.operationalEvidence, "-", 220)}</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-55">Risco operacional</p>
                    <p className="mt-2 text-sm leading-6 opacity-90">{compactText(analysis.risk, "-", 220)}</p>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-white/10 bg-black/10 p-3">
                  <p className="text-xs opacity-55">Ação recomendada</p>
                  <p className="mt-2 text-sm font-semibold leading-6 opacity-95">{compactText(analysis.action, "-", 260)}</p>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-xs opacity-85">
                  <span className="rounded-md bg-black/15 px-3 py-2">Regra: {analysis.ruleName}</span>
                  <span className="rounded-md bg-black/15 px-3 py-2">Tipo: {analysis.equipmentTypeLabel}</span>
                  <span className="rounded-md bg-black/15 px-3 py-2">Origem: {analysis.originLabel}</span>
                  <span className="rounded-md bg-black/15 px-3 py-2">Loja: {insight.loja_nome || insight.loja_id || "-"}</span>
                  <span className="rounded-md bg-black/15 px-3 py-2">Equipamento: {compactText(insight.tag, insight.dispositivo_id ? `Dispositivo ${insight.dispositivo_id}` : "-", 56)}</span>
                </div>
              </article>
          );
          })
        ) : (
          <EmptyState text={insights.length ? "Nenhuma ocorrência encontrada com os filtros atuais." : "Nenhuma ocorrência priorizada encontrada."} />
        )}
      </div>
    </div>
  );
}

function AssistantView({ embedded = false }: { embedded?: boolean }) {
  const [question, setQuestion] = useState("Resumo da operação agora");
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([
    "Resumo operacional",
    "Ocorrências abertas",
    "Lojas críticas",
    "Equipamentos offline",
    "Status da loja Sítio Cercado",
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    eletrofrioApi
      .assistantSuggestions()
      .then((result) => {
        if (active && result.items.length) {
          setSuggestions(result.items);
        }
      })
      .catch(() => {
        // Mantem os atalhos locais caso o backend esteja indisponivel.
      });
    return () => {
      active = false;
    };
  }, []);

  const ask = async (nextQuestion = question) => {
    const trimmed = nextQuestion.trim();
    if (trimmed.length < 4) {
      setError("Digite uma pergunta operacional mais especifica.");
      return;
    }

    try {
      setBusy(true);
      setError(null);
      setAnswer(null);
      const result = await eletrofrioApi.assistantQuery(trimmed);
      setAnswer(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar o diagnóstico agora. Verifique se o backend está ativo.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {!embedded ? (
        <Panel>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            Diagnóstico operacional
          </h1>
        </Panel>
      ) : null}

      {error ? <ErrorBanner message={error} /> : null}

      <Panel>
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-xl font-semibold">
              Consulta de status e prioridade
            </h3>
          </div>
        </div>

        <div className="grid gap-4">
          <label className="grid gap-2">
            <span className="text-sm text-white/60">Pergunta operacional</span>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={2}
              className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm text-white outline-none placeholder:text-white/35 focus:border-sky-300/40"
            />
          </label>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <button
              type="button"
              disabled={busy}
              onClick={() => void ask()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-400/15 disabled:opacity-60 sm:w-auto"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Consultar operação
            </button>
            {busy ? <span className="text-sm text-white/50">Consultando dados operacionais...</span> : null}
            <div className="flex flex-wrap gap-2">
            {suggestions.map((item) => (
              <button
                key={item}
                type="button"
                disabled={busy}
                onClick={() => {
                  setQuestion(item);
                  void ask(item);
                }}
                className="rounded-xl border border-white/10 bg-white/[0.045] px-3 py-2 text-xs font-semibold text-white/70 transition hover:bg-white/[0.07] disabled:opacity-60"
              >
                {item}
              </button>
            ))}
            </div>
          </div>
        </div>
      </Panel>

      {answer ? (
        <Panel>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-white/45">
                Síntese operacional
              </p>
              <h3 className="mt-2 text-xl font-semibold">
                Confiabilidade {answer.confidence_label || "operacional"} — {Math.round(answer.confidence * 100)}%
              </h3>
              <p className="mt-1 text-sm text-white/50">
                Tipo de consulta: {assistantIntentLabel(answer)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${confidenceTone(answer.confidence_label)}`}>
                {answer.confidence_reason || "Resposta baseada no recorte operacional disponível."}
              </span>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${answer.used_ai ? "border-emerald-400/25 bg-emerald-400/[0.09] text-emerald-100" : "border-amber-400/25 bg-amber-400/[0.09] text-amber-100"}`}>
                {answer.used_ai ? "síntese assistida" : "regras locais"}
              </span>
            </div>
          </div>
          <p className="mt-5 max-w-5xl text-sm leading-6 text-white/78">
            {answer.summary || answer.answer}
          </p>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-white/45">
                Principais evidências
              </p>
              <div className="mt-3 grid gap-2">
                {(answer.key_findings?.length ? answer.key_findings : answer.bullet_points || []).length ? (
                  (answer.key_findings?.length ? answer.key_findings : answer.bullet_points || []).map((item) => (
                    <div key={item} className="rounded-xl bg-white/[0.045] px-3 py-2 text-sm leading-6 text-white/72">
                      {item}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-white/55">Nenhuma evidência direta encontrada.</p>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-white/45">
                Ações recomendadas
              </p>
              <div className="mt-3 grid gap-2">
                {answer.recommended_actions?.length ? (
                  answer.recommended_actions.map((item) => (
                    <div key={item} className="rounded-xl bg-emerald-400/[0.07] px-3 py-2 text-sm leading-6 text-emerald-50/85">
                      {item}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-white/55">Sem recomendação adicional para esta consulta.</p>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-white/45">
                Fontes consultadas
              </p>
              <div className="mt-3 grid gap-2">
                {answer.sources.length ? (
                  answer.sources.map((source, index) => (
                    <div key={`${source.type}-${source.id || index}`} className="rounded-xl bg-white/[0.045] px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2 text-sm text-white/78">
                        <span>{source.label}</span>
                        <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] uppercase tracking-[0.12em] text-white/40">
                          {source.type}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-white/48">
                        {[source.loja_nome, source.tag, source.timestamp ? formatDate(source.timestamp) : null].filter(Boolean).join(" / ")}
                      </p>
                      {source.relevance_reason ? (
                        <p className="mt-1 text-xs leading-5 text-white/55">{source.relevance_reason}</p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-white/55">Nenhuma fonte direta encontrada.</p>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-white/45">
                Avisos de evidência
              </p>
              <div className="mt-3 grid gap-2">
                {answer.warnings.length ? (
                  answer.warnings.map((warning) => (
                    <div key={warning} className="rounded-xl bg-amber-400/[0.08] px-3 py-2 text-sm leading-6 text-amber-100/85">
                      {warning}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-white/55">Nenhum aviso relevante para esta resposta.</p>
                )}
              </div>
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function WhatsappView({ whatsapp, canManage }: { whatsapp: WhatsappController; canManage: boolean }) {
  const [phone, setPhone] = useState("");
  const [testMessage, setTestMessage] = useState(
    "Validação do canal operacional Eletrofrio."
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [communicationSearch, setCommunicationSearch] = useState("");
  const [communicationType, setCommunicationType] = useState("");
  const [communicationStatus, setCommunicationStatus] = useState("");
  const [communications, setCommunications] = useState<CommunicationLog[]>([]);
  const [timeline, setTimeline] = useState<CommunicationLog[]>([]);
  const [ragHistory, setRagHistory] = useState<RagQueryLog[]>([]);
  const [messageHistory, setMessageHistory] = useState<WhatsappMessageLog[]>([]);
  const [notificationStatus, setNotificationStatus] = useState<NotificationStatus | null>(null);
  const [notificationEvents, setNotificationEvents] = useState<NotificationEvent[]>([]);
  const [notificationRecipients, setNotificationRecipients] = useState<NotificationRecipient[]>([]);
  const [notificationBusy, setNotificationBusy] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState<string | null>(null);
  const [recipientForm, setRecipientForm] = useState<RecipientFormState>(emptyRecipientForm);
  const [editingRecipientId, setEditingRecipientId] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const connectedPhone = phoneFromWhatsappJid(whatsapp.status?.phone);
  const visibleError = localError || whatsapp.error;
  const today = new Date().toDateString();
  const messagesToday = messageHistory.filter((item) => new Date(item.created_at).toDateString() === today).length;
  const lastSentMessage = messageHistory.find((item) => item.direction === "outgoing");
  const answeredToday = ragHistory.filter((item) => new Date(item.created_at).toDateString() === today).length;
  const visibleCommunications = useMemo(() => {
    const seen = new Set<string>();
    return communications.filter((item) => {
      const createdAt = new Date(item.created_at);
      const minuteKey = Number.isNaN(createdAt.getTime()) ? item.created_at : createdAt.toISOString().slice(0, 16);
      const key = [
        item.type,
        item.status,
        item.source,
        item.phone || "",
        item.message_preview || "",
        minuteKey,
      ].join("|");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [communications]);
  const notificationCounts = notificationStatus?.events_today || {};
  const notificationOnline = Boolean(notificationStatus?.whatsapp?.connected);
  const notificationDryRun = Boolean(notificationStatus?.dry_run || notificationStatus?.whatsapp?.dryRun);

  const typeLabel = (value?: string | null) => {
    const labels: Record<string, string> = {
      incoming_question: "Pergunta recebida",
      rag_response: "Resposta operacional",
      operational_alert: "Alerta operacional",
      operational_summary: "Resumo operacional",
      manual_message: "Mensagem manual",
      system_event: "Evento do canal",
      rag_query: "Consulta RAG",
    };
    return labels[value || ""] || value || "Evento";
  };

  const statusLabel = (value?: string | null) => {
    const labels: Record<string, string> = {
      sent: "Enviado",
      received: "Recebido",
      failed: "Falhou",
      "dry-run": "Dry-run",
      dry_run: "Dry-run",
      skipped: "Ignorado",
      answered: "Respondido",
      connected: "Conectado",
      disconnected: "Desconectado",
      qr_generated: "QR gerado",
    };
    return labels[value || ""] || value || "-";
  };

  const loadCommunicationHistory = async () => {
    try {
      setHistoryLoading(true);
      setHistoryError(null);
      const [
        communicationsResult,
        timelineResult,
        ragResult,
        messagesResult,
        notificationsStatusResult,
        notificationEventsResult,
        notificationRecipientsResult,
      ] = await Promise.all([
        eletrofrioApi.communications({
          limit: 50,
          type: communicationType || undefined,
          status: communicationStatus || undefined,
          search: communicationSearch || undefined,
        }),
        eletrofrioApi.communicationTimeline(50),
        eletrofrioApi.ragHistory({ limit: 50, search: communicationSearch || undefined }),
        eletrofrioApi.whatsappMessages({ limit: 50 }),
        eletrofrioApi.notificationStatus(),
        eletrofrioApi.notificationEvents({ limit: 50 }),
        eletrofrioApi.notificationRecipients(),
      ]);
      setCommunications(communicationsResult.items);
      setTimeline(timelineResult.items);
      setRagHistory(ragResult.items);
      setMessageHistory(messagesResult.items);
      setNotificationStatus(notificationsStatusResult);
      setNotificationEvents(notificationEventsResult.items);
      setNotificationRecipients(notificationRecipientsResult.items);
      const schemaMessage =
        communicationsResult.message ||
        timelineResult.message ||
        ragResult.message ||
        messagesResult.message ||
        notificationsStatusResult.message ||
        notificationEventsResult.message ||
        notificationRecipientsResult.message;
      if (schemaMessage) setHistoryError(schemaMessage);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Não foi possível carregar o histórico de comunicação.");
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (!phone && connectedPhone) {
      setPhone(connectedPhone);
    }
  }, [connectedPhone, phone]);

  useEffect(() => {
    void loadCommunicationHistory();
    const interval = setInterval(() => {
      void loadCommunicationHistory();
    }, 15000);
    return () => clearInterval(interval);
  }, [communicationSearch, communicationStatus, communicationType]);

  const sendValidation = () => {
    const targetPhone = phone.trim() || connectedPhone;
    if (!targetPhone) {
      setLocalError("Informe um telefone com DDD ou conecte um aparelho para usar o número da sessão.");
      return;
    }

    setLocalError(null);
    void whatsapp.runAction(
      () => eletrofrioApi.whatsappSendTest(targetPhone, testMessage),
      (result) =>
        result.sent
          ? `Mensagem enviada para ${result.jid}.`
          : result.dryRun
            ? `Modo validação ativo: mensagem não enviada. Seria entregue para ${result.jid}.`
            : "Mensagem processada, mas não houve confirmação de envio."
    );
    setTimeout(() => void loadCommunicationHistory(), 1200);
  };

  const processNotificationQueue = async () => {
    try {
      setNotificationBusy(true);
      setNotificationMessage(null);
      const result = await eletrofrioApi.notificationProcess();
      setNotificationMessage(
        `Processadas: ${result.checked} analisadas, ${result.sent} enviadas, ${result.dry_run} dry-run, ${result.skipped} ignoradas, ${result.failed} falhas, ${result.ai_calls_used || 0} chamadas de IA.`
      );
      await loadCommunicationHistory();
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : "Não foi possível processar notificações.");
    } finally {
      setNotificationBusy(false);
    }
  };

  const sendNotificationDryRunTest = async () => {
    const targetPhone = phone.trim() || connectedPhone;
    if (!targetPhone) {
      setNotificationMessage("Informe um telefone com DDD ou conecte um aparelho para usar o número da sessão.");
      return;
    }

    try {
      setNotificationBusy(true);
      setNotificationMessage(null);
      await eletrofrioApi.notificationTest({
        phone: targetPhone,
        message: testMessage,
        dry_run: true,
      });
      setNotificationMessage("Teste de notificação registrado em modo dry-run.");
      await loadCommunicationHistory();
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : "Não foi possível registrar o teste.");
    } finally {
      setNotificationBusy(false);
    }
  };

  const resetRecipientForm = () => {
    setEditingRecipientId(null);
    setRecipientForm(emptyRecipientForm);
  };

  const editRecipient = (recipient: NotificationRecipient) => {
    setEditingRecipientId(recipient.id);
    setRecipientForm({
      name: recipient.name || "",
      phone: recipient.phone || "",
      role: recipient.role || "client",
      customer_id: recipient.customer_id || "",
      enabled: Boolean(recipient.enabled),
      receive_critical: Boolean(recipient.receive_critical),
      receive_warning_recurrent: Boolean(recipient.receive_warning_recurrent),
      cooldown_minutes: recipient.cooldown_minutes || 60,
    });
  };

  const saveRecipient = async () => {
    const payload = recipientPayload(recipientForm);
    if (!payload.phone) {
      setNotificationMessage("Informe o telefone do destinatário.");
      return;
    }

    try {
      setNotificationBusy(true);
      setNotificationMessage(null);
      if (editingRecipientId) {
        await eletrofrioApi.notificationUpdateRecipient(editingRecipientId, payload);
        setNotificationMessage("Destinatário atualizado.");
      } else {
        await eletrofrioApi.notificationCreateRecipient(payload);
        setNotificationMessage("Destinatário criado.");
      }
      resetRecipientForm();
      await loadCommunicationHistory();
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : "Não foi possível salvar o destinatário.");
    } finally {
      setNotificationBusy(false);
    }
  };

  const toggleRecipient = async (recipient: NotificationRecipient) => {
    try {
      setNotificationBusy(true);
      setNotificationMessage(null);
      await eletrofrioApi.notificationUpdateRecipient(recipient.id, { enabled: !recipient.enabled });
      setNotificationMessage(recipient.enabled ? "Destinatário desativado." : "Destinatário ativado.");
      await loadCommunicationHistory();
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : "Não foi possível alterar o destinatário.");
    } finally {
      setNotificationBusy(false);
    }
  };

  const removeRecipient = async (recipientId: string) => {
    try {
      setNotificationBusy(true);
      setNotificationMessage(null);
      await eletrofrioApi.notificationDeleteRecipient(recipientId);
      if (editingRecipientId === recipientId) resetRecipientForm();
      setNotificationMessage("Destinatário removido.");
      await loadCommunicationHistory();
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : "Não foi possível remover o destinatário.");
    } finally {
      setNotificationBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl">WhatsApp</h1>
          </div>
          <button
            type="button"
            disabled={historyLoading}
            onClick={() => void loadCommunicationHistory()}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.045] px-4 py-3 text-sm font-semibold text-white/75 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${historyLoading ? "animate-spin" : ""}`} />
            Atualizar central
          </button>
        </div>
      </Panel>

      {visibleError ? <ErrorBanner message={visibleError} /> : null}
      {historyError ? <ErrorBanner message={historyError} /> : null}
      {whatsapp.message ? (
        <div className="rounded-2xl border border-emerald-400/25 bg-emerald-400/[0.09] p-4 text-sm text-emerald-100">
          {whatsapp.message}
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-7">
        <StatusCard label="WhatsApp" value={whatsapp.status?.connected ? "Online" : "Offline"} tone={whatsapp.status?.connected ? "success" : "warning"} />
        <StatusCard label="Número conectado" value={connectedPhone || "Não conectado"} tone={connectedPhone ? "success" : "muted"} />
        <StatusCard label="Última sincronização" value={whatsapp.status?.lastConnectionAt ? formatDate(whatsapp.status.lastConnectionAt) : "Sem conexão"} tone={whatsapp.status?.lastConnectionAt ? "success" : "muted"} />
        <StatusCard label="Modo" value={whatsapp.status?.dryRun ? "Dry-run" : "Envio real"} tone={whatsapp.status?.dryRun ? "warning" : "success"} />
        <StatusCard label="Última mensagem" value={lastSentMessage ? formatDate(lastSentMessage.created_at) : "Sem envio"} tone={lastSentMessage ? "success" : "muted"} />
        <StatusCard label="Mensagens hoje" value={messagesToday} tone={messagesToday ? "success" : "muted"} />
        <StatusCard label="Consultas hoje" value={answeredToday} tone={answeredToday ? "success" : "muted"} />
      </section>

      <Panel>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-xl font-semibold">Alertas automáticos</h3>
            <p className="mt-2 text-sm leading-6 text-white/55">
              Envia apenas ocorrências relevantes, respeitando cliente, cooldown e duplicidade.
            </p>
          </div>
          {canManage ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                disabled={notificationBusy}
                onClick={() => void processNotificationQueue()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15 disabled:opacity-60"
              >
                {notificationBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageCircle className="h-4 w-4" />}
                Processar agora
              </button>
              <button
                type="button"
                disabled={notificationBusy}
                onClick={() => void sendNotificationDryRunTest()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-semibold text-white/75 transition hover:bg-white/[0.08] disabled:opacity-60"
              >
                <Send className="h-4 w-4" />
                Teste dry-run
              </button>
            </div>
          ) : null}
        </div>
        {notificationMessage ? (
          <div className="mt-4 rounded-xl border border-sky-300/20 bg-sky-300/10 px-4 py-3 text-sm text-sky-100">
            {notificationMessage}
          </div>
        ) : null}
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatusCard label="Motor" value={notificationOnline ? "WhatsApp online" : "Sem conexão"} tone={notificationOnline ? "success" : "warning"} />
          <StatusCard label="Modo" value={notificationDryRun ? "Dry-run" : "Envio real"} tone={notificationDryRun ? "warning" : "success"} />
          <StatusCard label="Destinatários" value={notificationStatus?.recipients ?? notificationRecipients.length} tone={notificationRecipients.length ? "success" : "muted"} />
          <StatusCard label="Hoje" value={`${notificationCounts.sent || 0} env. / ${notificationCounts.dry_run || 0} dry-run`} tone={(notificationCounts.sent || notificationCounts.dry_run) ? "success" : "muted"} />
        </div>
        <div className="mt-5 grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
            <div className="flex items-center justify-between gap-3">
              <h4 className="font-semibold text-white">Destinatários</h4>
              <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs text-white/55">{notificationRecipients.length}</span>
            </div>
            {canManage ? (
              <div className="mt-4 grid gap-3 rounded-lg border border-white/10 bg-black/10 p-3">
                <div className="grid gap-2">
                  <input
                    value={recipientForm.name}
                    onChange={(event) => setRecipientForm((form) => ({ ...form, name: event.target.value }))}
                    placeholder="Nome"
                    className="w-full rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm text-white outline-none placeholder:text-white/35"
                  />
                  <input
                    value={recipientForm.phone}
                    onChange={(event) => setRecipientForm((form) => ({ ...form, phone: event.target.value }))}
                    placeholder="Telefone com DDD"
                    className="w-full rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm text-white outline-none placeholder:text-white/35"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={recipientForm.role}
                    onChange={(event) => setRecipientForm((form) => ({ ...form, role: event.target.value }))}
                    className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white outline-none"
                  >
                    <option value="client">Cliente</option>
                    <option value="admin">Admin</option>
                  </select>
                  <input
                    type="number"
                    min={5}
                    value={recipientForm.cooldown_minutes}
                    onChange={(event) => setRecipientForm((form) => ({ ...form, cooldown_minutes: Number(event.target.value) }))}
                    className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm text-white outline-none"
                  />
                </div>
                <input
                  value={recipientForm.customer_id}
                  onChange={(event) => setRecipientForm((form) => ({ ...form, customer_id: event.target.value }))}
                  placeholder="Customer ID vazio para admin"
                  className="w-full rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm text-white outline-none placeholder:text-white/35"
                />
                <div className="grid gap-2 text-xs text-white/65">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={recipientForm.enabled}
                      onChange={(event) => setRecipientForm((form) => ({ ...form, enabled: event.target.checked }))}
                    />
                    Ativo
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={recipientForm.receive_critical}
                      onChange={(event) => setRecipientForm((form) => ({ ...form, receive_critical: event.target.checked }))}
                    />
                    Receber críticas
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={recipientForm.receive_warning_recurrent}
                      onChange={(event) => setRecipientForm((form) => ({ ...form, receive_warning_recurrent: event.target.checked }))}
                    />
                    Receber recorrências
                  </label>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={notificationBusy}
                    onClick={() => void saveRecipient()}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-60"
                  >
                    <Save className="h-4 w-4" />
                    {editingRecipientId ? "Salvar" : "Adicionar"}
                  </button>
                  {editingRecipientId ? (
                    <button
                      type="button"
                      onClick={resetRecipientForm}
                      className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm font-semibold text-white/70"
                    >
                      Cancelar
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
            <div className="mt-4 grid gap-3">
              {notificationRecipients.length ? notificationRecipients.slice(0, 20).map((item) => (
                <div key={item.id} className="rounded-lg border border-white/10 bg-black/10 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{item.name || item.phone}</p>
                      <p className="mt-1 text-xs text-white/45">{item.phone} / {item.role || "cliente"}</p>
                    </div>
                    <span className={`rounded-md px-2 py-1 text-xs ${item.enabled ? "bg-emerald-400/10 text-emerald-200" : "bg-white/10 text-white/45"}`}>
                      {item.enabled ? "ativo" : "inativo"}
                    </span>
                  </div>
                  {canManage ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={notificationBusy}
                        onClick={() => editRecipient(item)}
                        className="rounded-md border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-semibold text-white/70 disabled:opacity-60"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        disabled={notificationBusy}
                        onClick={() => void toggleRecipient(item)}
                        className="rounded-md border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-semibold text-white/70 disabled:opacity-60"
                      >
                        {item.enabled ? "Desativar" : "Ativar"}
                      </button>
                      <button
                        type="button"
                        disabled={notificationBusy}
                        onClick={() => void removeRecipient(item.id)}
                        className="rounded-md border border-red-400/20 bg-red-400/10 px-2.5 py-1 text-xs font-semibold text-red-100 disabled:opacity-60"
                      >
                        Remover
                      </button>
                    </div>
                  ) : null}
                </div>
              )) : (
                <EmptyState text="Nenhum destinatário configurado." />
              )}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
            <div className="flex items-center justify-between gap-3">
              <h4 className="font-semibold text-white">Auditoria recente</h4>
              <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs text-white/55">{notificationEvents.length}</span>
            </div>
            <div className="mt-4 grid gap-3">
              {notificationEvents.length ? notificationEvents.slice(0, 8).map((item) => (
                <article key={item.id} className="rounded-lg border border-white/10 bg-black/10 p-3">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-md bg-black/20 px-2.5 py-1 text-xs font-semibold">{statusLabel(item.status)}</span>
                        <span className="rounded-md bg-black/20 px-2.5 py-1 text-xs">{severityLabel(item.severity || "info")}</span>
                      </div>
                      <p className="mt-2 text-sm font-semibold text-white">{item.title || "Notificação operacional"}</p>
                      <p className="mt-1 text-sm leading-5 text-white/60">
                        {item.message_preview || item.skip_reason || item.error_message || "Evento registrado."}
                      </p>
                    </div>
                    <span className="text-xs text-white/45">{formatDate(item.created_at)}</span>
                  </div>
                </article>
              )) : (
                <EmptyState text="Nenhuma notificação registrada ainda." />
              )}
            </div>
          </div>
        </div>
      </Panel>

      <section className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <Panel>
          <h3 className="text-xl font-semibold">
            {whatsapp.status?.connected ? "Canal operacional conectado" : "Conectar aparelho"}
          </h3>
          <p className="mt-2 text-sm text-white/55">
            {whatsapp.status?.connected
              ? `Número: ${connectedPhone || whatsapp.status?.phone || "sessão conectada"}`
              : "Escaneie o QR Code para habilitar o canal operacional."}
          </p>
          {!whatsapp.status?.connected ? (
            <div className="mt-5 flex min-h-[260px] items-center justify-center rounded-xl border border-white/10 bg-[#f8fafc] text-slate-950 sm:min-h-[300px]">
              {whatsapp.connecting ? (
                <div className="px-6 text-center text-sm text-slate-600">
                  <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin" />
                  Gerando QR Code e abrindo conexão...
                </div>
              ) : whatsapp.qr?.dataUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
                <img src={whatsapp.qr.dataUrl} alt="QR Code WhatsApp Eletrofrio" className="h-60 w-60 sm:h-72 sm:w-72" />
              ) : (
                <div className="px-6 text-center text-sm text-slate-500">Clique em iniciar conexão para gerar o QR Code.</div>
              )}
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-emerald-400/25 bg-emerald-400/10 p-4 text-emerald-100">
              <p className="font-semibold">Sessão ativa</p>
              <p className="mt-1 text-sm opacity-80">Conectado em {formatDate(whatsapp.status?.lastConnectionAt)}</p>
            </div>
          )}
          {canManage ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                disabled={whatsapp.busy}
                onClick={() => void whatsapp.refreshQr()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-400/15 disabled:opacity-60"
              >
                {whatsapp.connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageCircle className="h-4 w-4" />}
                {whatsapp.connecting ? "Gerando QR..." : whatsapp.status?.connected ? "Reconectar" : "Iniciar conexão"}
              </button>
              <button
                type="button"
                disabled={whatsapp.busy}
                onClick={() => void whatsapp.refreshQr()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-semibold text-white/80 transition hover:bg-white/[0.08] disabled:opacity-60"
              >
                <RefreshCw className="h-4 w-4" />
                Atualizar status
              </button>
              <button
                type="button"
                disabled={whatsapp.busy}
                onClick={() => void whatsapp.runAction(eletrofrioApi.whatsappLogout, "Sessão encerrada.")}
                className="sm:col-span-2 inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm font-semibold text-red-200 transition hover:bg-red-400/15 disabled:opacity-60"
              >
                Encerrar sessão
              </button>
            </div>
          ) : null}
        </Panel>

        <Panel>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-xl font-semibold">Conversas operacionais</h3>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:w-[420px]">
              <input value={communicationSearch} onChange={(event) => setCommunicationSearch(event.target.value)} placeholder="Buscar telefone, loja, tag..." className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none" />
              <select value={communicationType} onChange={(event) => setCommunicationType(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none">
                <option value="">Todos os tipos</option>
                <option value="incoming_question">Perguntas</option>
                <option value="rag_response">Respostas RAG</option>
                <option value="operational_alert">Alertas</option>
                <option value="operational_summary">Resumos</option>
                <option value="manual_message">Manuais</option>
                <option value="system_event">Eventos</option>
              </select>
              <select value={communicationStatus} onChange={(event) => setCommunicationStatus(event.target.value)} className="rounded-xl border border-white/10 px-3 py-2 text-sm outline-none sm:col-span-2">
                <option value="">Todos os status</option>
                <option value="sent">Enviado</option>
                <option value="received">Recebido</option>
                <option value="failed">Falhou</option>
                <option value="dry-run">Dry-run</option>
              </select>
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {visibleCommunications.length ? visibleCommunications.slice(0, 12).map((item) => (
              <article key={item.id} className="rounded-xl border border-white/10 bg-white/[0.035] p-3 sm:p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex flex-wrap gap-2">
                      <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs font-semibold">{typeLabel(item.type)}</span>
                      <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs">{statusLabel(item.status)}</span>
                      <span className="rounded-md bg-black/15 px-2.5 py-1 text-xs">{item.source}</span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-white/78">{item.message_preview || "Evento operacional registrado."}</p>
                    <p className="mt-2 text-xs text-white/45">
                      {[item.phone, item.loja_nome, item.tag].filter(Boolean).join(" / ") || "Sem vínculo operacional direto"}
                    </p>
                  </div>
                  <span className="text-xs text-white/45">{formatDate(item.created_at)}</span>
                </div>
              </article>
            )) : (
              <EmptyState text="Nenhuma comunicação operacional registrada ainda." />
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Panel>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold">Consultas operacionais</h3>
            </div>
            <span className="rounded-md border border-white/10 bg-white/[0.045] px-3 py-1.5 text-xs text-white/55">{ragHistory.length} registros</span>
          </div>
          <div className="mt-5 grid gap-3">
            {ragHistory.length ? ragHistory.slice(0, 8).map((item) => (
              <article key={item.id} className="rounded-xl border border-white/10 bg-white/[0.035] p-3 sm:p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="font-semibold text-white">{item.question}</p>
                    <p className="mt-2 text-sm leading-6 text-white/65">{item.answer_preview || "Resposta registrada."}</p>
                  </div>
                  <div className="text-xs text-white/45 md:text-right">
                    <p>{item.confidence_label || "Confiança operacional"} {item.confidence != null ? `${Math.round(item.confidence * 100)}%` : ""}</p>
                    <p className="mt-1">{item.used_ai ? "síntese assistida" : "regras locais"} / {item.response_time_ms ?? "-"} ms</p>
                    <p className="mt-1">{formatDate(item.created_at)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-white/55">
                  <span className="rounded-md bg-black/15 px-2.5 py-1">{item.sources_json?.length || 0} fontes</span>
                  <span className="rounded-md bg-black/15 px-2.5 py-1">{item.warnings_json?.length || 0} avisos</span>
                </div>
              </article>
            )) : (
              <EmptyState text="Nenhuma consulta operacional registrada ainda." />
            )}
          </div>
        </Panel>

        <Panel>
          <h3 className="text-xl font-semibold">Timeline operacional</h3>
          <div className="mt-5 grid gap-3">
            {timeline.length ? timeline.slice(0, 14).map((item) => (
              <div key={`${item.timeline_source || "event"}-${item.id}`} className="relative border-l border-white/10 pl-4">
                <span className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full bg-sky-300" />
                <p className="text-xs text-white/40">{formatDate(item.created_at)}</p>
                <p className="mt-1 text-sm font-semibold text-white">{typeLabel(item.type)}</p>
                <p className="mt-1 text-sm leading-5 text-white/60">{item.message_preview || statusLabel(item.status)}</p>
              </div>
            )) : (
              <EmptyState text="Nenhum evento registrado ainda." />
            )}
          </div>
        </Panel>
      </section>

      <Panel>
        <h3 className="text-xl font-semibold">Teste e manutenção do canal</h3>
        <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <label className="grid gap-2">
            <span className="text-sm text-white/60">Telefone</span>
            <input
              value={phone}
              onChange={(event) => {
                setPhone(event.target.value);
                setLocalError(null);
              }}
              placeholder={connectedPhone || "5541999999999"}
              className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm text-white outline-none placeholder:text-white/35 focus:border-sky-300/40"
            />
          </label>
          <label className="grid gap-2">
            <span className="text-sm text-white/60">Mensagem</span>
            <input
              value={testMessage}
              onChange={(event) => setTestMessage(event.target.value)}
              className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm text-white outline-none placeholder:text-white/35 focus:border-sky-300/40"
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[360px] xl:items-end">
              <button
                type="button"
                disabled={whatsapp.busy || !canManage}
                onClick={sendValidation}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15 disabled:opacity-60"
              >
                <Send className="h-4 w-4" />
                Enviar teste
              </button>
              <button
                type="button"
                disabled={whatsapp.busy || notificationBusy || !canManage}
                onClick={() => void processNotificationQueue()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm font-semibold text-amber-100 transition hover:bg-amber-400/15 disabled:opacity-60"
              >
                <MessageCircle className="h-4 w-4" />
                Processar notificações
              </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

type IntelligentAlertRow = {
  id: string;
  generatedAt: string;
  type: string;
  unit: string;
  severity: string;
  message: string;
  relevance: string;
  deliveryStatus: string;
  deliveryTone: "success" | "warning" | "danger" | "muted";
  recipient: string;
  sentAt: string | null;
};

function notificationDeliveryLabel(status?: string | null) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "sent") return "Enviado para WhatsApp";
  if (normalized === "dry_run") return "Apenas simulado";
  if (normalized === "failed") return "Erro no envio";
  if (normalized === "skipped") return "Ignorado pelas regras";
  return "Pendente";
}

function notificationDeliveryTone(status?: string | null): "success" | "warning" | "danger" | "muted" {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "sent") return "success";
  if (normalized === "dry_run") return "warning";
  if (normalized === "failed") return "danger";
  return "muted";
}

function insightTypeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    temperature: "Temperatura",
    alarm: "Alarme operacional",
    recurrence: "Recorrência",
    offline: "Comunicação",
    operational_rule: "Regra operacional",
    store_concentration: "Concentração por loja",
  };
  return labels[String(value || "").toLowerCase()] || value || "Insight operacional";
}

function unitFromNotification(item: NotificationEvent) {
  const source = [item.message_full, item.message_preview, item.title].filter(Boolean).join("\n");
  const lojaMatch = source.match(/(?:Loja|Unidade|Local):\s*([^\n.]+)/i);
  return lojaMatch?.[1]?.trim() || "Unidade indicada na mensagem";
}

function notificationRelevanceReason(item: NotificationEvent) {
  if (item.skip_reason) return item.skip_reason;
  if (item.error_message) return item.error_message;
  if (item.severity === "critical") return "Ocorrência crítica passou pelas regras determinísticas de relevância.";
  if (item.title) return `Mensagem gerada por relevância operacional: ${item.title}.`;
  return "Evento avaliado pelo motor automático com controle de cooldown e duplicidade.";
}

function automaticMessageFromInsight(insight: EletrofrioInsight) {
  const unit = insight.loja_nome || (insight.loja_id != null ? `Loja ${insight.loja_id}` : "Unidade não informada");
  const equipment = insight.tag || (insight.dispositivo_id != null ? `Dispositivo ${insight.dispositivo_id}` : "equipamento relacionado");
  const problem = operationalSummaryText(insight);
  const action = cleanOperationalText(insight.recommended_action, "Validar sensor, condição do equipamento e prioridade operacional.");

  return `${unit} — ${equipment}. ${problem} Ação inicial: ${action}`;
}

function automaticRelevanceFromInsight(insight: EletrofrioInsight) {
  const evidence = insight.evidence_json || {};
  const priority = evidenceNumber(evidence, "operational_priority_score");
  const rule = evidenceString(evidence, "rule_name", "");
  if (insight.severity === "critical") return "Severidade crítica com risco operacional claro.";
  if (priority != null && priority >= 55) return `Prioridade operacional ${priority}/100, suficiente para entrar na fila automática.`;
  if (rule) return `Regra operacional aplicada: ${rule}.`;
  return "Insight relevante no recorte atual, preparado sem chamada obrigatória de LLM.";
}

function IntelligentAlertsView({
  insights,
  whatsapp,
}: {
  insights: EletrofrioInsight[];
  whatsapp: WhatsappController;
}) {
  const [status, setStatus] = useState<NotificationStatus | null>(null);
  const [events, setEvents] = useState<NotificationEvent[]>([]);
  const [recipients, setRecipients] = useState<NotificationRecipient[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connectedPhone = phoneFromWhatsappJid(whatsapp.status?.phone);
  const whatsappConnected = Boolean(whatsapp.status?.connected || status?.whatsapp?.connected);
  const dryRun = Boolean(status?.dry_run || status?.whatsapp?.dryRun);
  const enabledRecipients = useMemo(() => recipients.filter((item) => item.enabled), [recipients]);

  const loadAlerts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [statusResult, eventsResult, recipientsResult] = await Promise.all([
        eletrofrioApi.notificationStatus(),
        eletrofrioApi.notificationEvents({ limit: 100 }),
        eletrofrioApi.notificationRecipients(),
      ]);
      setStatus(statusResult);
      setEvents(eventsResult.items);
      setRecipients(recipientsResult.items);
      const schemaMessage = statusResult.message || eventsResult.message || recipientsResult.message;
      if (schemaMessage) setError(schemaMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar os alertas inteligentes.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAlerts();
    const interval = setInterval(() => {
      void loadAlerts();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadAlerts]);

  const rows = useMemo<IntelligentAlertRow[]>(() => {
    const eventRows = events.map((item) => ({
      id: `event-${item.id}`,
      generatedAt: item.created_at,
      type: item.channel === "whatsapp" ? "WhatsApp automático" : item.channel || "Alerta automático",
      unit: unitFromNotification(item),
      severity: severityLabel(item.severity || "info"),
      message: item.message_full || item.message_preview || item.title || "Mensagem automática registrada.",
      relevance: notificationRelevanceReason(item),
      deliveryStatus: notificationDeliveryLabel(item.status),
      deliveryTone: notificationDeliveryTone(item.status),
      recipient: item.phone || enabledRecipients[0]?.phone || connectedPhone || "Nenhum destinatário conectado",
      sentAt: item.sent_at,
    }));

    if (eventRows.length) return eventRows;

    return insights
      .filter((item) => item.severity === "critical" || severityRankForUi(item.severity) >= 2)
      .slice(0, 12)
      .map((item) => ({
        id: `preview-${item.id}`,
        generatedAt: item.created_at,
        type: insightTypeLabel(item.insight_type),
        unit: item.loja_nome || (item.loja_id != null ? `Loja ${item.loja_id}` : "Unidade não informada"),
        severity: severityLabel(item.severity),
        message: automaticMessageFromInsight(item),
        relevance: automaticRelevanceFromInsight(item),
        deliveryStatus: whatsappConnected
          ? dryRun
            ? "Apenas simulado"
            : "Pendente para envio"
          : "Simulado — nenhum WhatsApp conectado",
        deliveryTone: whatsappConnected && !dryRun ? "muted" : "warning",
        recipient: connectedPhone || enabledRecipients[0]?.phone || "Sem WhatsApp conectado",
        sentAt: item.whatsapp_sent_at,
      }));
  }, [connectedPhone, dryRun, enabledRecipients, events, insights, whatsappConnected]);

  const sentCount = rows.filter((item) => item.deliveryTone === "success").length;
  const simulatedCount = rows.filter((item) => item.deliveryStatus.toLowerCase().includes("simulado")).length;
  const failedCount = rows.filter((item) => item.deliveryTone === "danger").length;
  const pendingCount = rows.filter((item) => item.deliveryStatus.toLowerCase().includes("pendente")).length;

  const StatusIcon = ({ tone }: { tone: IntelligentAlertRow["deliveryTone"] }) => {
    if (tone === "success") return <CheckCircle2 className="h-4 w-4" />;
    if (tone === "danger") return <XCircle className="h-4 w-4" />;
    if (tone === "warning") return <BellRing className="h-4 w-4" />;
    return <Clock3 className="h-4 w-4" />;
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl">Alertas Inteligentes</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Histórico dos avisos automáticos gerados pelo motor operacional. A IA só entra quando a regra local não é suficiente e o orçamento permite.
            </p>
          </div>
          <button
            type="button"
            disabled={loading}
            onClick={() => void loadAlerts()}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-200 bg-white px-4 py-3 text-sm font-semibold text-sky-800 shadow-sm transition hover:bg-sky-50 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Atualizar
          </button>
        </div>
      </Panel>

      {error ? <ErrorBanner message={error} /> : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatusCard label="Canal WhatsApp" value={whatsappConnected ? "Conectado" : "Sem conexão"} tone={whatsappConnected ? "success" : "warning"} />
        <StatusCard label="Modo" value={dryRun ? "Simulação" : "Envio real"} tone={dryRun ? "warning" : "success"} />
        <StatusCard label="Enviados" value={sentCount} tone={sentCount ? "success" : "muted"} />
        <StatusCard label="Simulados" value={simulatedCount} tone={simulatedCount ? "warning" : "muted"} />
        <StatusCard label="Pendências / erros" value={`${pendingCount} / ${failedCount}`} tone={failedCount ? "danger" : pendingCount ? "warning" : "muted"} />
      </section>

      <Panel>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-xl font-semibold">Histórico automático</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Mostra o que foi enviado, o que seria enviado em simulação e por que a mensagem foi considerada relevante.
            </p>
          </div>
          <span className="rounded-md border border-sky-100 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-800">
            {rows.length} registros
          </span>
        </div>

        <div className="mt-5 grid gap-3 md:hidden">
          {rows.length ? rows.map((item) => (
            <article key={`${item.id}-mobile`} className="surface-muted rounded-xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-slate-500">{formatDate(item.generatedAt)}</p>
                  <h4 className="mt-1 text-base font-semibold text-slate-900">{item.type}</h4>
                  <p className="mt-1 text-sm text-slate-600">{item.unit}</p>
                </div>
                <span className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold ${statusPillClass(item.deliveryTone)}`}>
                  <StatusIcon tone={item.deliveryTone} />
                  {item.deliveryStatus}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{item.message}</p>
              <p className="mt-3 text-xs leading-5 text-slate-500">{item.relevance}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <span className="pill-soft rounded-md px-2.5 py-1">{item.severity}</span>
                <span className="pill-soft rounded-md px-2.5 py-1">{item.recipient}</span>
                <span className="pill-soft rounded-md px-2.5 py-1">{item.sentAt ? `Enviado em ${formatDate(item.sentAt)}` : "Sem envio confirmado"}</span>
              </div>
            </article>
          )) : (
            <EmptyState text="Nenhum alerta relevante encontrado no recorte atual." />
          )}
        </div>

        <div className="mt-5 hidden overflow-x-auto md:block">
          {rows.length ? (
            <table className="w-full min-w-[1100px] border-separate border-spacing-y-2 text-left text-sm">
              <thead>
                <tr className="text-xs font-semibold text-slate-500">
                  <th className="px-3 py-2">Data e hora</th>
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2">Unidade/local</th>
                  <th className="px-3 py-2">Prioridade</th>
                  <th className="px-3 py-2">Mensagem gerada</th>
                  <th className="px-3 py-2">Motivo da relevância</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Destino</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.id} className="surface-muted align-top">
                    <td className="rounded-l-xl px-3 py-4 text-slate-600">{formatDate(item.generatedAt)}</td>
                    <td className="px-3 py-4 font-semibold text-slate-800">{item.type}</td>
                    <td className="px-3 py-4 text-slate-700">{item.unit}</td>
                    <td className="px-3 py-4">
                      <span className="pill-soft rounded-md px-2.5 py-1 text-xs font-semibold">{item.severity}</span>
                    </td>
                    <td className="max-w-[280px] px-3 py-4 leading-6 text-slate-700">{item.message}</td>
                    <td className="max-w-[260px] px-3 py-4 leading-6 text-slate-600">{item.relevance}</td>
                    <td className="px-3 py-4">
                      <span className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-semibold ${statusPillClass(item.deliveryTone)}`}>
                        <StatusIcon tone={item.deliveryTone} />
                        {item.deliveryStatus}
                      </span>
                      {item.sentAt ? <p className="mt-2 text-xs text-slate-500">{formatDate(item.sentAt)}</p> : null}
                    </td>
                    <td className="rounded-r-xl px-3 py-4 text-slate-600">{item.recipient}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState text="Nenhum alerta relevante encontrado no recorte atual." />
          )}
        </div>
      </Panel>
    </div>
  );
}

function ruleLimitLabel(rule: OperationalRule) {
  if (rule.condition_type === "above" && rule.threshold_max != null) return `> ${rule.threshold_max}`;
  if (rule.condition_type === "below" && rule.threshold_min != null) return `< ${rule.threshold_min}`;
  if (rule.condition_type === "outside_range") return `${rule.threshold_min ?? "-"} a ${rule.threshold_max ?? "-"}`;
  if (rule.condition_type === "repeated_event") return `${rule.recurrence_count ?? 3} eventos / ${rule.recurrence_window_minutes ?? 120} min`;
  return rule.alarm_text_pattern || "-";
}

function ruleConditionLabel(value: string) {
  const labels: Record<string, string> = {
    above: "Acima do limite",
    below: "Abaixo do limite",
    outside_range: "Fora da faixa",
    contains_text: "Texto do alarme",
    repeated_event: "Recorrência",
    missing_telemetry: "Telemetria ausente",
  };
  return labels[value] || value || "-";
}

function ruleScopeLabel(rule: OperationalRule) {
  if (rule.scope_type === "equipment_type") return `Tipo: ${rule.scope_value || rule.equipment_type || "equipamento"}`;
  if (rule.scope_type === "alarm_group") return `Grupo: ${rule.scope_value || "alarme"}`;
  if (rule.scope_type === "store") return `Loja: ${rule.scope_value || "-"}`;
  if (rule.scope_type === "device") return `Dispositivo: ${rule.scope_value || "-"}`;
  return "Global";
}

function newRuleDraft(): OperationalRule {
  return {
    id: `draft-${Date.now()}`,
    name: "Nova regra operacional",
    description: "",
    enabled: true,
    scope_type: "global",
    scope_value: null,
    priority: 50,
    severity_when_triggered: "warning",
    equipment_type: null,
    measurement_type: null,
    condition_type: "contains_text",
    threshold_min: null,
    threshold_max: null,
    duration_minutes: null,
    recurrence_count: null,
    recurrence_window_minutes: null,
    alarm_text_pattern: "",
    explanation_template: "",
    recommended_action_template: "Validar evidências no painel operacional antes de acionar manutenção.",
  };
}

function isDraftRule(rule: OperationalRule | null) {
  return Boolean(rule?.id?.startsWith("draft-"));
}

function ruleSearchText(rule: OperationalRule) {
  return [
    rule.name,
    rule.description,
    rule.scope_type,
    rule.scope_value,
    rule.equipment_type,
    rule.measurement_type,
    rule.condition_type,
    rule.alarm_text_pattern,
    rule.explanation_template,
    rule.recommended_action_template,
  ].join(" ").toLowerCase();
}

function RulesView({ canManage }: { canManage: boolean }) {
  const [rules, setRules] = useState<OperationalRule[]>([]);
  const [evaluations, setEvaluations] = useState<RuleEvaluation[]>([]);
  const [selectedRule, setSelectedRule] = useState<OperationalRule | null>(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [schemaMessage, setSchemaMessage] = useState<string | null>(null);

  const loadRules = async () => {
    try {
      setBusy(true);
      setError(null);
      const [rulesResult, evaluationsResult] = await Promise.all([
        eletrofrioApi.rules(),
        eletrofrioApi.ruleEvaluations(40),
      ]);
      setRules(rulesResult.items);
      setEvaluations(evaluationsResult.items);
      setSchemaMessage(rulesResult.message || evaluationsResult.message || null);
      if (!selectedRule && rulesResult.items.length) {
        setSelectedRule(rulesResult.items[0]);
      } else if (selectedRule && !isDraftRule(selectedRule)) {
        setSelectedRule(rulesResult.items.find((item) => item.id === selectedRule.id) || rulesResult.items[0] || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar regras operacionais.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadRules();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredRules = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    if (!normalizedSearch) return rules;
    return rules.filter((rule) => ruleSearchText(rule).includes(normalizedSearch));
  }, [rules, search]);

  const activeRules = rules.filter((rule) => rule.enabled).length;
  const criticalRules = rules.filter((rule) => rule.severity_when_triggered === "critical").length;
  const latestEvaluation = evaluations[0];
  const draftMode = isDraftRule(selectedRule);

  const updateSelectedRule = (patch: Partial<OperationalRule>) => {
    setSelectedRule((current) => (current ? { ...current, ...patch } : current));
  };

  const startNewRule = () => {
    if (!canManage) return;
    setMessage(null);
    setError(null);
    setSelectedRule(newRuleDraft());
  };

  const applyDefaults = async () => {
    if (!canManage) return;
    try {
      setBusy(true);
      setError(null);
      setMessage(null);
      const result = await eletrofrioApi.applyRuleDefaults();
      setMessage(`Regras sugeridas aplicadas: ${Number(result.applied ?? 0)} novas, ${Number(result.skipped ?? 0)} já existentes.`);
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível aplicar regras sugeridas.");
    } finally {
      setBusy(false);
    }
  };

  const evaluateRules = async () => {
    if (!canManage) return;
    try {
      setBusy(true);
      setError(null);
      setMessage(null);
      const result = await eletrofrioApi.evaluateRules();
      setMessage(`Reavaliação concluída: ${Number(result.matched ?? 0)} ocorrências com regra aplicada. O bot usará as regras ativas na próxima análise.`);
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível reavaliar ocorrências.");
    } finally {
      setBusy(false);
    }
  };

  const toggleRule = async (rule: OperationalRule) => {
    if (!canManage) return;
    if (isDraftRule(rule)) {
      setSelectedRule({ ...rule, enabled: !rule.enabled });
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const updated = await eletrofrioApi.toggleRule(rule.id);
      setRules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedRule(updated);
      setMessage(updated.enabled ? "Regra ativada. Ela será usada nas próximas avaliações." : "Regra desativada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível alterar status da regra.");
    } finally {
      setBusy(false);
    }
  };

  const saveSelectedRule = async () => {
    if (!canManage) return;
    if (!selectedRule) return;
    if (!selectedRule.name.trim()) {
      setError("Informe um nome para a regra.");
      return;
    }
    if (selectedRule.condition_type === "contains_text" && !selectedRule.alarm_text_pattern?.trim()) {
      setError("Informe o texto ou padrão do alarme para essa condição.");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const updated = draftMode
        ? await eletrofrioApi.createRule(selectedRule)
        : await eletrofrioApi.updateRule(selectedRule.id, selectedRule);
      setRules((current) => {
        if (draftMode) return [updated, ...current];
        return current.map((item) => (item.id === updated.id ? updated : item));
      });
      setSelectedRule(updated);
      setMessage("Regra salva. O bot usará essa configuração na próxima avaliação.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar regra.");
    } finally {
      setBusy(false);
    }
  };

  const deleteSelectedRule = async () => {
    if (!canManage) return;
    if (!selectedRule) return;
    if (draftMode) {
      setSelectedRule(rules[0] || null);
      return;
    }
    const confirmed = window.confirm(`Excluir a regra "${selectedRule.name}"? As avaliações antigas ficam no histórico, mas a regra sai das próximas análises.`);
    if (!confirmed) return;
    try {
      setBusy(true);
      setError(null);
      await eletrofrioApi.deleteRule(selectedRule.id);
      const remaining = rules.filter((rule) => rule.id !== selectedRule.id);
      setRules(remaining);
      setSelectedRule(remaining[0] || null);
      setMessage("Regra excluída. Ela não será usada nas próximas avaliações.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir regra.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Regras Operacionais</h1>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 xl:min-w-[520px]">
            <InfoTile label="Ativas" value={`${activeRules}/${rules.length}`} />
            <InfoTile label="Críticas" value={criticalRules} />
            <InfoTile label="Última avaliação" value={latestEvaluation ? formatDate(latestEvaluation.evaluated_at) : "-"} />
          </div>
        </div>
      </Panel>

      {schemaMessage ? <ErrorBanner message={schemaMessage} /> : null}
      {error ? <ErrorBanner message={error} /> : null}
      {message ? <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/10 p-4 text-sm text-emerald-100">{message}</div> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.85fr)_minmax(0,1.15fr)]">
        <Panel>
          <div className="flex flex-col gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-white/45">Regras aplicadas</p>
              <h3 className="mt-2 text-xl font-semibold">{filteredRules.length} na lista</h3>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.045] px-3 py-2">
              <Search className="h-4 w-4 text-white/35" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Buscar por nome, loja, ativo ou alarme..."
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none"
              />
            </div>
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-3">
                <button disabled={busy} onClick={startNewRule} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-3 py-3 text-sm font-semibold text-white/80 disabled:opacity-60">
                  <Plus className="h-4 w-4" />
                  Nova
                </button>
                <button disabled={busy} onClick={() => void applyDefaults()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-3 py-3 text-sm font-semibold text-sky-100 disabled:opacity-60">
                  <ShieldCheck className="h-4 w-4" />
                  Sugeridas
                </button>
                <button disabled={busy} onClick={() => void evaluateRules()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-3 text-sm font-semibold text-emerald-100 disabled:opacity-60">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Reavaliar
                </button>
              </div>
            ) : null}
          </div>

          <div className="mt-5 grid max-h-[620px] gap-2 overflow-auto pr-1">
            {filteredRules.map((rule) => (
              <button
                key={rule.id}
                type="button"
                onClick={() => setSelectedRule(rule)}
                className={`rounded-xl border p-3 text-left transition ${
                  selectedRule?.id === rule.id ? "border-sky-300/45 bg-sky-300/10" : "border-white/10 bg-white/[0.035] hover:border-white/20"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{rule.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-white/55">{rule.description || rule.explanation_template || "Sem descrição."}</p>
                  </div>
                  <span className={`shrink-0 rounded-md px-2 py-1 text-xs ${rule.enabled ? "bg-emerald-400/10 text-emerald-200" : "bg-white/[0.06] text-slate-400"}`}>
                    {rule.enabled ? "ativa" : "inativa"}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-white/65">
                  <span className="rounded-md bg-black/15 px-2 py-1">{severityLabel(rule.severity_when_triggered)}</span>
                  <span className="rounded-md bg-black/15 px-2 py-1">{ruleConditionLabel(rule.condition_type)}</span>
                  <span className="rounded-md bg-black/15 px-2 py-1">{ruleScopeLabel(rule)}</span>
                  <span className="rounded-md bg-black/15 px-2 py-1">{ruleLimitLabel(rule)}</span>
                </div>
              </button>
            ))}
            {!filteredRules.length && <EmptyState text={busy ? "Carregando regras operacionais." : "Nenhuma regra encontrada."} />}
          </div>
        </Panel>

        <Panel>
          {selectedRule ? (
            <div className="mt-4 grid gap-4">
              <div className="flex flex-col gap-3 border-b border-white/10 pb-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-white/45">{draftMode ? "Nova regra" : "Editar regra"}</p>
                  <h3 className="mt-2 text-xl font-semibold">{selectedRule.name || "Regra operacional"}</h3>
                </div>
                {canManage ? <div className="flex flex-wrap gap-2">
                  <button disabled={busy} onClick={() => void toggleRule(selectedRule)} className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold disabled:opacity-60 ${selectedRule.enabled ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100" : "border-white/10 bg-white/[0.055] text-white/70"}`}>
                    <Power className="h-4 w-4" />
                    {selectedRule.enabled ? "Ativa" : "Inativa"}
                  </button>
                  <button disabled={busy} onClick={() => void saveSelectedRule()} className="inline-flex items-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-3 py-2 text-sm font-semibold text-sky-100 disabled:opacity-60">
                    <Save className="h-4 w-4" />
                    Salvar
                  </button>
                  <button disabled={busy} onClick={() => void deleteSelectedRule()} className="inline-flex items-center gap-2 rounded-xl border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm font-semibold text-red-100 disabled:opacity-60">
                    <Trash2 className="h-4 w-4" />
                    Excluir
                  </button>
                </div> : null}
              </div>
              <label className="grid gap-2">
                <span className="text-sm text-white/60">Nome</span>
                <input value={selectedRule.name} onChange={(event) => updateSelectedRule({ name: event.target.value })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
              </label>
              <label className="grid gap-2">
                <span className="text-sm text-white/60">Descrição curta</span>
                <textarea rows={2} value={selectedRule.description || ""} onChange={(event) => updateSelectedRule({ description: event.target.value })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Severidade</span>
                  <select value={selectedRule.severity_when_triggered} onChange={(event) => updateSelectedRule({ severity_when_triggered: event.target.value })} className="rounded-xl border border-white/10 bg-[#0d141d] px-4 py-3 text-sm">
                    <option value="info">Informativo</option>
                    <option value="warning">Atenção</option>
                    <option value="critical">Crítico</option>
                  </select>
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Condição</span>
                  <select value={selectedRule.condition_type} onChange={(event) => updateSelectedRule({ condition_type: event.target.value })} className="rounded-xl border border-white/10 bg-[#0d141d] px-4 py-3 text-sm">
                    <option value="above">Acima de</option>
                    <option value="below">Abaixo de</option>
                    <option value="outside_range">Fora da faixa</option>
                    <option value="contains_text">Texto do alarme</option>
                    <option value="repeated_event">Recorrência</option>
                    <option value="missing_telemetry">Telemetria ausente</option>
                  </select>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Escopo</span>
                  <select value={selectedRule.scope_type} onChange={(event) => updateSelectedRule({ scope_type: event.target.value })} className="rounded-xl border border-white/10 bg-[#0d141d] px-4 py-3 text-sm">
                    <option value="global">Global</option>
                    <option value="equipment_type">Tipo de ativo</option>
                    <option value="alarm_group">Grupo de alarme</option>
                    <option value="store">Loja</option>
                    <option value="device">Dispositivo</option>
                  </select>
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Valor do escopo</span>
                  <input value={selectedRule.scope_value || ""} onChange={(event) => updateSelectedRule({ scope_value: event.target.value || null })} placeholder="Ex.: frozen, compressor, 315" className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Ordem de atendimento</span>
                  <input type="number" value={selectedRule.priority} onChange={(event) => updateSelectedRule({ priority: Number(event.target.value) || 100 })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                  <span className="text-xs text-white/40">Número menor entra antes na fila de avaliação. Ex.: 5 antes de 50.</span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-4">
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Limite mínimo</span>
                  <input type="number" value={selectedRule.threshold_min ?? ""} onChange={(event) => updateSelectedRule({ threshold_min: event.target.value === "" ? null : Number(event.target.value) })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Limite máximo</span>
                  <input type="number" value={selectedRule.threshold_max ?? ""} onChange={(event) => updateSelectedRule({ threshold_max: event.target.value === "" ? null : Number(event.target.value) })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Recorrência</span>
                  <input type="number" value={selectedRule.recurrence_count ?? ""} onChange={(event) => updateSelectedRule({ recurrence_count: event.target.value === "" ? null : Number(event.target.value) })} placeholder="3" className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                </label>
                <label className="grid gap-2">
                  <span className="text-sm text-white/60">Janela min.</span>
                  <input type="number" value={selectedRule.recurrence_window_minutes ?? ""} onChange={(event) => updateSelectedRule({ recurrence_window_minutes: event.target.value === "" ? null : Number(event.target.value) })} placeholder="120" className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
                </label>
              </div>
              <label className="grid gap-2">
                <span className="text-sm text-white/60">Texto ou padrão do alarme</span>
                <input value={selectedRule.alarm_text_pattern || ""} onChange={(event) => updateSelectedRule({ alarm_text_pattern: event.target.value })} placeholder="Ex.: alta temperatura|compressor|offline" className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
              </label>
              <label className="grid gap-2">
                <span className="text-sm text-white/60">Explicação que aparece na ocorrência</span>
                <textarea rows={3} value={selectedRule.explanation_template || ""} onChange={(event) => updateSelectedRule({ explanation_template: event.target.value })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
              </label>
              <label className="grid gap-2">
                <span className="text-sm text-white/60">Ação recomendada</span>
                <textarea rows={3} value={selectedRule.recommended_action_template || ""} onChange={(event) => updateSelectedRule({ recommended_action_template: event.target.value })} className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm" />
              </label>
            </div>
          ) : (
            <EmptyState text="Selecione uma regra para ver detalhes." />
          )}
        </Panel>
      </div>

      <Panel>
        <p className="text-xs uppercase tracking-[0.18em] text-white/45">Últimas avaliações</p>
        <h3 className="mt-2 text-xl font-semibold">Aplicação recente das regras</h3>
        <div className="mt-5 grid gap-3">
          {evaluations.length ? evaluations.map((item) => (
            <div key={item.id || `${item.rule_id}-${item.evaluated_at}`} className="grid gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-4 text-sm md:grid-cols-[1fr_auto]">
              <div>
                <p className="font-semibold">{item.explanation || evidenceString(item.evidence_json, "rule_name", "Regra operacional aplicada")}</p>
                <p className="mt-1 text-white/60">{item.loja_nome || `Loja ${item.loja_id ?? "-"}`} - {item.tag || `Dispositivo ${item.dispositivo_id ?? "-"}`}</p>
              </div>
              <div className="text-white/65 md:text-right">
                <p>{severityLabel(item.severity || "info")} - Urgência {item.score ?? "-"}/100</p>
                <p>{formatDate(item.evaluated_at)}</p>
              </div>
            </div>
          )) : <EmptyState text="Nenhuma avaliação registrada ainda. Use Reavaliar ocorrências." />}
        </div>
      </Panel>
    </div>
  );
}

function compactText(value: string | null | undefined, fallback = "-", max = 150) {
  const text = String(value || fallback).trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 3).trim()}...`;
}

function statusPillClass(tone: "success" | "warning" | "danger" | "muted") {
  const classes = {
    success: "border-emerald-300/50 bg-emerald-50 text-emerald-700",
    warning: "border-amber-300/60 bg-amber-50 text-amber-700",
    danger: "border-red-300/55 bg-red-50 text-red-700",
    muted: "border-slate-200 bg-slate-100 text-slate-600",
  };
  return classes[tone];
}

function severityRankForUi(value: string | null | undefined) {
  const normalized = String(value || "").toLowerCase();
  if (["critical", "critico", "crítico", "high", "alta"].includes(normalized)) return 4;
  if (["warning", "medium", "medio", "médio", "atenção", "atencao"].includes(normalized)) return 2;
  return 1;
}

function isUsefulRun(run: CollectorRun) {
  return (
    run.status === "success" ||
    (run.units_count || 0) > 0 ||
    (run.alarms_count || 0) > 0 ||
    (run.telemetry_count || 0) > 0 ||
    (run.anomalies_count || 0) > 0
  );
}

function StatusCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "success" | "warning" | "danger" | "muted";
}) {
  return (
    <div className={`status-card status-card-${tone} surface-soft rounded-xl p-4`}>
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <div className={`mt-2 inline-flex rounded-md border px-2.5 py-1 text-sm font-semibold ${statusPillClass(tone)}`}>
        {value}
      </div>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="surface-muted rounded-xl p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function OperationView() {
  const [settings, setSettings] = useState<CollectorSettings | null>(null);
  const [runs, setRuns] = useState<CollectorRun[]>([]);
  const [operationOverview, setOperationOverview] = useState<EletrofrioOverview | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [intervalMinutes, setIntervalMinutes] = useState(5);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTechnicalFailures, setShowTechnicalFailures] = useState(false);
  const [lastManualCollection, setLastManualCollection] = useState<(CollectorRunResult & { collectedAt: string }) | null>(null);
  const actuallyRunning = isCollectorActuallyRunning(settings);
  const lastGoodRun = settings?.lastGoodRun;

  const cleanRuns = runs.filter((run) => {
    const noisyTimeout =
      run.trigger_source === "loop" &&
      run.units_count === 0 &&
      run.alarms_count === 0 &&
      (run.error_message || "").includes("Timeout na API Eletrofrio: unidades");
    const staleAutoRunning =
      run.status === "running" &&
      run.trigger_source === "loop" &&
      run.units_count === 0 &&
      run.alarms_count === 0 &&
      (minutesSince(run.started_at) ?? 0) > 5;
    return !noisyTimeout && !staleAutoRunning;
  });
  const usefulRuns = cleanRuns.filter(isUsefulRun);
  const visibleRuns = (showTechnicalFailures ? cleanRuns : usefulRuns).slice(0, 5);
  const collectionForSummary = lastManualCollection || (lastGoodRun
    ? {
        status: lastGoodRun.status,
        units: lastGoodRun.units_count,
        alarms: lastGoodRun.alarms_count,
        telemetry: lastGoodRun.telemetry_count,
        anomalies_count: lastGoodRun.anomalies_count,
        collectedAt: lastGoodRun.finished_at || lastGoodRun.started_at,
      }
    : null);

  const loadAutomation = async () => {
    setError(null);

    const [statusResult, overviewResult, runsResult] = await Promise.all([
      eletrofrioApi.collectorStatus().catch(() => null),
      eletrofrioApi.overview().catch(() => null),
      eletrofrioApi.collectorRuns(12).catch(() => ({ items: [] as CollectorRun[] })),
    ]);

    if (statusResult) {
      setSettings(statusResult);
      setEnabled(statusResult.enabled);
      setIntervalMinutes(statusResult.intervalMinutes);
    } else {
      setError("Não foi possível carregar o status operacional agora. Verifique se o backend está ativo.");
    }

    if (overviewResult) {
      setOperationOverview(overviewResult);
    }
    setRuns(runsResult.items);
  };

  useEffect(() => {
    void loadAutomation();
    const interval = setInterval(() => {
      void loadAutomation();
    }, busy || actuallyRunning ? 5000 : 30000);
    return () => clearInterval(interval);
  }, [busy, actuallyRunning]);

  const saveAutomation = async () => {
    if (intervalMinutes < 5) {
      setError("O intervalo mínimo permitido é de 5 minutos.");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      setMessage(null);
      const result = await eletrofrioApi.updateCollectorSettings({
        enabled,
        intervalMinutes,
      });
      setSettings(result);
      setMessage(enabled ? "Coleta automática ativada." : "Coleta automática desativada.");
      await loadAutomation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar as configurações operacionais.");
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    try {
      setBusy(true);
      setError(null);
      setMessage("Executando sincronização operacional...");
      const result = await eletrofrioApi.collectorRunNow();
      const label = result.status === "partial_success" ? "Sincronização concluída com dados cacheados" : "Sincronização concluída";
      setMessage(`${label}: ${result.units ?? 0} lojas, ${result.alarms ?? 0} alarmes, ${result.telemetry ?? 0} telemetrias.`);
      if (["success", "partial_success"].includes(result.status)) {
        setLastManualCollection({ ...result, collectedAt: new Date().toISOString() });
      }
      await loadAutomation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível executar a sincronização agora.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <Panel>
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl">Centro Operacional</h1>
          </div>
          <button type="button" onClick={() => void loadAutomation()} disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.045] px-4 py-3 text-sm font-semibold text-white/75 transition hover:bg-white/[0.07] disabled:opacity-60">
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
        </div>
      </Panel>

      {error ? <ErrorBanner message={error} /> : null}
      {message ? <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/10 p-4 text-sm text-emerald-100">{message}</div> : null}

      <section className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        <StatusCard label="API Eletrofrio" value={operationOverview ? "Operacional" : "Validando"} tone={operationOverview ? "success" : "warning"} />
        <StatusCard
          label="Coleta"
          value={busy || actuallyRunning ? "Executando" : lastGoodRun ? "Finalizada" : settings?.enabled ? "Automática" : "Manual"}
          tone={busy || actuallyRunning ? "warning" : lastGoodRun ? "success" : settings?.enabled ? "success" : "muted"}
        />
        <StatusCard label="Último snapshot" value={lastGoodRun ? formatDate(lastGoodRun.finished_at || lastGoodRun.started_at) : "Sem coleta"} tone={lastGoodRun ? "success" : "warning"} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(360px,0.85fr)_minmax(0,1.15fr)]">
        <div className="grid content-start gap-4">
          <Panel>
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-white/45">Sincronização</p>
                <h3 className="mt-2 text-xl font-semibold">Sincronização dos dados</h3>
                <p className="mt-2 text-sm text-white/60">
                  {settings?.enabled
                    ? "Coleta automática programada."
                    : "Automação desativada - coletas podem ser executadas manualmente."}
                </p>
              </div>
              <span className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${statusPillClass(settings?.enabled ? "success" : "muted")}`}>
                {actuallyRunning ? "Executando agora" : settings?.enabled ? "Automação ativa" : "Manual"}
              </span>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <InfoTile label="Intervalo atual" value={`${intervalMinutes || 5} min`} />
              <InfoTile label="Última execução útil" value={lastGoodRun ? formatDate(lastGoodRun.finished_at || lastGoodRun.started_at) : "Sem coleta validada"} />
              <InfoTile label="Próxima execução" value={settings?.enabled && settings?.nextRunAt ? formatDate(settings.nextRunAt) : "Automação desativada"} />
              <InfoTile label="Estado da coleta" value={busy || actuallyRunning ? "Em execução" : lastGoodRun ? "Finalizada" : "Aguardando"} />
            </div>

            <div className="mt-5 grid gap-4">
              <label className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                <span>
                  <span className="block text-sm font-semibold text-white">Automação</span>
                  <span className="mt-1 block text-xs text-white/45">Liga ou desliga a coleta em segundo plano.</span>
                </span>
                <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-5 w-5 accent-emerald-400" />
              </label>

              <label className="grid gap-2">
                <span className="text-sm text-white/60">Intervalo da coleta em minutos</span>
                <input
                  type="number"
                  min={5}
                  value={intervalMinutes}
                  onBlur={() => {
                    if (!Number.isFinite(intervalMinutes) || intervalMinutes < 5) {
                      setIntervalMinutes(5);
                    }
                  }}
                  onChange={(event) => setIntervalMinutes(Number(event.target.value))}
                  className="rounded-xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm text-white outline-none focus:border-sky-300/40"
                />
                <span className={`text-xs ${intervalMinutes < 5 ? "text-red-200" : "text-white/40"}`}>Mínimo permitido: 5 minutos.</span>
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <button type="button" disabled={busy || intervalMinutes < 5} onClick={() => void saveAutomation()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-400/15 disabled:opacity-60">
                  <ShieldCheck className="h-4 w-4" />
                  Salvar
                </button>
                <button type="button" disabled={busy || actuallyRunning} onClick={() => void runNow()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15 disabled:opacity-60">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Executar coleta agora
                </button>
              </div>
            </div>
          </Panel>

          {collectionForSummary ? (
            <Panel>
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-white/45">Coleta concluída</p>
                  <h3 className="mt-2 text-xl font-semibold">Resultado da coleta</h3>
                  <p className="mt-2 text-sm text-white/60">
                    Última leitura consolidada da operação.
                  </p>
                </div>
                <span className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${statusPillClass("success")}`}>
                  Concluída
                </span>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                <InfoTile label="Lojas analisadas" value={collectionForSummary.units ?? 0} />
                <InfoTile label="Alarmes encontrados" value={collectionForSummary.alarms ?? 0} />
                <InfoTile label="Telemetrias processadas" value={collectionForSummary.telemetry ?? 0} />
                <InfoTile label="Horário da coleta" value={formatDate(collectionForSummary.collectedAt)} />
                <InfoTile label="Status" value={collectionForSummary.status === "partial_success" ? "concluída com cache" : "concluída"} />
              </div>
            </Panel>
          ) : null}

          <Panel>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-white/45">Histórico útil</p>
                <h3 className="mt-2 text-xl font-semibold">Últimas sincronizações</h3>
              </div>
              <label className="flex items-center gap-2 text-xs text-white/60">
                <input type="checkbox" checked={showTechnicalFailures} onChange={(event) => setShowTechnicalFailures(event.target.checked)} className="h-4 w-4 accent-amber-300" />
                Mostrar falhas técnicas
              </label>
            </div>
            <div className="mt-5 space-y-3">
              {visibleRuns.length ? (
                visibleRuns.map((run) => (
                  <div key={run.id} className="grid gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-4 text-sm md:grid-cols-[1fr_auto]">
                    <div>
                      <p className="font-semibold text-white">{collectorRunLabel(run)}</p>
                      <p className="mt-1 text-white/50">{formatDate(run.started_at)} - {triggerSourceLabel(run.trigger_source)}</p>
                    </div>
                    <div className="text-white/65 md:text-right">
                      <p>{run.units_count} lojas / {run.alarms_count} alarmes</p>
                      <p>{run.telemetry_count} telemetrias</p>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState text="Nenhuma sincronização útil para exibir." />
              )}
            </div>
          </Panel>
        </div>

        <div className="grid content-start gap-4">
          <Panel>
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <h3 className="text-2xl font-semibold">
                  {busy || actuallyRunning ? "Coleta em execução" : collectionForSummary ? "Coleta finalizada" : "Aguardando coleta"}
                </h3>
                <p className="mt-2 text-sm text-white/60">
                  {busy || actuallyRunning
                    ? "Acompanhando a sincronização em tempo real."
                    : collectionForSummary
                      ? "Resumo da última leitura operacional."
                      : "Execute uma coleta manual ou ative a automação."}
                </p>
              </div>
              <span className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${statusPillClass(busy || actuallyRunning ? "warning" : collectionForSummary ? "success" : "muted")}`}>
                {busy || actuallyRunning ? "Executando" : collectionForSummary ? "Finalizada" : "Aguardando"}
              </span>
            </div>

            <div className="mt-5">
              {busy || actuallyRunning ? (
                <div className="rounded-xl border border-amber-400/20 bg-amber-400/10 p-5">
                  <div className="flex items-center gap-3 text-amber-100">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span className="font-semibold">Sincronização em andamento</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-amber-100/75">
                    Buscando lojas, alarmes e telemetrias. Esta área atualiza automaticamente enquanto a coleta estiver em execução.
                  </p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <InfoTile label="Última execução útil" value={lastGoodRun ? formatDate(lastGoodRun.finished_at || lastGoodRun.started_at) : "Ainda sem coleta"} />
                    <InfoTile label="Origem" value={settings?.latestRun ? triggerSourceLabel(settings.latestRun.trigger_source) : busy ? "manual" : "automática"} />
                  </div>
                </div>
              ) : collectionForSummary ? (
                <div className="grid gap-4">
                  <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
                    <InfoTile label="Lojas" value={collectionForSummary.units ?? 0} />
                    <InfoTile label="Alarmes" value={collectionForSummary.alarms ?? 0} />
                    <InfoTile label="Telemetrias" value={collectionForSummary.telemetry ?? 0} />
                    <InfoTile label="Atualização" value={formatDate(collectionForSummary.collectedAt)} />
                    <InfoTile label="Status" value={collectionForSummary.status === "partial_success" ? "Com cache" : "Concluída"} />
                    <InfoTile label="Origem" value={lastManualCollection ? "Manual" : triggerSourceLabel(lastGoodRun?.trigger_source)} />
                  </div>
                </div>
              ) : (
                <EmptyState text="Nenhuma coleta em andamento. Execute uma coleta agora para acompanhar o resultado aqui." />
              )}
            </div>
          </Panel>
        </div>
      </section>
    </div>
  );
}

export default function HomePage() {
  const [activeView, setActiveView] = useState<ViewId>("dashboard");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const isAuthenticated = Boolean(authUser);
  const overviewState = useEletrofrioOverview(isAuthenticated, activeView === "ativos");
  const insightsState = useEletrofrioInsights(isAuthenticated);
  const whatsapp = useWhatsappStatus(30000, isAuthenticated);
  const [collectorBusy, setCollectorBusy] = useState(false);
  const [collectorMessage, setCollectorMessage] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isAdmin = authUser?.role === "admin";

  useEffect(() => {
    const restoreSession = async () => {
      const token = getAuthToken();
      if (!token) {
        setAuthChecked(true);
        return;
      }
      try {
        const result = await eletrofrioApi.me();
        setAuthUser(result.user);
      } catch {
        setAuthToken(null);
        setAuthUser(null);
      } finally {
        setAuthChecked(true);
      }
    };
    void restoreSession();

    const expireSession = () => {
      setAuthToken(null);
      setAuthUser(null);
    };
    window.addEventListener("eletrofrio-auth-expired", expireSession);
    return () => window.removeEventListener("eletrofrio-auth-expired", expireSession);
  }, []);

  useEffect(() => {
    if (!authUser) return;
    const syncViewFromRoute = () => {
      const nextView = viewFromBrowser();
      const allowedView = authUser.role === "admin" || nextView !== "operacao" ? nextView : "dashboard";
      setActiveView(allowedView);
      window.localStorage.setItem(VIEW_STORAGE_KEY, allowedView);

      if (!window.location.hash) {
        window.history.replaceState(null, "", viewHash(allowedView));
      }
    };

    syncViewFromRoute();
    window.addEventListener("hashchange", syncViewFromRoute);
    window.addEventListener("popstate", syncViewFromRoute);

    return () => {
      window.removeEventListener("hashchange", syncViewFromRoute);
      window.removeEventListener("popstate", syncViewFromRoute);
    };
  }, [authUser]);

  const changeView = (view: ViewId) => {
    const allowedView = isAdmin || view !== "operacao" ? view : "dashboard";
    setActiveView(allowedView);
    window.localStorage.setItem(VIEW_STORAGE_KEY, allowedView);
    window.history.pushState(null, "", viewHash(allowedView));
  };

  const handleLogin = (user: AuthUser) => {
    setAuthUser(user);
    void Promise.all([overviewState.refresh(), insightsState.refresh(), whatsapp.refresh()]);
  };

  const handleLogout = async () => {
    try {
      await eletrofrioApi.logout();
    } catch {
      // Logout local basta quando o token ja expirou.
    }
    setAuthToken(null);
    setAuthUser(null);
  };

  const runCollector = async () => {
    if (!isAdmin) return;
    try {
      setCollectorBusy(true);
      setCollectorMessage(null);
      const result = await eletrofrioApi.runCollector();
      setCollectorMessage(
        `Coleta finalizada: ${result.units ?? 0} unidades, ${result.alarms ?? 0} alarmes, ${result.telemetry ?? 0} telemetrias.`
      );
      await Promise.all([overviewState.refresh(), insightsState.refresh()]);
    } catch (err) {
      setCollectorMessage(err instanceof Error ? err.message : "Falha ao rodar coleta.");
    } finally {
      setCollectorBusy(false);
    }
  };

  const titleByView: Record<ViewId, string> = {
    dashboard: "Visão geral",
    ativos: "Ativos",
    alertas: "Ocorrências",
    inteligentes: "Alertas Inteligentes",
    operacao: "Operação",
    regras: "Regras",
    whatsapp: "WhatsApp",
  };

  const content = {
    dashboard: (
      <DashboardView
        overview={overviewState.overview}
        loading={overviewState.loading}
        onRefresh={overviewState.refresh}
        onRunCollector={runCollector}
        collectorBusy={collectorBusy}
        collectorMessage={collectorMessage}
        whatsappConnected={Boolean(whatsapp.status?.connected)}
        canRunCollector={isAdmin}
      />
    ),
    ativos: (
      <AssetsView
        devices={overviewState.devices}
        alarms={overviewState.alarms}
        telemetry={overviewState.telemetry}
        overviewDevices={overviewState.overview?.device_metrics || []}
      />
    ),
    alertas: <InsightsView insights={insightsState.insights} />,
    inteligentes: <IntelligentAlertsView insights={insightsState.insights} whatsapp={whatsapp} />,
    operacao: <OperationView />,
    regras: <RulesView canManage={isAdmin} />,
    whatsapp: <WhatsappView whatsapp={whatsapp} canManage={isAdmin} />,
  } satisfies Record<ViewId, React.ReactNode>;

  if (!authChecked) {
    return <LoadingSplash text="Validando sessão e permissões." />;
  }

  if (!authUser) {
    return <LoginView onLogin={handleLogin} />;
  }

  return (
    <main className="industrial-ui min-h-screen text-slate-800">
      <div className="flex min-h-screen flex-col">
        <Header
          title={titleByView[activeView]}
          connected={Boolean(whatsapp.status?.connected)}
          userLabel={authUser.customer_name || authUser.username}
          userRole={authUser.role}
          onLogout={handleLogout}
        />

        <div className={`app-shell-grid grid flex-1 ${sidebarCollapsed ? "is-sidebar-collapsed" : ""}`}>
          <Sidebar
            activeView={activeView}
            onViewChange={changeView}
            role={authUser.role}
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((value) => !value)}
            totals={{
              units: overviewState.overview?.totals.units,
              devices: overviewState.overview?.totals.devices,
              alarms: overviewState.overview?.totals.alarms,
            }}
          />

          <section className="min-w-0 flex-1 px-3 pb-24 pt-3 sm:px-4 md:px-5 lg:px-6 lg:pb-6 lg:pt-4">
            <div key={activeView} className="app-content-view mx-auto flex w-full max-w-[1360px] flex-col gap-4">
              {overviewState.error ? <ErrorBanner message={overviewState.error} /> : null}
              {insightsState.error && activeView === "alertas" ? (
                <ErrorBanner message={insightsState.error} />
              ) : null}
              {content[activeView]}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
