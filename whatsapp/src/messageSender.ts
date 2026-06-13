import type { WASocket } from "@whiskeysockets/baileys";
import { config } from "./config.js";
import { logCommunication, logWhatsappMessage } from "./communicationLog.js";
import { getSocket } from "./whatsappClient.js";

function digitsOnly(value: string) {
  return value.replace(/\D/g, "");
}

export function normalizeBrazilianDigits(phone: string) {
  let digits = digitsOnly(phone);
  if (!digits) throw new Error("Número de WhatsApp vazio.");

  if ((digits.length === 10 || digits.length === 11) && !digits.startsWith(config.defaultCountryCode)) {
    digits = `${config.defaultCountryCode}${digits}`;
  }

  if (digits.length < 12 || digits.length > 14) {
    throw new Error(`Número de WhatsApp inválido: ${phone}`);
  }

  return digits;
}

export function normalizeBrazilianPhone(phone: string) {
  if (phone.includes("@s.whatsapp.net") || phone.includes("@lid")) {
    const [recipient, domain] = phone.trim().split("@", 2);
    const cleanRecipient = recipient.split(":", 1)[0];
    return `${cleanRecipient}@${domain}`;
  }
  const digits = normalizeBrazilianDigits(phone);
  return `${digits}@s.whatsapp.net`;
}

function unique(values: string[]) {
  return [...new Set(values)];
}

function nationalBrazilianDigits(phone: string) {
  let digits = digitsOnly(phone);
  if (digits.startsWith(config.defaultCountryCode) && (digits.length === 12 || digits.length === 13)) {
    digits = digits.slice(config.defaultCountryCode.length);
  }
  return digits;
}

export function brazilianPhoneCandidates(phone: string) {
  if (phone.includes("@s.whatsapp.net") || phone.includes("@lid")) {
    return [normalizeBrazilianPhone(phone)];
  }

  const nationalDigits = nationalBrazilianDigits(phone);
  const candidates = [normalizeBrazilianPhone(phone)];

  if (nationalDigits.length === 11 && nationalDigits[2] === "9") {
    candidates.push(`${config.defaultCountryCode}${nationalDigits.slice(0, 2)}${nationalDigits.slice(3)}@s.whatsapp.net`);
  }

  if (nationalDigits.length === 10) {
    candidates.push(`${config.defaultCountryCode}${nationalDigits.slice(0, 2)}9${nationalDigits.slice(2)}@s.whatsapp.net`);
  }

  return unique(candidates);
}

function recipientAllowed(phone: string) {
  if (!config.allowedRecipients.length) return true;

  const candidateJids = brazilianPhoneCandidates(phone);
  const candidateDigits = candidateJids.map((candidate) => candidate.split("@", 1)[0]);

  return config.allowedRecipients.some((recipient) => {
    try {
      const allowedJids = brazilianPhoneCandidates(recipient);
      const allowedDigits = allowedJids.map((allowedJid) => allowedJid.split("@", 1)[0]);

      return (
        allowedJids.some((allowedJid) => candidateJids.includes(allowedJid)) ||
        allowedDigits.some((allowedDigit) => candidateDigits.includes(allowedDigit))
      );
    } catch {
      return false;
    }
  });
}

async function resolveRecipientJid(sock: WASocket, phone: string) {
  const candidateJids = brazilianPhoneCandidates(phone);

  try {
    const matches = (await sock.onWhatsApp(...candidateJids)) ?? [];
    const resolved = matches.find((match) => match.exists && match.jid);

    if (resolved?.jid) {
      if (resolved.jid !== candidateJids[0]) {
        console.log(`[WA] Destinatário resolvido: ${phone} -> ${resolved.jid} (candidatos: ${candidateJids.join(", ")})`);
      }
      return resolved.jid;
    }

    console.warn(`[WA] Nenhum candidato confirmado para ${phone}; tentando ${candidateJids[0]}.`);
  } catch (error) {
    console.warn(`[WA] Falha ao validar destinatário ${phone}; tentando ${candidateJids[0]}.`, error);
  }

  return candidateJids[0];
}

function formatOutgoingMessage(message: string) {
  const text = message.trim();
  if (!text) return "";
  if (text.includes("eletrofrio.147.15.56.49.nip.io")) return text;

  const url = config.appPublicUrl.includes("eletrofrio.147.15.56.49.nip.io")
    ? config.appPublicUrl
    : "https://eletrofrio.147.15.56.49.nip.io";

  return [
    text,
    "",
    "🔎 *Acesse o portal para acompanhar:*",
    `${url.replace(/\/+$/, "")}/`,
  ].join("\n");
}

export async function sendWhatsAppMessage(phone: string, message: string) {
  const fallbackJid = normalizeBrazilianPhone(phone);
  const text = formatOutgoingMessage(message);
  if (!text) throw new Error("Mensagem vazia.");

  if (!recipientAllowed(phone)) {
    await logWhatsappMessage({
      phone: fallbackJid,
      direction: "outgoing",
      type: "manual_message",
      message: text,
      dry_run: config.dryRun,
      delivery_status: "failed",
    });
    throw new Error("Destinatário não permitido em WHATSAPP_ALLOWED_RECIPIENTS.");
  }

  if (config.dryRun || !config.enabled) {
    console.log(`[WA][DRY-RUN] Para ${fallbackJid}: ${text}`);
    await logWhatsappMessage({
      phone: fallbackJid,
      direction: "outgoing",
      type: "manual_message",
      message: text,
      dry_run: true,
      delivery_status: "dry-run",
    });
    await logCommunication({
      type: "manual_message",
      direction: "outgoing",
      phone: fallbackJid,
      message: text,
      status: "dry-run",
      source: "WhatsApp",
    });
    return { sent: false, dryRun: true, jid: fallbackJid };
  }

  const sock = getSocket();
  if (!sock) throw new Error("WhatsApp não conectado.");

  const jid = await resolveRecipientJid(sock, phone);
  await sock.sendMessage(jid, { text });
  console.log(`[WA] Mensagem enviada para ${jid}`);
  await logWhatsappMessage({
    phone: jid,
    direction: "outgoing",
    type: "manual_message",
    message: text,
    dry_run: false,
    delivery_status: "sent",
  });
  await logCommunication({
    type: "manual_message",
    direction: "outgoing",
    phone: jid,
    message: text,
    status: "sent",
    source: "WhatsApp",
  });
  return { sent: true, dryRun: false, jid };
}
