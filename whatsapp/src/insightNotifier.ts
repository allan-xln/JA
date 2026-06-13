import { config } from "./config.js";
import { logCommunication, logWhatsappMessage } from "./communicationLog.js";
import { sendWhatsAppMessage } from "./messageSender.js";
import { patchRows, selectRows } from "./supabase.js";
import { getConnectedPhone, getWhatsAppStatus } from "./whatsappClient.js";

type Insight = {
  id: string;
  insight_type: string;
  severity: "info" | "warning" | "critical" | string;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  title: string;
  summary: string;
  technical_reason: string | null;
  recommended_action: string | null;
  evidence_json: Record<string, unknown> | null;
  created_at: string;
  whatsapp_sent_at: string | null;
  ticket_opened_at: string | null;
};

type Anomaly = {
  id: string;
  status: string;
  severity: "info" | "warning" | "critical" | string;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  equipment_id?: number | null;
  tag: string | null;
  title: string | null;
  summary: string | null;
  message: string | null;
  technical_reason: string | null;
  recommended_action: string | null;
  evidence_json: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  detected_at: string;
  whatsapp_sent_at: string | null;
};

type NotificationItem = {
  source: "insight" | "anomaly";
  id: string;
  severity: string;
  loja_id: number | null;
  loja_nome: string | null;
  dispositivo_id: number | null;
  tag: string | null;
  title: string | null;
  summary: string | null;
  message: string | null;
  technical_reason: string | null;
  recommended_action: string | null;
  evidence_json: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  whatsapp_sent_at: string | null;
};

type SummaryTotals = {
  total: number;
  critical: number;
  warning: number;
  info: number;
  anomalies: number;
  insights: number;
};

type CollectorRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  units_count: number;
  alarms_count: number;
  telemetry_count: number;
  anomalies_count?: number | null;
};

type IgnoreReason =
  | "whatsapp_disabled"
  | "no_recipients"
  | "already_sent"
  | "insufficient_evidence"
  | "low_priority"
  | "device_cooldown"
  | "store_cooldown"
  | "send_error";

function minutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function hasEnoughEvidence(item: NotificationItem) {
  const evidence = item.evidence_json || {};
  return evidence.sufficient_evidence !== false;
}

function numberFromEvidence(value: unknown) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

function compactText(value: string | null | undefined, fallback: string, maxLength = 210) {
  const text = String(value || fallback).replace(/\s+/g, " ").trim();
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 3).trim()}...`;
}

function portalFooter() {
  return `Mais detalhes no portal:\n${config.appPublicUrl}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function ruleEvaluation(item: NotificationItem) {
  return asRecord(item.metadata?.rule_evaluation);
}

function warningHasOperationalWeight(item: NotificationItem) {
  const evidence = item.evidence_json || {};
  const deviceSummary = evidence.device_alarm_summary as Record<string, unknown> | undefined;
  const deviceMetrics = evidence.device_metrics as Record<string, unknown> | undefined;
  const storeMetrics = evidence.store_metrics as Record<string, unknown> | undefined;

  const alarmCount =
    numberFromEvidence(deviceSummary?.alarm_count) ||
    numberFromEvidence(deviceMetrics?.alarm_count) ||
    numberFromEvidence(storeMetrics?.alarm_count);

  const isCriticalStore =
    evidence.special_rule === "loja_315" ||
    item.loja_id === 315 ||
    numberFromEvidence(storeMetrics?.alarm_count) >= 5;

  return alarmCount >= 2 || isCriticalStore || hasCriticalTerm(item);
}

