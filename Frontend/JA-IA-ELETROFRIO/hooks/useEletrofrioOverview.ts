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
    try {
      setError(null);
      const [healthData, overviewData] = await Promise.all([
        eletrofrioApi.health(),
        eletrofrioApi.overview(),
      ]);

      setHealth(healthData);
      setOverview(overviewData);
      setLoading(false);

      if (!loadDetails) return;

      const [unitsData, devicesData, alarmsData, telemetryData] = await Promise.all([
        eletrofrioApi.units(),
        eletrofrioApi.devices(),
        eletrofrioApi.alarms(80),
        eletrofrioApi.telemetry(80),
      ]);

      setUnits(unitsData.items || []);
      setDevices(devicesData.items || []);
      setAlarms(alarmsData.items || []);
      setTelemetry(telemetryData.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar dados reais.");
    } finally {
      setLoading(false);
    }
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
