import type { WAMessage, WASocket } from "@whiskeysockets/baileys";
import { logCommunication, logWhatsappMessage } from "./communicationLog.js";
import { config } from "./config.js";
import { sendWhatsAppMessage } from "./messageSender.js";

function extractText(message: WAMessage) {
  const body = message.message;
  return (
    body?.conversation ||
    body?.extendedTextMessage?.text ||
    body?.imageMessage?.caption ||
    body?.videoMessage?.caption ||
    ""
  ).trim();
}

export async function handleIncomingMessage(sock: WASocket, message: WAMessage) {
  if (!message.message || message.key.fromMe || message.key.remoteJid === "status@broadcast") return;

  const sender = message.key.remoteJid || "";
  const originalText = extractText(message);
  const text = originalText.toLowerCase();
  if (!text) return;

  if (isOperationalQuestion(text)) {
    await sock.readMessages([message.key]);
    await logWhatsappMessage({
      phone: sender,
      direction: "incoming",
      type: "incoming_question",
      message: originalText,
      delivery_status: "received",
    });
    await logCommunication({
      type: "incoming_question",
      direction: "incoming",
      phone: sender,
      message: originalText,
      status: "received",
      source: "WhatsApp",
    });
    const answer = await askOperationalAssistant(originalText, sender);
    await sendWhatsAppMessage(sender, answer);
    await logCommunication({
      type: "rag_response",
      direction: "outgoing",
      phone: sender,
      message: answer,
      status: config.dryRun ? "dry-run" : "sent",
      source: "IA operacional",
    });
    return;
  }

  await sock.readMessages([message.key]);
}

export function isOperationalQuestion(text: string) {
  return [
    /\b(status|alertas?|resumo|lojas?|sensores?|equipamentos?|anomalias?|offline|temperatura|critico|crítico|critica|crítica|falhas?|problemas?|camara|câmara|compressor|rack|degelo|press[aã]o|glicol|opera(?:ção|cao|ções|coes))\b/,
    /alta\s+temperatura/,
    /baixa\s+temperatura/,
    /\bqual\s+(sensor|equipamento|loja)\b/,
    /como\s+est[aá]/,
    /como\s+(v[aã]o|andam|est[aã]o)\s+(as\s+)?opera(?:ções|coes)/,
    /teve\s+(alguma\s+)?(anomalia|falha|problema)/,
    /ocorreu\s+hoje/,
    /deu\s+problema/,
  ].some((pattern) => pattern.test(text));
}

type AssistantSource = {
  type?: string;
  label?: string;
  loja_nome?: string | null;
  tag?: string | null;
};

type AssistantAnswer = {
  answer?: string;
  intent?: string;
  intent_label?: string;
  confidence?: number;
  confidence_label?: string;
  summary?: string;
  key_findings?: string[];
  recommended_actions?: string[];
  bullet_points?: string[];
  warnings?: string[];
  sources?: AssistantSource[];
  scope?: {
    label?: string;
    role?: string;
    customer_id?: string | null;
    customer_name?: string | null;
  };
};

async function askOperationalAssistant(question: string, sender: string) {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.internalServiceToken) {
      headers["X-Eletrofrio-Service-Token"] = config.internalServiceToken;
    }
    const response = await fetch(`${config.eletrofrioApiUrl}/api/eletrofrio/assistant/whatsapp`, {
      method: "POST",
      headers,
      body: JSON.stringify({ question, origin: "whatsapp", phone: sender }),
    });

    if (!response.ok) {
      throw new Error(`Backend retornou ${response.status}: ${await response.text()}`);
    }

    return formatOperationalReply((await response.json()) as AssistantAnswer);
  } catch (error) {
    console.error("[WA] Falha ao consultar assistente operacional:", error);
    return [
      "⚠️ *Consulta operacional indisponível*",
      "",
      "Não consegui consultar os dados agora.",
      "Tente novamente em alguns instantes.",
    ].join("\n");
  }
}