function normalize(value: string) {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function itemText(item: NotificationItem) {
  return normalize(
    [
      item.source,
      item.severity,
      item.title,
      item.summary,
      item.message,
      item.technical_reason,
      item.recommended_action,
      item.tag,
      JSON.stringify(item.evidence_json || {}),
      JSON.stringify(item.metadata || {}),
    ].join(" "),
  );
}

function hasCriticalTerm(item: NotificationItem) {
  const text = itemText(item);
  return [
    "alta temperatura",
    "nivel de liquido",
    "nivel liquido",
    "falha de compressor",
    "compressor",
    "offline",
    "baixa pressao",
    "degelo",
    "comunicacao",
    "rack",
    "camara",
  ].some((term) => text.includes(term));
}

function operationalEvidenceText(item: NotificationItem) {
  const raw = item.message || item.summary || item.title || "";
  if (!normalize(raw).includes("analise gerada por regras deterministicas")) {
    return raw || "ocorrência operacional relevante registrada recentemente.";
  }

  const alarm = item.evidence_json?.alarm as Record<string, unknown> | undefined;
  const alarmMessage = String(alarm?.alarm_message || alarm?.alarm_type || "");
  const tag = item.tag || String(alarm?.tag || "");
  const loja = item.loja_nome || String(alarm?.loja_nome || "");

  if (alarmMessage) {
    return `evidência operacional registrada: ${alarmMessage}${tag ? ` no equipamento ${tag}` : ""}${loja ? ` da loja ${loja}` : ""}.`;
  }
  if (tag) {
    return `equipamento ${tag} exige acompanhamento operacional${loja ? ` na loja ${loja}` : ""}.`;
  }
  return "ocorrência operacional relevante registrada recentemente.";
}

function itemPriorityScore(item: NotificationItem) {
  const severity = normalize(item.severity || "");
  const evidence = item.evidence_json || {};
  const metadata = item.metadata || {};
  const score = numberFromEvidence(evidence.operational_score) || numberFromEvidence(metadata.operational_score);
  let priority = score;
  if (["critical", "critico", "critica"].includes(severity)) priority += 100;
  if (["warning", "alerta", "atencao", "media", "medio"].includes(severity)) priority += 45;
  if (hasCriticalTerm(item)) priority += 25;
  if (warningHasOperationalWeight(item)) priority += 15;
  return priority;
}

function severityBucket(item: NotificationItem): "critical" | "warning" | "info" {
  const severity = normalize(item.severity || "");
  if (["critical", "critico", "critica", "high", "alta", "alto"].includes(severity)) return "critical";
  if (["warning", "alerta", "atencao", "atenção", "media", "medio", "medium"].includes(severity)) return "warning";
  return "info";
}

function summaryTotals(items: NotificationItem[]): SummaryTotals {
  return items.reduce<SummaryTotals>(
    (totals, item) => {
      totals.total += 1;
      const sourceKey = item.source === "anomaly" ? "anomalies" : "insights";
      const severityKey = severityBucket(item);
      totals[sourceKey] += 1;
      totals[severityKey] += 1;
      return totals;
    },
    { total: 0, critical: 0, warning: 0, info: 0, anomalies: 0, insights: 0 },
  );
}

function shouldNotifyItem(item: NotificationItem) {
  const severity = normalize(item.severity || "");
  if (item.whatsapp_sent_at) return false;
  if (!hasEnoughEvidence(item)) return false;
  if (["critical", "critico", "critica"].includes(severity)) return true;
  if (["warning", "alerta", "atencao", "media", "medio"].includes(severity)) return warningHasOperationalWeight(item);
  if (hasCriticalTerm(item)) return true;
  return false;
}

function ignoreReasonForItem(item: NotificationItem): IgnoreReason | null {
  if (item.whatsapp_sent_at) return "already_sent";
  if (!hasEnoughEvidence(item)) return "insufficient_evidence";
  if (!shouldNotifyItem(item)) return "low_priority";
  return null;
}

async function recentlySentForDevice(dispositivoId: number | null) {
  if (!dispositivoId) return false;
  const insightRows = await selectRows<Insight>("eletrofrio_ai_insights", {
    select: "id",
    dispositivo_id: `eq.${dispositivoId}`,
    whatsapp_sent_at: `gte.${minutesAgo(config.minIntervalMinutesPerDevice)}`,
    limit: 1,
  });
  if (insightRows.length > 0) return true;

  const anomalyRows = await selectRows<Anomaly>("eletrofrio_anomalies", {
    select: "id",
    equipment_id: `eq.${dispositivoId}`,
    whatsapp_sent_at: `gte.${minutesAgo(config.minIntervalMinutesPerDevice)}`,
    limit: 1,
  });
  return anomalyRows.length > 0;
}

async function recentlySentForStore(lojaId: number | null) {
  if (!lojaId) return false;
  const insightRows = await selectRows<Insight>("eletrofrio_ai_insights", {
    select: "id",
    loja_id: `eq.${lojaId}`,
    whatsapp_sent_at: `gte.${minutesAgo(config.minIntervalMinutesPerStore)}`,
    limit: 1,
  });
  if (insightRows.length > 0) return true;

  const anomalyRows = await selectRows<Anomaly>("eletrofrio_anomalies", {
    select: "id",
    loja_id: `eq.${lojaId}`,
    whatsapp_sent_at: `gte.${minutesAgo(config.minIntervalMinutesPerStore)}`,
    limit: 1,
  });
  return anomalyRows.length > 0;
}

function formatOperationalMessage(item: NotificationItem) {
  const loja = item.loja_nome || (item.loja_id ? `unidade ${item.loja_id}` : "loja monitorada");
  const equipamento = item.tag || (item.dispositivo_id ? `dispositivo ${item.dispositivo_id}` : "equipamento monitorado");
  const severity = ["critical", "critico", "critica"].includes(normalize(item.severity || "")) ? "Alta" : "Atenção";
  const evidence = operationalEvidenceText(item);
  const evaluation = ruleEvaluation(item);
  const ruleName = String(item.evidence_json?.rule_name || evaluation.rule_name || "");
  const evidenceLevel = String(item.evidence_json?.evidence_level || evaluation.evidence_level || "");
  const action =
    String(item.evidence_json?.recommended_action || evaluation.recommended_action || "") ||
    item.recommended_action ||
    "Verificar operação local, comunicação, porta, carga térmica e condição do equipamento.";

  const message = [
    "🔔 Alerta Eletrofrio",
    `Prioridade: ${severity}`,
    "",
    `Loja: ${loja}`,
    `Equipamento: ${equipamento}`,
    ruleName ? `Regra: ${ruleName}` : "",
    evidenceLevel ? `Evidência: ${evidenceLevel}` : "",
    "",
    `Situação: ${evidence}`,
    "",
    "Próximo passo:",
    action,
    "",
    "Obs.: diagnóstico inicial; confirme a condição no local antes de acionar manutenção.",
    "",
    portalFooter(),
  ]
    .filter(Boolean)
    .join("\n");

  return message.length <= 900 ? message : `${message.slice(0, 856).trim()}...\nObs.: mensagem resumida para o canal operacional.`;
}

function formatSummaryItem(item: NotificationItem, index: number) {
  const loja = item.loja_nome || (item.loja_id ? `unidade ${item.loja_id}` : "loja monitorada");
  const equipamento = item.tag || (item.dispositivo_id ? `dispositivo ${item.dispositivo_id}` : "equipamento monitorado");
  const severity = severityBucket(item) === "critical" ? "crítica" : severityBucket(item) === "warning" ? "atenção" : "informativa";
  const source = item.source === "anomaly" ? "anomalia" : "insight";
  const evidence = compactText(operationalEvidenceText(item), "Ocorrência operacional relevante.", 240);
  const evaluation = ruleEvaluation(item);
  const action =
    String(item.evidence_json?.recommended_action || evaluation.recommended_action || "") ||
    item.recommended_action ||
    "validar leitura local, porta, carga térmica e condição do equipamento.";

  return [
    `${index}. ${loja} - ${equipamento}`,
    `Prioridade: ${severity}. Origem: ${source}.`,
    `Situação: ${evidence}`,
    `Próximo passo: ${compactText(action, "Validar evidência local e condição do equipamento.", 180)}`,
  ].join("\n");
}

function topLabels(items: NotificationItem[], keySelector: (item: NotificationItem) => string, limit = 4) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = keySelector(item);
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit)
    .map(([label, count]) => `${label} (${count})`);
}

