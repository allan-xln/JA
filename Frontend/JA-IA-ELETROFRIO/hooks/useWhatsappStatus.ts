"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { eletrofrioApi } from "@/services/eletrofrioApi";
import type { WhatsappQr, WhatsappStatus } from "@/types/eletrofrio";

function friendlyWhatsappError(err: unknown) {
  const message =
    err instanceof Error ? err.message : "Falha ao consultar WhatsApp.";

  if (
    message.includes("Serviço WhatsApp indisponível") ||
    message.includes("Connection refused") ||
    message.includes("Failed to establish a new connection") ||
    message.includes("Max retries exceeded")
  ) {
    return "Canal WhatsApp offline. Inicie o serviço local do WhatsApp para gerar o QR Code e ativar notificações.";
  }

  return message;
}

export function useWhatsappStatus(autoRefreshMs = 10000, enabled = true) {
  const [status, setStatus] = useState<WhatsappStatus | null>(null);
  const [qr, setQr] = useState<WhatsappQr | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setError(null);
    const [statusResult, qrResult] = await Promise.allSettled([
      eletrofrioApi.whatsappStatus(),
      eletrofrioApi.whatsappQr(),
    ]);

    if (statusResult.status === "fulfilled") {
      setStatus(statusResult.value);
    }

    if (qrResult.status === "fulfilled") {
      setQr(qrResult.value);
    }

    const hasUsableQr =
      qrResult.status === "fulfilled" &&
      Boolean(qrResult.value.dataUrl || qrResult.value.qr);

    if (statusResult.status === "rejected" && qrResult.status === "rejected") {
      setError(friendlyWhatsappError(statusResult.reason));
    } else if (statusResult.status === "rejected" && !hasUsableQr) {
      setError(friendlyWhatsappError(statusResult.reason));
    } else {
      setError(null);
    }

    setLoading(false);
  }, [enabled]);

  const refreshQr = useCallback(async () => {
    try {
      setBusy(true);
      setConnecting(true);
      setError(null);
      await eletrofrioApi.whatsappStart();
      for (let attempt = 0; attempt < 12; attempt += 1) {
        await refresh();
        const [statusResult, qrResult] = await Promise.allSettled([
          eletrofrioApi.whatsappStatus(),
          eletrofrioApi.whatsappQr(),
        ]);
        if (statusResult.status === "fulfilled") setStatus(statusResult.value);
        if (qrResult.status === "fulfilled") setQr(qrResult.value);
        const connected = statusResult.status === "fulfilled" && statusResult.value.connected;
        const hasQr = qrResult.status === "fulfilled" && Boolean(qrResult.value.dataUrl || qrResult.value.qr);
        if (connected || hasQr) break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    } catch (err) {
      setError(friendlyWhatsappError(err));
    } finally {
      setConnecting(false);
      setBusy(false);
    }
  }, [refresh]);

  const runAction = useCallback(
    async <T,>(action: () => Promise<T>, success: string | ((result: T) => string)) => {
      try {
        setBusy(true);
        setError(null);
        setMessage(null);
        const result = await action();
        setMessage(typeof success === "function" ? success(result) : success);
        await refresh();
      } catch (err) {
        setError(friendlyWhatsappError(err));
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

  useEffect(() => {
    if (!enabled || !autoRefreshMs) return;
    const interval = setInterval(() => {
      void refresh();
    }, autoRefreshMs);
    return () => clearInterval(interval);
  }, [autoRefreshMs, enabled, refresh]);

  return useMemo(
    () => ({ status, qr, loading, busy, connecting, message, error, refresh, refreshQr, runAction }),
    [status, qr, loading, busy, connecting, message, error, refresh, refreshQr, runAction]
  );
}
