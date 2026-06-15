import "dotenv/config";
import path from "node:path";

const rootEnvPath = path.resolve(process.cwd(), "..", ".env");
await import("dotenv").then(({ config }) => config({ path: rootEnvPath, override: false }));

function boolEnv(name: string, fallback = false) {
  const value = process.env[name];
  if (value == null) return fallback;
  return ["1", "true", "yes", "y", "on"].includes(value.trim().toLowerCase());
}

function numberEnv(name: string, fallback: number) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

export const config = {
  port: numberEnv("WHATSAPP_PORT", numberEnv("WHATSAPP_SERVICE_PORT", 8091)),
  enabled: boolEnv("WHATSAPP_ENABLED", false),
  dryRun: boolEnv("WHATSAPP_DRY_RUN", true),
  sessionDir: process.env.WHATSAPP_SESSION_DIR || "./whatsapp/sessions/eletrofrio",
  defaultCountryCode: process.env.WHATSAPP_DEFAULT_COUNTRY_CODE || "55",
  allowedRecipients: (process.env.WHATSAPP_ALLOWED_RECIPIENTS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean),
  minIntervalMinutesPerDevice: numberEnv("WHATSAPP_MIN_INTERVAL_MINUTES_PER_DEVICE", 30),
  minIntervalMinutesPerStore: numberEnv("WHATSAPP_MIN_INTERVAL_MINUTES_PER_STORE", 60),
  eletrofrioApiUrl: (process.env.ELETROFRIO_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, ""),
  internalServiceToken: process.env.ELETROFRIO_INTERNAL_SERVICE_TOKEN || process.env.SUPABASE_SERVICE_ROLE_KEY || "",
  appPublicUrl: (process.env.APP_PUBLIC_URL || "https://eletrofrio.147.15.56.49.nip.io").replace(/\/+$/, ""),
  supabaseUrl: (process.env.SUPABASE_URL || "").replace(/\/+$/, ""),
  supabaseServiceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY || "",
};

export function requireSupabaseConfig() {
  if (!config.supabaseUrl || !config.supabaseServiceRoleKey) {
    throw new Error("Supabase não configurado para o WhatsApp. Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.");
  }
}
