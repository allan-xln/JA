"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  CheckCircle2,
  ClipboardList,
  Copy,
  History,
  Loader2,
  MessageCircle,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";

import { eletrofrioApi } from "@/services/eletrofrioApi";
import type {
  AnomalyAiSolution,
  AnomalyDetail,
  AnomalyEvent,
  EletrofrioAnomaly,
  NotificationRecipient,
} from "@/types/eletrofrio";

const STATUS_OPTIONS = [
  { value: "active", label: "Abertas" },
  { value: "resolved", label: "Resolvidas" },
  { value: "all", label: "Todas" },
  { value: "reopened", label: "Reabertas" },
  { value: "ticket_opened", label: "Com chamado" },
  { value: "whatsapp_sent", label: "WhatsApp enviado" },
];

const SEVERITY_OPTIONS = [
  { value: "all", label: "Todas severidades" },
  { value: "critical", label: "Críticas" },
  { value: "warning", label: "Atenção" },
  { value: "medium", label: "Média" },
  { value: "info", label: "Info" },
];

function formatDate(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString("pt-BR");
}

function compactDate(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function statusLabel(value?: string | null) {
  const normalized = String(value || "open");
  const labels: Record<string, string> = {
    open: "Aberta",
    acknowledged: "Reconhecida",
    investigating: "Em investigação",
    solution_suggested: "Sugestão gerada",
    whatsapp_sent: "WhatsApp enviado",
    ticket_opened: "Chamado aberto",
    resolved: "Resolvida",
    reopened: "Reaberta",
    ignored: "Ignorada",
  };
  return labels[normalized] || normalized;
}

function severityLabel(value?: string | null) {
  const normalized = String(value || "info").toLowerCase();
  if (["critical", "critico", "crítico"].includes(normalized)) return "Crítica";
  if (["warning", "medium", "media", "média"].includes(normalized)) return "Atenção";
  if (["high", "alta"].includes(normalized)) return "Alta";
  return "Info";
}

function severityClass(value?: string | null) {
  const normalized = String(value || "").toLowerCase();
  if (["critical", "critico", "crítico"].includes(normalized)) return "border-red-200 bg-red-50 text-red-700";
  if (["warning", "medium", "media", "média", "high", "alta"].includes(normalized)) return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-sky-100 bg-sky-50 text-sky-700";
}

function statusClass(value?: string | null) {
  const normalized = String(value || "open");
  if (normalized === "resolved") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (normalized === "reopened") return "border-red-200 bg-red-50 text-red-700";
  if (normalized === "ignored") return "border-slate-200 bg-slate-100 text-slate-600";
  if (normalized === "ticket_opened") return "border-violet-200 bg-violet-50 text-violet-700";
  if (normalized === "whatsapp_sent") return "border-teal-200 bg-teal-50 text-teal-700";
  return "border-sky-100 bg-sky-50 text-sky-700";
}

function anomalyTitle(anomaly: EletrofrioAnomaly) {
  return anomaly.title || anomaly.summary || anomaly.message || "Anomalia operacional";
}

function equipmentLabel(anomaly: EletrofrioAnomaly) {
  return anomaly.tag || anomaly.dispositivo_id || anomaly.equipment_id || "-";
}

function storeLabel(anomaly: EletrofrioAnomaly) {
  return anomaly.loja_nome || anomaly.customer_name || anomaly.loja_id || "-";
}

function solutionJson(solution?: AnomalyAiSolution | null) {
  return solution?.solution_json || null;
}

function solutionLines(solution?: AnomalyAiSolution | null): Array<[string, unknown]> {
  const json = solutionJson(solution);
  if (!json) return [];
  const alternatives = Array.isArray(json.alternative_causes) ? json.alternative_causes : [];
  const lines: Array<[string, unknown]> = [
    ["Diagnóstico provável", json.diagnosis],
    ["Causa mais provável", json.probable_cause],
    ["Causas alternativas", alternatives.length ? alternatives.join("; ") : undefined],
    ["Ação imediata", json.immediate_action],
    ["Ação técnica", json.technical_action],
    ["Urgência", json.urgency],
    ["Risco", json.risk],
    ["Técnico em campo", json.field_technician_required],
    ["WhatsApp", json.whatsapp_message],
    ["Observação", json.root_cause_note],
  ];
  return lines.filter(([, value]) => Boolean(value));
}

function evidencePreview(anomaly: AnomalyDetail) {
  const evidence = anomaly.evidence_json || {};
  const keys = Object.keys(evidence);
  if (!keys.length) return "Sem evidência estruturada adicional.";
  return keys
    .slice(0, 5)
    .map((key) => `${key}: ${JSON.stringify(evidence[key]).slice(0, 180)}`)
    .join("\n");
}

function eventIcon(event: AnomalyEvent) {
  if (event.event_type.includes("whatsapp")) return <MessageCircle className="h-4 w-4" />;
  if (event.event_type.includes("ticket")) return <ClipboardList className="h-4 w-4" />;
  if (event.event_type.includes("resolved")) return <CheckCircle2 className="h-4 w-4" />;
  if (event.event_type.includes("ai_solution")) return <Sparkles className="h-4 w-4" />;
  return <History className="h-4 w-4" />;
}

function actionImpact(anomaly: AnomalyDetail) {
  const critical = String(anomaly.severity || "").toLowerCase() === "critical";
  if (critical) {
    return "Impacto provável: risco de perda operacional, perda de produto ou indisponibilidade se a condição persistir.";
  }
  return "Impacto provável: exige acompanhamento para evitar evolução para ocorrência crítica.";
}

type BusyAction =
  | "list"
  | "detail"
  | "suggest"
  | "whatsapp"
  | "resolve"
  | "reopen"
  | "note"
  | "ticket"
  | "status"
  | "code-search"
  | "ensure-code"
  | null;

export function AnomalyOperationsView() {
  const [items, setItems] = useState<EletrofrioAnomaly[]>([]);
  const [statusFilter, setStatusFilter] = useState("active");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [codeSearch, setCodeSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnomalyDetail | null>(null);
  const [recipients, setRecipients] = useState<NotificationRecipient[]>([]);
  const [recipientId, setRecipientId] = useState("");
  const [note, setNote] = useState("");
  const [ticketDescription, setTicketDescription] = useState("");
  const [busy, setBusy] = useState<BusyAction>("list");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicateBlocked, setDuplicateBlocked] = useState(false);

  const loadList = useCallback(async () => {
    try {
      setBusy((current) => current || "list");
      setError(null);
      const response = await eletrofrioApi.anomalies({
        limit: 120,
        status: statusFilter,
        severity: severityFilter,
        search,
      });
      setItems(response.items);
      if (response.data_unavailable) {
        setError(response.message || "Banco operacional temporariamente sobrecarregado. Tente atualizar em instantes.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar anomalias.");
    } finally {
      setBusy((current) => (current === "list" ? null : current));
    }
  }, [search, severityFilter, statusFilter]);

  const loadRecipients = useCallback(async () => {
    try {
      const response = await eletrofrioApi.notificationRecipients();
      setRecipients(response.items || []);
    } catch {
      setRecipients([]);
    }
  }, []);

  const applyDetail = useCallback((response: AnomalyDetail) => {
    setDetail(response);
    setSelectedId(response.id);
    const firstRecipient = recipients.find((recipient) => {
      if (!recipient.enabled) return false;
      if (!response.customer_id) return recipient.role === "admin";
      return String(recipient.customer_id || "") === String(response.customer_id);
    });
    setRecipientId(firstRecipient?.id || "");
  }, [recipients]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      setSelectedId(id);
      setDetail(null);
      setBusy("detail");
      setError(null);
      setMessage(null);
      const response = await eletrofrioApi.anomalyDetail(id);
      applyDetail(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao abrir anomalia.");
    } finally {
      setBusy(null);
    }
  }, [applyDetail]);

  const searchByCode = async () => {
    const code = codeSearch.trim();
    if (!code) {
      setError("Informe o código da ocorrência.");
      return;
    }
    try {
      setBusy("code-search");
      setError(null);
      setMessage(null);
      const response = await eletrofrioApi.searchAnomalyByCode(code);
      applyDetail(response);
      setCodeSearch(response.public_code || code.toUpperCase());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nenhuma ocorrência encontrada com esse código.");
    } finally {
      setBusy(null);
    }
  };

  const copyCode = async (code?: string | null) => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setMessage(`Código ${code} copiado.`);
      setError(null);
    } catch {
      setError("Não foi possível copiar o código automaticamente.");
    }
  };

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    void loadRecipients();
  }, [loadRecipients]);

  const criticalCount = useMemo(
    () => items.filter((item) => String(item.severity || "").toLowerCase() === "critical").length,
    [items],
  );
  const reopenedCount = useMemo(
    () => items.filter((item) => item.status === "reopened").length,
    [items],
  );
  const whatsappPending = useMemo(
    () => items.filter((item) => item.whatsapp_status && item.whatsapp_status !== "sent" && item.whatsapp_status !== "dry_run").length,
    [items],
  );

  const refreshOpenDetail = async () => {
    if (!selectedId) return;
    await loadDetail(selectedId);
  };

  const runAction = async (action: BusyAction, task: () => Promise<string | null | undefined>) => {
    try {
      setBusy(action);
      setError(null);
      setMessage(null);
      const resultMessage = await task();
      if (resultMessage) setMessage(resultMessage);
      await loadList();
      await refreshOpenDetail();
    } catch (err) {
      const text = err instanceof Error ? err.message : "Ação não concluída.";
      if (text.includes("já foi enviada")) setDuplicateBlocked(true);
      setError(text);
    } finally {
      setBusy(null);
    }
  };

  const selectedSolution = detail?.latest_solution;
  const canSendWhatsapp = Boolean(solutionJson(selectedSolution));
  const detailEvents = detail?.events ?? [];
  const detailNotes = detail?.notes ?? [];
  const detailTickets = detail?.tickets ?? [];
  const selectedRecipients = useMemo(() => {
    if (!detail) return recipients;
    return recipients.filter((recipient) => {
      if (!recipient.enabled) return false;
      if (!detail.customer_id) return recipient.role === "admin";
      return recipient.role === "admin" || String(recipient.customer_id || "") === String(detail.customer_id);
    });
  }, [detail, recipients]);

  const closeDrawer = () => {
    setSelectedId(null);
    setDetail(null);
    setMessage(null);
    setError(null);
    setDuplicateBlocked(false);
  };

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sky-100 bg-white/85 p-4 shadow-sm shadow-sky-100/40">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-sky-700">Ocorrências operacionais</p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">Anomalias priorizadas até a resolução</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">
              Cada item abre um fluxo completo com diagnóstico, sugestão IA, WhatsApp, chamado, observações e timeline.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadList()}
            disabled={busy === "list"}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-100 bg-white px-4 py-2 text-sm font-semibold text-sky-700 shadow-sm transition hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "list" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Atualizar
          </button>
        </div>

        <form
          className="mt-4 rounded-2xl border border-sky-100 bg-sky-50/60 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void searchByCode();
          }}
        >
          <p className="mb-2 text-sm font-semibold text-sky-900">Consulta rápida por código</p>
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <label className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-sky-500" />
              <input
                value={codeSearch}
                onChange={(event) => setCodeSearch(event.target.value)}
                placeholder="Buscar por código da ocorrência"
                className="h-11 w-full rounded-xl border border-sky-200 bg-white pl-10 pr-3 font-mono text-sm uppercase outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              />
            </label>
            <button
              type="submit"
              disabled={busy === "code-search"}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-sky-700 px-5 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "code-search" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Consultar ocorrência
            </button>
          </div>
        </form>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-red-100 bg-red-50/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-red-500">Críticas ativas</p>
            <p className="mt-1 text-2xl font-semibold text-red-700">{criticalCount}</p>
          </div>
          <div className="rounded-xl border border-amber-100 bg-amber-50/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-600">Reabertas</p>
            <p className="mt-1 text-2xl font-semibold text-amber-800">{reopenedCount}</p>
          </div>
          <div className="rounded-xl border border-sky-100 bg-sky-50/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-600">WhatsApp pendente/falhou</p>
            <p className="mt-1 text-2xl font-semibold text-sky-800">{whatsappPending}</p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_180px_190px]">
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar loja, equipamento, sensor, cliente..."
              className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            />
          </label>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          >
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {error && !selectedId ? (
        <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>
      ) : null}
      {message && !selectedId ? (
        <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{message}</div>
      ) : null}

      <section className="grid gap-3">
        {busy === "list" && !items.length ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-32 animate-pulse rounded-2xl border border-slate-100 bg-white/70" />
          ))
        ) : items.length ? (
          items.map((anomaly) => (
            <div
              key={anomaly.id}
              role="button"
              tabIndex={0}
              onClick={() => void loadDetail(anomaly.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void loadDetail(anomaly.id);
                }
              }}
              className="group cursor-pointer rounded-2xl border border-slate-200 bg-white/90 p-4 text-left shadow-sm shadow-sky-100/30 outline-none transition hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-50/70 hover:shadow-lg hover:shadow-sky-100/60 focus-visible:border-sky-400 focus-visible:ring-2 focus-visible:ring-sky-200"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 font-mono text-xs font-bold text-sky-800">
                      {anomaly.public_code || "Código pendente"}
                    </span>
                    {anomaly.public_code ? (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void copyCode(anomaly.public_code);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
                        aria-label={`Copiar código ${anomaly.public_code}`}
                      >
                        <Copy className="h-3.5 w-3.5" />
                        Copiar
                      </button>
                    ) : null}
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${severityClass(anomaly.severity)}`}>
                      {severityLabel(anomaly.severity)}
                    </span>
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${statusClass(anomaly.status)}`}>
                      {statusLabel(anomaly.status)}
                    </span>
                    {anomaly.recurrence_count ? (
                      <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-700">
                        Recorrência {anomaly.recurrence_count}
                      </span>
                    ) : null}
                    {anomaly.whatsapp_sent_at ? (
                      <span className="rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-xs font-bold text-teal-700">
                        WhatsApp {anomaly.whatsapp_status || "registrado"}
                      </span>
                    ) : null}
                    {anomaly.ticket_opened_at ? (
                      <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-bold text-violet-700">
                        Chamado aberto
                      </span>
                    ) : null}
                  </div>
                  <h3 className="mt-3 text-lg font-semibold text-slate-950 transition group-hover:text-sky-800">{anomalyTitle(anomaly)}</h3>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">{anomaly.message || anomaly.technical_reason || "Sem descrição adicional."}</p>
                  <div className="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-4">
                    <span><strong className="text-slate-800">Loja:</strong> {storeLabel(anomaly)}</span>
                    <span><strong className="text-slate-800">Equipamento:</strong> {equipmentLabel(anomaly)}</span>
                    <span><strong className="text-slate-800">Valor:</strong> {anomaly.value_label || (anomaly.value ?? "-")}</span>
                    <span><strong className="text-slate-800">Aberta:</strong> {anomaly.open_hours ?? 0}h</span>
                  </div>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-right text-sm text-slate-600">
                  <p className="font-semibold text-slate-900">Score {Math.round(Number(anomaly.priority_score || 0))}</p>
                  <p>{formatDate(anomaly.last_seen_at || anomaly.detected_at)}</p>
                  <p className="mt-2 text-xs font-semibold text-sky-700 opacity-0 transition group-hover:opacity-100">
                    Abrir detalhes
                  </p>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-8 text-center text-slate-600">
            Nenhuma anomalia encontrada para os filtros atuais.
          </div>
        )}
      </section>

      {selectedId && typeof document !== "undefined" ? createPortal((
        <div
          className="anomaly-modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-md sm:p-5"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 2147483647,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            background: "rgba(15, 23, 42, 0.62)",
            backdropFilter: "blur(10px)",
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Detalhes da ocorrência"
            className="anomaly-modal-shell flex h-[94vh] w-full max-w-[1560px] animate-[modal-enter_180ms_ease-out] flex-col overflow-hidden rounded-[28px] border border-white/60 bg-slate-50 text-slate-900 shadow-2xl shadow-slate-950/30 ring-1 ring-slate-950/10"
            style={{
              position: "relative",
              zIndex: 2147483647,
              width: "min(1560px, calc(100vw - 32px))",
              height: "min(94vh, 980px)",
              maxHeight: "calc(100vh - 24px)",
              overflow: "hidden",
              borderRadius: "28px",
              border: "1px solid rgba(203, 213, 225, 0.95)",
              background: "#f8fafc",
              color: "#0f172a",
              boxShadow: "0 28px 90px rgba(15, 23, 42, 0.38)",
            }}
          >
            <div className="anomaly-modal-header relative overflow-hidden border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur xl:px-6">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-sky-500 via-cyan-300 to-emerald-300" />
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Fluxo operacional</p>
                  <h2 className="mt-1 max-w-5xl text-balance text-2xl font-semibold text-slate-950">
                    {detail ? anomalyTitle(detail) : "Carregando anomalia..."}
                  </h2>
                  {detail ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-1.5 font-mono text-sm font-bold text-sky-800">
                        {detail.public_code || "Código pendente"}
                      </span>
                      {detail.public_code ? (
                        <button
                          type="button"
                          onClick={() => void copyCode(detail.public_code)}
                          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm transition hover:bg-slate-50"
                        >
                          <Copy className="h-3.5 w-3.5" />
                          Copiar código
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={busy === "ensure-code"}
                          onClick={() => void runAction("ensure-code", async () => {
                            const updated = await eletrofrioApi.ensureAnomalyPublicCode(detail.id);
                            setDetail((current) => current ? { ...current, ...updated } : current);
                            return `Código ${updated.public_code} gerado.`;
                          })}
                          className="inline-flex items-center gap-1 rounded-lg bg-sky-700 px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-60"
                        >
                          {busy === "ensure-code" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                          Gerar código
                        </button>
                      )}
                      <span className="text-sm text-slate-600">
                        {storeLabel(detail)} • {equipmentLabel(detail)} • aberta há {detail.open_hours ?? 0}h
                      </span>
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={closeDrawer}
                  className="shrink-0 rounded-2xl border border-slate-200 bg-white p-3 text-slate-500 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
                  aria-label="Fechar detalhes"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              {detail ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${severityClass(detail.severity)}`}>
                    {severityLabel(detail.severity)}
                  </span>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${statusClass(detail.status)}`}>
                    {statusLabel(detail.status)}
                  </span>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-600">
                    Sensor {detail.sensor_id || "-"}
                  </span>
                </div>
              ) : null}
            </div>

            {!detail ? (
              <div className="anomaly-modal-body flex flex-1 items-center justify-center bg-gradient-to-br from-slate-50 via-white to-sky-50/50 text-slate-600">
                {error && busy !== "detail" ? (
                  <div className="max-w-lg rounded-3xl border border-red-100 bg-white px-6 py-5 text-center shadow-lg shadow-red-100/50">
                    <X className="mx-auto h-7 w-7 text-red-600" />
                    <p className="mt-3 text-sm font-semibold text-slate-900">Não consegui abrir os detalhes desta ocorrência.</p>
                    <p className="mt-1 text-sm text-red-700">{error}</p>
                    <div className="mt-4 flex flex-wrap justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => selectedId && void loadDetail(selectedId)}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-800"
                      >
                        Tentar novamente
                      </button>
                      <button
                        type="button"
                        onClick={closeDrawer}
                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                      >
                        Fechar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-3xl border border-sky-100 bg-white px-6 py-5 text-center shadow-lg shadow-sky-100/50">
                    <Loader2 className="mx-auto h-7 w-7 animate-spin text-sky-700" />
                    <p className="mt-3 text-sm font-semibold text-slate-900">Carregando detalhes da ocorrência...</p>
                    <p className="mt-1 text-xs text-slate-500">Buscando histórico, solução e dados técnicos.</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="anomaly-modal-body flex-1 overflow-y-auto bg-gradient-to-br from-slate-50 via-white to-sky-50/50 p-4 xl:p-5">
                {message ? (
                  <div className="mb-4 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{message}</div>
                ) : null}
                {error ? (
                  <div className="mb-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div>
                ) : null}

                <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.85fr)]">
                  <div className="space-y-4">
                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Dados técnicos</h3>
                      <div className="mt-3 grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                        <Info label="Código da ocorrência" value={detail.public_code || "Código pendente"} />
                        <Info label="Loja/unidade" value={storeLabel(detail)} />
                        <Info label="Equipamento" value={equipmentLabel(detail)} />
                        <Info label="Tag/dispositivo" value={detail.tag || detail.dispositivo_id || detail.equipment_id || "-"} />
                        <Info label="Sensor" value={detail.sensor_id || "-"} />
                        <Info label="Valor atual" value={detail.value_label || String(detail.value ?? "-")} />
                        <Info label="Faixa esperada" value={detail.expected_range_label || "-"} />
                        <Info label="Desvio" value={detail.deviation_label || "-"} />
                        <Info label="Detecção" value={formatDate(detail.detected_at)} />
                        <Info label="Recorrência" value={String(detail.recurrence_count || 0)} />
                      </div>
                    </section>

                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Diagnóstico operacional</h3>
                      <div className="mt-3 space-y-3 text-sm leading-6 text-slate-700">
                        <p><strong>Descrição:</strong> {detail.message || anomalyTitle(detail)}</p>
                        <p><strong>Impacto provável:</strong> {actionImpact(detail)}</p>
                        <p><strong>Recomendação inicial:</strong> {detail.recommended_action || "Validar condição operacional e evidências no local."}</p>
                        <p><strong>Motivo técnico:</strong> {detail.technical_reason || "Sem motivo técnico estruturado além da evidência coletada."}</p>
                        <pre className="max-h-44 overflow-auto rounded-2xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
                          {evidencePreview(detail)}
                        </pre>
                      </div>
                    </section>

                    <section className="rounded-3xl border border-sky-100 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-sky-700">Sugestão IA</h3>
                          <p className="mt-1 text-sm text-slate-600">Gerada apenas sob demanda e reaproveitada quando a anomalia não mudou.</p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            void runAction("suggest", async () => {
                              const response = await eletrofrioApi.suggestAnomalySolution(detail.id);
                              setDetail((current) =>
                                current
                                  ? { ...current, ...response.anomaly, latest_solution: response.solution }
                                  : current,
                              );
                              return response.cached ? "Sugestão recente reutilizada do cache." : "Sugestão de correção gerada e registrada.";
                            })
                          }
                          disabled={busy === "suggest"}
                          className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {busy === "suggest" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                          Gerar sugestão de correção
                        </button>
                      </div>

                      {selectedSolution ? (
                        <div className="mt-4 rounded-2xl border border-sky-100 bg-sky-50/60 p-4">
                          <div className="mb-3 flex flex-wrap gap-2 text-xs font-bold">
                            <span className="rounded-full border border-sky-200 bg-white px-2.5 py-1 text-sky-700">
                              {selectedSolution.used_ai ? "IA usada" : "Fallback local"}
                            </span>
                            {selectedSolution.cached ? (
                              <span className="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-emerald-700">Cache</span>
                            ) : null}
                            {selectedSolution.created_at ? (
                              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-600">
                                {formatDate(selectedSolution.created_at)}
                              </span>
                            ) : null}
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            {solutionLines(selectedSolution).map(([label, value]) => (
                              <div key={label} className="rounded-xl bg-white/80 p-3 text-sm shadow-sm shadow-sky-100/40">
                                <p className="font-semibold text-slate-900">{label}</p>
                                <p className="mt-1 whitespace-pre-wrap text-slate-700">{String(value)}</p>
                              </div>
                            ))}
                          </div>

                          <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                            <select
                              value={recipientId}
                              onChange={(event) => setRecipientId(event.target.value)}
                              className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                            >
                              <option value="">Destinatário automático do cliente</option>
                              {selectedRecipients.map((recipient) => (
                                <option key={recipient.id} value={recipient.id}>
                                  {recipient.name || recipient.phone} - {recipient.role}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              onClick={() =>
                                void runAction("whatsapp", async () => {
                                  const response = await eletrofrioApi.sendAnomalyWhatsapp(detail.id, {
                                    recipient_id: recipientId || undefined,
                                    confirm_duplicate: duplicateBlocked,
                                  });
                                  setDuplicateBlocked(false);
                                  if (response.status === "whatsapp_disconnected") return "WhatsApp desconectado. Envio não realizado.";
                                  if (response.status === "dry_run") return "Dry-run registrado. Nenhuma mensagem real foi enviada.";
                                  if (response.sent) return "Sugestão enviada por WhatsApp e registrada no histórico.";
                                  return response.message || "Envio WhatsApp processado.";
                                })
                              }
                              disabled={busy === "whatsapp" || !canSendWhatsapp}
                              className="inline-flex items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {busy === "whatsapp" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                              {duplicateBlocked ? "Confirmar reenvio" : "Enviar por WhatsApp"}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-4 rounded-xl border border-dashed border-sky-200 bg-sky-50/40 p-4 text-sm text-slate-600">
                          Nenhuma sugestão gerada ainda. Clique no botão para criar uma recomendação prática usando os dados desta anomalia.
                        </div>
                      )}
                    </section>
                  </div>

                  <aside className="space-y-4 xl:sticky xl:top-0 xl:self-start">
                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Ações rápidas</h3>
                      <div className="mt-3 grid gap-2">
                        <ActionButton busy={busy === "status"} onClick={() => void runAction("status", async () => {
                          await eletrofrioApi.updateOperationalAnomalyStatus(detail.id, "acknowledged", note || undefined);
                          return "Anomalia reconhecida.";
                        })}>
                          Reconhecer
                        </ActionButton>
                        <ActionButton busy={busy === "status"} onClick={() => void runAction("status", async () => {
                          await eletrofrioApi.updateOperationalAnomalyStatus(detail.id, "investigating", note || undefined);
                          return "Anomalia marcada em investigação.";
                        })}>
                          Investigar
                        </ActionButton>
                        <ActionButton busy={busy === "resolve"} onClick={() => void runAction("resolve", async () => {
                          await eletrofrioApi.resolveOperationalAnomaly(detail.id, note || undefined);
                          return "Anomalia marcada como resolvida.";
                        })}>
                          Marcar como resolvida
                        </ActionButton>
                        <ActionButton busy={busy === "reopen"} onClick={() => void runAction("reopen", async () => {
                          await eletrofrioApi.reopenOperationalAnomaly(detail.id, note || undefined);
                          return "Anomalia reaberta e priorizada.";
                        })}>
                          Reabrir anomalia
                        </ActionButton>
                        <ActionButton busy={busy === "ticket"} onClick={() => void runAction("ticket", async () => {
                          await eletrofrioApi.openAnomalyTicket(detail.id, { description: ticketDescription || undefined, priority: detail.severity });
                          setTicketDescription("");
                          return "Chamado interno aberto e registrado.";
                        })}>
                          Abrir chamado
                        </ActionButton>
                        <ActionButton busy={busy === "status"} onClick={() => void runAction("status", async () => {
                          const suggestion = solutionJson(selectedSolution)?.immediate_action;
                          if (suggestion) {
                            await eletrofrioApi.addAnomalyNote(detail.id, `Ação recomendada: ${suggestion}`);
                          }
                          await eletrofrioApi.updateOperationalAnomalyStatus(detail.id, "investigating", "Ação recomendada registrada.");
                          return "Ação recomendada registrada.";
                        })}>
                          Recomendar ação
                        </ActionButton>
                        <ActionButton busy={busy === "status"} onClick={() => void runAction("status", async () => {
                          await eletrofrioApi.updateOperationalAnomalyStatus(detail.id, "ignored", note || "Ignorada temporariamente pela operação.");
                          return "Anomalia ignorada temporariamente e mantida no histórico.";
                        })}>
                          Ignorar temporariamente
                        </ActionButton>
                        <a
                          href="#anomaly-history"
                          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                        >
                          <History className="h-4 w-4" />
                          Ver histórico completo
                        </a>
                      </div>
                    </section>

                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Observação e chamado</h3>
                      <div className="mt-3 grid gap-3">
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Adicionar observação</span>
                          <textarea
                            value={note}
                            onChange={(event) => setNote(event.target.value)}
                            rows={4}
                            placeholder="Ex.: Loja informou porta aberta durante carga."
                            className="mt-2 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                          />
                          <button
                            type="button"
                            onClick={() => void runAction("note", async () => {
                              await eletrofrioApi.addAnomalyNote(detail.id, note);
                              setNote("");
                              return "Observação registrada no histórico.";
                            })}
                            disabled={busy === "note" || note.trim().length < 3}
                            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {busy === "note" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                            Salvar observação
                          </button>
                        </label>
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Descrição adicional do chamado</span>
                          <textarea
                            value={ticketDescription}
                            onChange={(event) => setTicketDescription(event.target.value)}
                            rows={4}
                            placeholder="Contexto para equipe técnica ou integração GLPI futura."
                            className="mt-2 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                          />
                        </label>
                      </div>
                    </section>

                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Observações avançadas</h3>
                      <div className="mt-3 grid gap-2">
                        {detailNotes.length ? (
                          detailNotes.map((item) => (
                            <div key={item.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm">
                              <p className="font-semibold text-slate-900">{item.author_name || item.user_id || "Operação"} • {formatDate(item.created_at)}</p>
                              <p className="mt-1 text-slate-700">{item.note}</p>
                            </div>
                          ))
                        ) : (
                          <p className="text-sm text-slate-500">Nenhuma observação registrada.</p>
                        )}
                      </div>
                    </section>

                    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40">
                      <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Chamados</h3>
                      <div className="mt-3 grid gap-2">
                        {detailTickets.length ? (
                          detailTickets.map((ticket) => (
                            <div key={ticket.id} className="rounded-xl border border-violet-100 bg-violet-50/60 p-3 text-sm">
                              <p className="font-semibold text-violet-900">{ticket.title}</p>
                              <p className="mt-1 text-violet-700">#{ticket.id} • {ticket.status} • prioridade {ticket.priority}</p>
                            </div>
                          ))
                        ) : (
                          <p className="text-sm text-slate-500">Nenhum chamado interno aberto.</p>
                        )}
                      </div>
                    </section>
                  </aside>

                  <section id="anomaly-history" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm shadow-sky-100/40 xl:col-span-2">
                    <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-500">Histórico completo</h3>
                    <div className="mt-4 grid gap-3 xl:grid-cols-2">
                      {detailEvents.length ? detailEvents.map((event) => (
                        <div key={event.id} className="flex gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
                          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500">
                            {eventIcon(event)}
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-slate-900">
                              {compactDate(event.created_at)} - {event.public_code || detail.public_code || "Código pendente"} - {event.title}
                            </p>
                            {event.description ? <p className="mt-1 text-sm text-slate-600">{event.description}</p> : null}
                            {event.old_status || event.new_status ? (
                              <p className="mt-1 text-xs font-semibold text-slate-500">
                                {event.old_status ? statusLabel(event.old_status) : "-"} → {event.new_status ? statusLabel(event.new_status) : "-"}
                              </p>
                            ) : null}
                          </div>
                        </div>
                      )) : (
                        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-500">
                          Nenhum evento registrado ainda para esta ocorrência.
                        </div>
                      )}
                    </div>
                  </section>
                </div>
              </div>
            )}
          </div>
        </div>
      ), document.body) : null}
    </div>
  );
}

function Info({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function ActionButton({
  children,
  busy,
  onClick,
}: {
  children: ReactNode;
  busy?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {children}
    </button>
  );
}
