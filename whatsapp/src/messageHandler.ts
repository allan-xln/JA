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

function isOperationalQuestion(text: string) {
  return [
    /\b(status|alertas?|resumo|lojas?|sensores?|equipamentos?|anomalias?|offline|temperatura|critico|crítico|critica|crítica|falhas?|problemas?|camara|câmara|compressor|rack|degelo|press[aã]o|glicol)\b/,
    /alta\s+temperatura/,
    /baixa\s+temperatura/,
    /\bqual\s+(sensor|equipamento|loja)\b/,
    /como\s+est[aá]/,
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
  confidence?: number;
  warnings?: string[];
  sources?: AssistantSource[];
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
    return "Não consegui consultar os dados operacionais agora. Tente novamente em alguns instantes.";
  }
}

function formatOperationalReply(body: AssistantAnswer) {
  const answer = cleanAnswer(body.answer || "Não há evidência suficiente para responder com segurança.");
  const details: string[] = ["Consulta operacional"];

  if (typeof body.confidence === "number" && body.confidence < 0.55) {
    details.push(`Evidência limitada (${Math.round(body.confidence * 100)}%).`);
  }

  if (Array.isArray(body.warnings) && body.warnings.length) {
    details.push(`Atenção: ${body.warnings.slice(0, 1).join(" ")}`);
  }

  if (Array.isArray(body.sources) && body.sources.length) {
    const sourceLabels = body.sources
      .slice(0, 3)
      .map((source) => {
        const base = source.label || source.type;
        const detail = source.tag || source.loja_nome;
        return detail ? `${base}: ${detail}` : base;
      })
      .filter(Boolean);
    if (sourceLabels.length) {
      details.push(`Evidências: ${sourceLabels.join("; ")}.`);
    }
  }

  return truncateMessage([details[0], "", answer, ...details.slice(1)].join("\n"));
}

function cleanAnswer(value: string) {
  return value
    .replace(/\b(ol[aá][,!]?\s*)?sou (um|uma) ia\b/gi, "")
    .replace(/\bassistente inteligente\b/gi, "canal operacional")
    .trim();
}

function truncateMessage(value: string, maxLength = 900) {
  const compact = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");

  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 42).trim()}...\nResumo reduzido para o canal operacional.`;
}
