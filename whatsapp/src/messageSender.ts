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

function recipientAllowed(phone: string) {
  if (!config.allowedRecipients.length) return true;

  const jid = normalizeBrazilianPhone(phone);
  const digits = jid.split("@", 1)[0];
  return config.allowedRecipients.some((recipient) => {
    try {
      const allowedJid = normalizeBrazilianPhone(recipient);
      return allowedJid === jid || allowedJid.split("@", 1)[0] === digits;
    } catch {
      return false;
    }
  });
}

export async function sendWhatsAppMessage(phone: string, message: string) {
  const jid = normalizeBrazilianPhone(phone);
  const text = message.trim();
  if (!text) throw new Error("Mensagem vazia.");

  if (!recipientAllowed(phone)) {
    await logWhatsappMessage({
      phone: jid,
      direction: "outgoing",
      type: "manual_message",
      message: text,
      dry_run: config.dryRun,
      delivery_status: "failed",
    });
    throw new Error("Destinatário não permitido em WHATSAPP_ALLOWED_RECIPIENTS.");
  }

  if (config.dryRun || !config.enabled) {
    console.log(`[WA][DRY-RUN] Para ${jid}: ${text}`);
    await logWhatsappMessage({
      phone: jid,
      direction: "outgoing",
      type: "manual_message",
      message: text,
      dry_run: true,
      delivery_status: "dry-run",
    });
    await logCommunication({
      type: "manual_message",
      direction: "outgoing",
      phone: jid,
      message: text,
      status: "dry-run",
      source: "WhatsApp",
    });
    return { sent: false, dryRun: true, jid };
  }

  const sock = getSocket();
  if (!sock) throw new Error("WhatsApp não conectado.");

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
