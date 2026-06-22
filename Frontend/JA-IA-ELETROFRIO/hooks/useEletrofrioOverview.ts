"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { eletrofrioApi } from "@/services/eletrofrioApi";
import type {
  EletrofrioAlarm,
  EletrofrioDevice,
  EletrofrioOverview,
  EletrofrioTelemetry,
  EletrofrioUnit,
} from "@/types/eletrofrio";

type OverviewState = {
  health: Awaited<ReturnType<typeof eletrofrioApi.health>> | null;
  overview: EletrofrioOverview | null;
  units: EletrofrioUnit[];
  devices: EletrofrioDevice[];
  alarms: EletrofrioAlarm[];
  telemetry: EletrofrioTelemetry[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

export function useEletrofrioOverview(enabled = true, loadDetails = false): OverviewState {
  const [health, setHealth] = useState<OverviewState["health"]>(null);
  const [overview, setOverview] = useState<EletrofrioOverview | null>(null);
  const [units, setUnits] = useState<EletrofrioUnit[]>([]);
  const [devices, setDevices] = useState<EletrofrioDevice[]>([]);
  const [alarms, setAlarms] = useState<EletrofrioAlarm[]>([]);
  const [telemetry, setTelemetry] = useState<EletrofrioTelemetry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    const [healthResult, overviewResult] = await Promise.allSettled([
      eletrofrioApi.health(),
      eletrofrioApi.overview(),
    ]);

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    }

    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
    } else {
      setError(overviewResult.reason instanceof Error ? overviewResult.reason.message : "Falha ao carregar dados reais.");
      setLoading(false);
      return;
    }

    if (!loadDetails) {
      setLoading(false);
      return;
    }

    const [unitsResult, devicesResult, alarmsResult, telemetryResult] = await Promise.allSettled([
      eletrofrioApi.units(),
      eletrofrioApi.devices(),
      eletrofrioApi.alarms(80),
      eletrofrioApi.telemetry(80),
    ]);

    if (unitsResult.status === "fulfilled") setUnits(unitsResult.value.items || []);
    if (devicesResult.status === "fulfilled") setDevices(devicesResult.value.items || []);
    if (alarmsResult.status === "fulfilled") setAlarms(alarmsResult.value.items || []);
    if (telemetryResult.status === "fulfilled") setTelemetry(telemetryResult.value.items || []);

    const failedDetail = [unitsResult, devicesResult, alarmsResult, telemetryResult].find(
      (result) => result.status === "rejected",
    );
    if (failedDetail?.status === "rejected") {
      setError(failedDetail.reason instanceof Error ? failedDetail.reason.message : "Falha ao carregar parte dos dados reais.");
    }

    setLoading(false);
  }, [enabled, loadDetails]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

  return useMemo(
    () => ({ health, overview, units, devices, alarms, telemetry, loading, error, refresh }),
    [health, overview, units, devices, alarms, telemetry, loading, error, refresh]
  );
}