function selectSummaryHighlights(items: NotificationItem[]) {
  const seen = new Set<string>();
  const sorted = [...items].sort((left, right) => {
    const priorityDiff = itemPriorityScore(right) - itemPriorityScore(left);
    if (priorityDiff) return priorityDiff;
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  });

  const selected: NotificationItem[] = [];
  for (const item of sorted) {
    const key = `${item.loja_id || item.loja_nome || "loja"}:${item.dispositivo_id || item.tag || item.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    selected.push(item);
    if (selected.length >= 10) break;
  }
  return selected;
}

function formatOperationalSummaryMessage(run: CollectorRun | null, items: NotificationItem[], allItems: NotificationItem[]) {
  const finishedAt = run?.finished_at || run?.started_at || new Date().toISOString();
  const totals = summaryTotals(allItems);
  const criticalItems = allItems.filter((item) => severityBucket(item) === "critical");
  const warningItems = allItems.filter((item) => severityBucket(item) === "warning");
  const topStores = topLabels(allItems, (item) => item.loja_nome || (item.loja_id ? `Loja ${item.loja_id}` : ""));
  const topEquipment = topLabels(allItems, (item) => item.tag || (item.dispositivo_id ? `Dispositivo ${item.dispositivo_id}` : ""));
  const header = [
    "📋 Resumo operacional Eletrofrio",
    "",
    `Atualização: ${new Date(finishedAt).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}.`,
    `Base da coleta: ${run?.units_count ?? 0} lojas, ${run?.alarms_count ?? 0} alarmes e ${run?.telemetry_count ?? 0} telemetrias.`,
    `Ocorrências relevantes: ${totals.total} (${totals.critical} críticas, ${totals.warning} em atenção, ${totals.info} informativas).`,
    topStores.length ? `Lojas com mais ocorrências: ${topStores.join("; ")}.` : "",
    topEquipment.length ? `Equipamentos mais recorrentes: ${topEquipment.join("; ")}.` : "",
    criticalItems.length || warningItems.length
      ? `Prioridade agora: tratar ${criticalItems.length} críticas e acompanhar ${warningItems.length} em atenção.`
      : "Prioridade agora: acompanhar ocorrências informativas e manter a coleta ativa.",
    "",
    "Destaques principais:",
  ].filter(Boolean).join("\n");
  const body = items.map((item, index) => formatSummaryItem(item, index + 1)).join("\n\n");
  const footer = `\n\nObs.: diagnóstico inicial; valide a condição no local antes de acionar manutenção.\n\n${portalFooter()}`;
  const message = `${header}\n${body}${footer}`;
  return message.length <= 3600 ? message : `${message.slice(0, 3548).trim()}...\n\nObs.: resumo reduzido para o canal operacional.`;
}

function addReason(reasons: Record<string, number>, reason: IgnoreReason) {
  reasons[reason] = (reasons[reason] || 0) + 1;
}

function operationalRecipients() {
  if (config.allowedRecipients.length) return config.allowedRecipients;
  const connectedPhone = getConnectedPhone();
  return connectedPhone ? [connectedPhone] : [];
}

function insightToItem(insight: Insight): NotificationItem {
  return {
    source: "insight",
    id: insight.id,
    severity: insight.severity,
    loja_id: insight.loja_id,
    loja_nome: insight.loja_nome,
    dispositivo_id: insight.dispositivo_id,
    tag: insight.tag,
    title: insight.title,
    summary: insight.summary,
    message: insight.summary || insight.title,
    technical_reason: insight.technical_reason,
    recommended_action: insight.recommended_action,
    evidence_json: insight.evidence_json,
    created_at: insight.created_at,
    whatsapp_sent_at: insight.whatsapp_sent_at,
  };
}

function anomalyToItem(anomaly: Anomaly): NotificationItem {
  return {
    source: "anomaly",
    id: anomaly.id,
    severity: anomaly.severity,
    loja_id: anomaly.loja_id,
    loja_nome: anomaly.loja_nome,
    dispositivo_id: anomaly.dispositivo_id || anomaly.equipment_id || null,
    tag: anomaly.tag,
    title: anomaly.title,
    summary: anomaly.summary,
    message: anomaly.message || anomaly.summary || anomaly.title,
    technical_reason: anomaly.technical_reason,
    recommended_action: anomaly.recommended_action,
    evidence_json: anomaly.evidence_json,
    metadata: anomaly.metadata,
    created_at: anomaly.detected_at,
    whatsapp_sent_at: anomaly.whatsapp_sent_at,
  };
}

async function patchSent(item: NotificationItem) {
  const now = new Date().toISOString();
  if (item.source === "anomaly") {
    await patchRows("eletrofrio_anomalies", { id: item.id }, { whatsapp_sent_at: now, whatsapp_status: "sent" });
    return;
  }
  await patchRows("eletrofrio_ai_insights", { id: item.id }, { whatsapp_sent_at: now });
}

async function latestSuccessfulRun() {
  const rows = await selectRows<CollectorRun>("eletrofrio_collector_runs", {
    select: "*",
    order: "started_at.desc",
    limit: 8,
  });
  return rows.find((row) => ["success", "partial_success"].includes(row.status)) || rows[0] || null;
}

async function currentNotificationItems() {
  const recentInsights = await selectRows<Insight>("eletrofrio_ai_insights", {
    select: "*",
    order: "created_at.desc",
    limit: 120,
  });
  const openAnomalies = await selectRows<Anomaly>("eletrofrio_anomalies", {
    select: "*",
    status: "eq.open",
    order: "detected_at.desc",
    limit: 120,
  });
  return [
    ...openAnomalies.map(anomalyToItem),
    ...recentInsights.map(insightToItem),
  ];
}

async function selectSummaryItems(items: NotificationItem[]) {
  const selected: NotificationItem[] = [];
  const seen = new Set<string>();
  const sorted = items
    .filter((item) => shouldNotifyItem(item))
    .sort((left, right) => itemPriorityScore(right) - itemPriorityScore(left));

  for (const item of sorted) {
    if (await recentlySentForDevice(item.dispositivo_id)) continue;
    if (await recentlySentForStore(item.loja_id)) continue;
    const key = `${item.loja_id || "loja"}:${item.dispositivo_id || item.tag || item.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    selected.push(item);
    if (selected.length >= 5) break;
  }
  return selected;
}

export async function sendOperationalSummary() {
  const recipients = operationalRecipients();
  const recipientSource = config.allowedRecipients.length ? "allowed_list" : "connected_phone";
  const status = getWhatsAppStatus();

  if (!config.enabled) {
    return {
      ok: false,
      dry_run: config.dryRun,
      message: "Canal operacional desativado. Ative WHATSAPP_ENABLED para enviar.",
      selected_count: 0,
      sent_count: 0,
      recipients: recipients.length,
      recipient_source: recipientSource,
      items: [],
    };
  }

  if (!status.connected && !config.dryRun) {
    return {
      ok: false,
      dry_run: config.dryRun,
      message: "Canal operacional desconectado. Conecte o WhatsApp antes de enviar.",
      selected_count: 0,
      sent_count: 0,
      recipients: recipients.length,
      recipient_source: recipientSource,
      items: [],
    };
  }

  if (!recipients.length) {
    return {
      ok: false,
      dry_run: config.dryRun,
      message: "Nenhum destinatário autorizado encontrado para o resumo operacional.",
      selected_count: 0,
      sent_count: 0,
      recipients: 0,
      recipient_source: "none",
      items: [],
    };
  }

  const run = await latestSuccessfulRun();
  const current = await currentNotificationItems();
  const summaryItems = selectSummaryHighlights(current);
  const pendingSelected = await selectSummaryItems(current);

  if (!summaryItems.length) {
    return {
      ok: true,
      dry_run: config.dryRun,
      message: "Nenhuma ocorrência real encontrada para o resumo operacional.",
      selected_count: 0,
      sent_count: 0,
      recipients: recipients.length,
      recipient_source: recipientSource,
      items: [],
    };
  }

  const totals = summaryTotals(current);
  const message = formatOperationalSummaryMessage(run, summaryItems, current);
  const items = summaryItems.map((item) => ({
    id: item.id,
    source: item.source,
    loja_nome: item.loja_nome,
    tag: item.tag,
    severity: item.severity,
    reason: operationalEvidenceText(item),
  }));

  if (config.dryRun) {
    console.log(`[WA][DRY-RUN][SUMMARY] ${message}`);
    await logWhatsappMessage({
      phone: recipients.join(", "),
      direction: "outgoing",
      type: "operational_summary",
      message,
      dry_run: true,
      delivery_status: "dry-run",
    });
    await logCommunication({
      type: "operational_summary",
      direction: "outgoing",
      phone: recipients.join(", "),
      message,
      status: "dry-run",
      source: "sistema",
      payload_json: { selected_count: summaryItems.length, recipients: recipients.length, totals, items },
    });
    return {
      ok: true,
      dry_run: true,
      message: "Resumo operacional preparado em modo validação.",
      selected_count: summaryItems.length,
      sent_count: 0,
      recipients: recipients.length,
      recipient_source: recipientSource,
      totals,
      items,
      preview: message,
    };
  }

  try {
    for (const recipient of recipients) {
      await sendWhatsAppMessage(recipient, message);
    }
  } catch (error) {
    await logCommunication({
      type: "operational_summary",
      direction: "outgoing",
      phone: recipients.join(", "),
      message,
      status: "failed",
      source: "sistema",
      payload_json: { selected_count: summaryItems.length, totals, error: error instanceof Error ? error.message : String(error) },
    });
    return {
      ok: false,
      dry_run: false,
      message: error instanceof Error && error.message.includes("não conectado")
        ? "Canal operacional desconectado. Conecte o WhatsApp antes de enviar."
        : error instanceof Error
          ? error.message
          : "Não foi possível enviar o resumo operacional.",
      selected_count: summaryItems.length,
      sent_count: 0,
      recipients: recipients.length,
      recipient_source: recipientSource,
      totals,
      items,
      preview: message,
    };
  }

  for (const item of pendingSelected) {
    await patchSent(item);
  }
  await logWhatsappMessage({
    phone: recipients.join(", "),
    direction: "outgoing",
    type: "operational_summary",
    message,
    dry_run: false,
    delivery_status: "sent",
  });
  await logCommunication({
    type: "operational_summary",
    direction: "outgoing",
    phone: recipients.join(", "),
    message,
    status: "sent",
    source: "sistema",
    payload_json: { selected_count: summaryItems.length, recipients: recipients.length, totals, items },
  });

  return {
    ok: true,
    dry_run: false,
    message: "Resumo operacional enviado para WhatsApp.",
    selected_count: summaryItems.length,
    sent_count: recipients.length,
    recipients: recipients.length,
    recipient_source: recipientSource,
    totals,
    items,
    preview: message,
  };
}

export async function processPendingInsights() {
  const recipients = operationalRecipients();

  if (!config.enabled) {
    return {
      total_analyzed: 0,
      total_eligible: 0,
      total_sent: 0,
      total_ignored: 0,
      ignore_reasons: { whatsapp_disabled: 1 },
      dry_run: config.dryRun,
      processed: 0,
      sent: 0,
      skipped: 0,
      dryRun: 0,
      wouldSend: 0,
      recipients: recipients.length,
      recipient_source: config.allowedRecipients.length ? "allowed_list" : "connected_phone",
      simulated_messages: [],
      notified: [],
    };
  }

  if (!recipients.length) {
    return {
      total_analyzed: 0,
      total_eligible: 0,
      total_sent: 0,
      total_ignored: 0,
      ignore_reasons: { no_recipients: 1 },
      dry_run: config.dryRun,
      processed: 0,
      sent: 0,
      skipped: 0,
      dryRun: 0,
      wouldSend: 0,
      recipients: 0,
      recipient_source: "none",
      simulated_messages: [],
      notified: [],
    };
  }

  const pendingInsights = await selectRows<Insight>("eletrofrio_ai_insights", {
    select: "*",
    whatsapp_sent_at: "is.null",
    order: "created_at.asc",
    limit: 50,
  });
  const pendingAnomalies = await selectRows<Anomaly>("eletrofrio_anomalies", {
    select: "*",
    status: "eq.open",
    whatsapp_sent_at: "is.null",
    order: "detected_at.asc",
    limit: 50,
  });
  const pending = [
    ...pendingAnomalies.map(anomalyToItem),
    ...pendingInsights.map(insightToItem),
  ].sort((left, right) => String(left.created_at).localeCompare(String(right.created_at))).slice(0, 80);

  let eligible = 0;
  let sent = 0;
  let ignored = 0;
  const ignoreReasons: Record<string, number> = {};
  const notified: string[] = [];
  const simulatedMessages: Array<{ id: string; recipients: number; message: string }> = [];

  for (const item of pending) {
    const reason = ignoreReasonForItem(item);
    if (reason) {
      ignored += 1;
      addReason(ignoreReasons, reason);
      continue;
    }
    eligible += 1;
    if (await recentlySentForDevice(item.dispositivo_id)) {
      ignored += 1;
      addReason(ignoreReasons, "device_cooldown");
      continue;
    }
    if (await recentlySentForStore(item.loja_id)) {
      ignored += 1;
      addReason(ignoreReasons, "store_cooldown");
      continue;
    }

    const message = formatOperationalMessage(item);
    if (config.dryRun) {
      console.log(`[WA][DRY-RUN][${item.source.toUpperCase()}] ${item.id}: ${message}`);
      simulatedMessages.push({ id: item.id, recipients: recipients.length, message });
      await logCommunication({
        type: "operational_alert",
        direction: "outgoing",
        phone: recipients.join(", "),
        loja_id: item.loja_id,
        loja_nome: item.loja_nome,
        dispositivo_id: item.dispositivo_id,
        tag: item.tag,
        message,
        status: "dry-run",
        source: "sistema",
        payload_json: { item_id: item.id, item_source: item.source, severity: item.severity },
      });
    } else {
      try {
        for (const recipient of recipients) {
          await sendWhatsAppMessage(recipient, message);
        }
      } catch (error) {
        ignored += 1;
        addReason(ignoreReasons, "send_error");
        console.error("[WA] Falha ao enviar insight operacional:", error);
        await logCommunication({
          type: "operational_alert",
          direction: "outgoing",
          phone: recipients.join(", "),
          loja_id: item.loja_id,
          loja_nome: item.loja_nome,
          dispositivo_id: item.dispositivo_id,
          tag: item.tag,
          message,
          status: "failed",
          source: "sistema",
          payload_json: { item_id: item.id, item_source: item.source, error: error instanceof Error ? error.message : String(error) },
        });
        continue;
      }
      await patchSent(item);
      await logCommunication({
        type: "operational_alert",
        direction: "outgoing",
        phone: recipients.join(", "),
        loja_id: item.loja_id,
        loja_nome: item.loja_nome,
        dispositivo_id: item.dispositivo_id,
        tag: item.tag,
        message,
        status: "sent",
        source: "sistema",
        payload_json: { item_id: item.id, item_source: item.source, severity: item.severity },
      });
      sent += 1;
    }
    notified.push(item.id);
  }

  return {
    total_analyzed: pending.length,
    total_eligible: eligible,
    total_sent: sent,
    total_ignored: ignored,
    ignore_reasons: ignoreReasons,
    dry_run: config.dryRun,
    processed: pending.length,
    sent,
    skipped: ignored,
    dryRun: simulatedMessages.length,
    wouldSend: simulatedMessages.reduce((total, item) => total + item.recipients, 0),
    recipients: recipients.length,
    recipient_source: config.allowedRecipients.length ? "allowed_list" : "connected_phone",
    analyzed_by_source: {
      anomalies: pendingAnomalies.length,
      insights: pendingInsights.length,
    },
    simulated_messages: simulatedMessages,
    notified,
  };
}
