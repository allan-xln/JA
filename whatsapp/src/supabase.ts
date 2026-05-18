import { config, requireSupabaseConfig } from "./config.js";

type QueryValue = string | number | boolean;

function headers(extra: Record<string, string> = {}) {
  requireSupabaseConfig();
  return {
    apikey: config.supabaseServiceRoleKey,
    Authorization: `Bearer ${config.supabaseServiceRoleKey}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

function tableUrl(table: string, params?: Record<string, QueryValue>) {
  const url = new URL(`${config.supabaseUrl}/rest/v1/${table}`);
  Object.entries(params || {}).forEach(([key, value]) => url.searchParams.set(key, String(value)));
  return url.toString();
}

export async function selectRows<T>(table: string, params: Record<string, QueryValue> = {}): Promise<T[]> {
  const response = await fetch(tableUrl(table, params), { headers: headers() });
  if (!response.ok) throw new Error(`Supabase select ${table} falhou: ${response.status} ${await response.text()}`);
  return (await response.json()) as T[];
}

export async function patchRows<T>(
  table: string,
  filters: Record<string, QueryValue>,
  data: Record<string, unknown>
): Promise<T[]> {
  const params = Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, `eq.${value}`]));
  const response = await fetch(tableUrl(table, params), {
    method: "PATCH",
    headers: headers({ Prefer: "return=representation" }),
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Supabase patch ${table} falhou: ${response.status} ${await response.text()}`);
  return (await response.json()) as T[];
}

export async function insertRows<T>(
  table: string,
  rows: Record<string, unknown> | Array<Record<string, unknown>>
): Promise<T[]> {
  const payload = Array.isArray(rows) ? rows : [rows];
  if (!payload.length) return [];
  const response = await fetch(tableUrl(table), {
    method: "POST",
    headers: headers({ Prefer: "return=representation" }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Supabase insert ${table} falhou: ${response.status} ${await response.text()}`);
  return (await response.json()) as T[];
}