export function formatOperationalReply(body: AssistantAnswer) {
  const answer = cleanParagraph(body.answer || "Não há evidência suficiente para responder com segurança.");
  const summary = capitalizeFirst(cleanParagraph(body.summary || answer).replace(/^resumo operacional:\s*/i, ""));
  const title = body.intent === "operation_summary"
    ? "📊 *Eletrofrio | Resumo operacional*"
    : `🔎 *Eletrofrio | ${cleanTitle(body.intent_label || "Consulta operacional")}*`;
  const sections: string[] = [title];

  const customerName = cleanParagraph(body.scope?.customer_name || "");
  if (customerName) {
    sections.push(`🏢 *Cliente:* ${customerName}`);
  }

  if (summary) {
    sections.push(`*Visão geral*\n${summary}`);
  }

  const highlights = uniqueItems([
    ...(body.key_findings || []),
    ...(body.bullet_points || []),
  ], 4);
  if (highlights.length) {
    sections.push(`*Pontos principais*\n${highlights.map((item) => `• ${item}`).join("\n")}`);
  }

  const actions = uniqueItems(body.recommended_actions || [], 3);
  if (actions.length) {
    sections.push(`*Próximos passos*\n${actions.map((item, index) => `${index + 1}. ${item}`).join("\n")}`);
  }

  const warnings = uniqueItems(body.warnings || [], 1);
  if (warnings.length) {
    sections.push(`⚠️ *Atenção*\n${warnings[0]}`);
  } else if (typeof body.confidence === "number" && body.confidence < 0.55) {
    sections.push("⚠️ *Evidência limitada*\nConfirme as informações no painel e valide a condição em campo.");
  }

  const sourceLabels = uniqueItems(
    (body.sources || []).map((source) => {
      const base = source.label || source.type || "Fonte operacional";
      const detail = source.tag || source.loja_nome;
      return detail ? `${base}: ${detail}` : base;
    }),
    3,
  );
  if (sourceLabels.length) {
    sections.push(`_Dados consultados: ${sourceLabels.join(" • ")}_`);
  }

  return truncateMessage(sections.join("\n\n"));
}

function cleanAnswer(value: string) {
  return value
    .replace(/\b(ol[aá][,!]?\s*)?sou (um|uma) ia\b/gi, "")
    .replace(/\bassistente inteligente\b/gi, "canal operacional")
    .trim();
}

function cleanParagraph(value: string) {
  return cleanAnswer(value).replace(/\s+/g, " ").trim();
}

function cleanTitle(value: string) {
  const cleaned = cleanParagraph(value).replace(/[\r\n*_`~]+/g, " ").trim();
  return cleaned || "Consulta operacional";
}

function capitalizeFirst(value: string) {
  return value ? `${value.charAt(0).toLocaleUpperCase("pt-BR")}${value.slice(1)}` : value;
}

function cleanListItem(value: string) {
  return cleanParagraph(value)
    .replace(/^(?:[-•*]|\d+[.)])\s*/, "")
    .trim();
}

function uniqueItems(values: string[], limit: number) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const item = cleanListItem(String(value || ""));
    const key = item.toLocaleLowerCase("pt-BR");
    if (!item || seen.has(key)) continue;
    seen.add(key);
    result.push(item);
    if (result.length >= limit) break;
  }
  return result;
}

function truncateMessage(value: string, maxLength = 1800) {
  const compact = value
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (compact.length <= maxLength) return compact;
  const suffix = "\n\n_Resposta resumida para facilitar a leitura no WhatsApp._";
  const available = maxLength - suffix.length - 3;
  const preferredCut = compact.lastIndexOf("\n", available);
  const cutAt = preferredCut > available * 0.7 ? preferredCut : available;
  return `${compact.slice(0, cutAt).trim()}...${suffix}`;
}
