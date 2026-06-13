import express from "express";
import { config } from "./config.js";
import { processPendingInsights, sendOperationalSummary } from "./insightNotifier.js";
import { sendWhatsAppMessage } from "./messageSender.js";
import { getWhatsAppQr, getWhatsAppStatus, logoutWhatsAppClient, startWhatsAppClient } from "./whatsappClient.js";

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "eletrofrio-whatsapp", ...getWhatsAppStatus() });
});

app.post("/start", async (_req, res) => {
  try {
    res.json(await startWhatsAppClient());
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : String(error) });
  }
});

app.get("/status", (_req, res) => {
  res.json(getWhatsAppStatus());
});

app.get("/qr", (_req, res) => {
  res.json(getWhatsAppQr());
});

app.post("/logout", async (_req, res) => {
  try {
    res.json(await logoutWhatsAppClient());
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : String(error) });
  }
});

app.post("/send-test", async (req, res) => {
  try {
    const phone = String(req.body?.phone || "");
    const message = String(
      req.body?.message ||
      "*Eletrofrio Refrigeração*\n✅ *Teste recebido*\n\nO canal operacional está pronto para enviar métricas e alertas inteligentes.",
    );
    res.json(await sendWhatsAppMessage(phone, message));
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : String(error) });
  }
});

app.post("/process-insights", async (_req, res) => {
  try {
    res.json(await processPendingInsights());
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : String(error) });
  }
});

app.post("/send-operational-summary", async (_req, res) => {
  try {
    res.json(await sendOperationalSummary());
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : String(error) });
  }
});

app.listen(config.port, () => {
  console.log(`[WA] Serviço WhatsApp Eletrofrio ouvindo em http://127.0.0.1:${config.port}`);
  if (config.enabled) {
    startWhatsAppClient().catch((error) => console.error("[WA] Falha ao iniciar automaticamente:", error));
  } else {
    console.log("[WA] WHATSAPP_ENABLED=false. Use /start depois de ativar a flag.");
  }
});
