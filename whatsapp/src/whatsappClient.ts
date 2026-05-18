import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
  type WASocket,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import QRCode from "qrcode";
import * as qrcode from "qrcode-terminal";
import { logCommunication } from "./communicationLog.js";
import { config } from "./config.js";
import { ensureSessionDir, resetSessionDir } from "./sessionManager.js";
import { handleIncomingMessage } from "./messageHandler.js";

type ConnectionState = "disabled" | "idle" | "connecting" | "open" | "close";
type TerminalQrModule = {
  generate: (input: string, options?: { small?: boolean }) => void;
};

const terminalQr = (
  "generate" in qrcode
    ? qrcode
    : (qrcode as unknown as { default: TerminalQrModule }).default
) as TerminalQrModule;

let socket: WASocket | null = null;
let connectionStatus: ConnectionState = config.enabled ? "idle" : "disabled";
let lastQr: string | null = null;
let lastQrDataUrl: string | null = null;
let lastQrAt: string | null = null;
let lastConnectionAt: string | null = null;
let lastDisconnectReason: string | null = null;
let connectedPhone: string | null = null;
let reconnectTimer: NodeJS.Timeout | null = null;
let lastLoggedConnectionStatus: string | null = null;

export function getSocket() {
  return socket;
}

export function getConnectedPhone() {
  return connectedPhone;
}

export function getWhatsAppStatus() {
  return {
    enabled: config.enabled,
    dryRun: config.dryRun,
    status: connectionStatus,
    connected: connectionStatus === "open",
    hasQr: Boolean(lastQr),
    lastQrAt,
    lastConnectionAt,
    lastDisconnectReason,
    phone: connectedPhone,
    sessionDir: config.sessionDir,
    allowedRecipients: config.allowedRecipients.length,
  };
}

export function getWhatsAppQr() {
  return {
    hasQr: Boolean(lastQr),
    qr: lastQr,
    dataUrl: lastQrDataUrl,
    lastQrAt,
    connected: connectionStatus === "open",
  };
}

function clearQr() {
  lastQr = null;
  lastQrDataUrl = null;
  lastQrAt = null;
}

function scheduleReconnect() {
  if (!config.enabled || reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    startWhatsAppClient().catch((error) => {
      console.error("[WA] Falha ao reconectar:", error);
      scheduleReconnect();
    });
  }, 5000);
}

function logConnectionEventOnce(status: string, payload: Parameters<typeof logCommunication>[0]) {
  if (lastLoggedConnectionStatus === status) return;
  lastLoggedConnectionStatus = status;
  void logCommunication(payload);
}

async function storeQr(qr: string) {
  lastQr = qr;
  lastQrAt = new Date().toISOString();
  try {
    lastQrDataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
  } catch (error) {
    lastQrDataUrl = null;
    console.warn("[WA] Falha ao gerar QR Code dataURL:", error);
  }

  console.log("[WA] Escaneie o QR Code abaixo para conectar o WhatsApp da Eletrofrio:");
  terminalQr.generate(qr, { small: true });
  await logCommunication({
    type: "system_event",
    direction: "system",
    message: "QR Code gerado para conexão do canal operacional.",
    status: "qr_generated",
    source: "WhatsApp",
    payload_json: { lastQrAt },
  });
}

export async function startWhatsAppClient() {
  if (!config.enabled) {
    connectionStatus = "disabled";
    console.log("[WA] WhatsApp desativado por WHATSAPP_ENABLED=false.");
    return getWhatsAppStatus();
  }

  if (socket && connectionStatus === "open") return getWhatsAppStatus();
  if (socket && connectionStatus === "connecting") return getWhatsAppStatus();

  connectionStatus = "connecting";
  const sessionDir = ensureSessionDir();
  const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
  const { version } = await fetchLatestBaileysVersion();

  socket = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    browser: ["Eletrofrio-IA", "Desktop", "1.0.0"],
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false,
    markOnlineOnConnect: false,
  });

  socket.ev.on("creds.update", saveCreds);

  socket.ev.on("messages.upsert", async ({ messages }) => {
    for (const message of messages) {
      try {
        if (socket) await handleIncomingMessage(socket, message);
      } catch (error) {
        console.error("[WA] Falha ao processar mensagem recebida:", error);
      }
    }
  });

  socket.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      void storeQr(qr);
    }

    if (connection === "open") {
      connectionStatus = "open";
      lastConnectionAt = new Date().toISOString();
      lastDisconnectReason = null;
      connectedPhone = socket?.user?.id || socket?.user?.name || null;
      clearQr();
      console.log("[WA] WhatsApp Eletrofrio conectado.");
      logConnectionEventOnce("connected", {
        type: "system_event",
        direction: "system",
        phone: connectedPhone,
        message: "Canal operacional conectado.",
        status: "connected",
        source: "WhatsApp",
        payload_json: { lastConnectionAt },
      });
    }

    if (connection === "close") {
      connectionStatus = "close";
      const statusCode = (lastDisconnect?.error as Boom | undefined)?.output?.statusCode;
      lastDisconnectReason = String(statusCode || lastDisconnect?.error?.message || "desconectado");
      socket = null;
      connectedPhone = null;
      console.warn("[WA] WhatsApp desconectado:", lastDisconnectReason);
      logConnectionEventOnce(`disconnected:${lastDisconnectReason}`, {
        type: "system_event",
        direction: "system",
        message: "Canal operacional desconectado.",
        status: "disconnected",
        source: "WhatsApp",
        payload_json: { lastDisconnectReason },
      });

      if (statusCode !== DisconnectReason.loggedOut) {
        scheduleReconnect();
      }
    }
  });

  return getWhatsAppStatus();
}

export async function logoutWhatsAppClient() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  try {
    if (socket) {
      await socket.logout();
      socket.end(undefined);
    }
  } catch (error) {
    console.warn("[WA] Logout Baileys retornou aviso:", error);
  }

  socket = null;
  connectedPhone = null;
  clearQr();
  resetSessionDir();
  connectionStatus = config.enabled ? "idle" : "disabled";
  lastDisconnectReason = "logout";
  return getWhatsAppStatus();
}
