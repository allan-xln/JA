"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartPoint } from "@/lib/types";

type TemperatureChartProps = {
  data: ChartPoint[];
};

export function TemperatureChart({ data }: TemperatureChartProps) {
  const hasData = data.length > 0;

  return (
    <section className="rounded-3xl border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/10 backdrop-blur-xl">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-white/45">
            Tendência térmica
          </p>
          <h3 className="mt-2 text-xl font-semibold">
            Temperatura dos equipamentos
          </h3>
        </div>

        <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-200">
          Atualização contínua
        </div>
      </div>

      {!hasData ? (
        <div className="flex min-h-[320px] items-center justify-center rounded-3xl border border-dashed border-white/10 bg-black/10 text-sm text-white/50">
          Nenhum dado de temperatura disponível no momento.
        </div>
      ) : (
        <div className="h-[320px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 10, right: 12, left: -12, bottom: 0 }}
            >
              <CartesianGrid
                stroke="rgba(255,255,255,0.08)"
                strokeDasharray="3 3"
              />

              <XAxis
                dataKey="time"
                stroke="rgba(255,255,255,0.45)"
                tick={{ fill: "rgba(255,255,255,0.55)", fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
              />

              <YAxis
                stroke="rgba(255,255,255,0.45)"
                tick={{ fill: "rgba(255,255,255,0.55)", fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                domain={["auto", "auto"]}
                tickFormatter={(value) => `${value}°`}
              />

              <Tooltip
                contentStyle={{
                  background: "rgba(8, 17, 31, 0.95)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 16,
                  color: "#f8fafc",
                  backdropFilter: "blur(10px)",
                }}
                labelStyle={{ color: "rgba(255,255,255,0.7)" }}
                formatter={(value, name) => {
                  const numericValue =
                    typeof value === "number" ? value : Number(value ?? 0);
                  if (name === "temperature") return [`${numericValue} °C`, "Temperatura"];
                  if (name === "limit") return [`${numericValue} °C`, "Limite"];
                  return [String(value), name];
                }}
              />

              <ReferenceLine
                y={
                  data.length > 0
                    ? Number(
                        (
                          data.reduce((acc, item) => acc + item.limit, 0) / data.length
                        ).toFixed(1)
                      )
                    : 0
                }
                stroke="rgba(248,113,113,0.7)"
                strokeDasharray="6 6"
              />

              <Line
                type="monotone"
                dataKey="limit"
                stroke="rgba(248,113,113,0.85)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />

              <Line
                type="monotone"
                dataKey="temperature"
                stroke="rgba(34,197,94,0.95)"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
