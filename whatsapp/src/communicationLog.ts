import { insertRows } from "./supabase.js";

function preview(value: string, limit = 220) {
  const compact = value.replace(/\s+/g, " ").trim();
  return compact.length <= limit ? compact : `${compact.slice(0, limit - 3).trim()}...`;
}

async function safeInsert(table: string, payload: Record<string, unknown>) {
  try {
    await insertRows(table, payload);
  } catch (error) {
    console.warn(`[WA] Comunicação não registrada em ${table}:`, error instanceof Error ? error.message : error);
  }
}

export async function logCommunication(payload: {
  type: string;
  direction?: string;
  phone?: string | null;
  loja_id?: number | null;
  loja_nome?: string | null;
  dispositivo_id?: number | null;
  tag?: string | null;
  message?: string;
  status?: string;
  source?: string;
  payload_json?: Record<string, unknown>;
}) {
  await safeInsert("eletrofrio_communication_logs", {
    type: payload.type,
    direction: payload.direction || "system",
    phone: payload.phone || null,
    loja_id: payload.loja_id ?? null,
    loja_nome: payload.loja_nome || null,
    dispositivo_id: payload.dispositivo_id ?? null,
    tag: payload.tag || null,
    message_preview: preview(payload.message || ""),
    payload_json: payload.payload_json || {},
    status: payload.status || "received",
    source: payload.source || "WhatsApp",
    created_at: new Date().toISOString(),
  });
}

export async function logWhatsappMessage(payload: {
  phone?: string | null;
  direction: "incoming" | "outgoing" | "system";
  type: string;
  message: string;
  dry_run?: boolean;
  delivery_status?: string;
}) {
  await safeInsert("eletrofrio_whatsapp_messages", {
    phone: payload.phone || null,
    direction: payload.direction,
    type: payload.type,
    message_preview: preview(payload.message),
    message_full: payload.message,
    dry_run: Boolean(payload.dry_run),
    delivery_status: payload.delivery_status || "received",
    created_at: new Date().toISOString(),
  });
}
