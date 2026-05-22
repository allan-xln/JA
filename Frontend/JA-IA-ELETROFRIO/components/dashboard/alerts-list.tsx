import type { AlertItem } from "@/lib/types";

type AlertsListProps = {
  alerts: AlertItem[];
};

const toneClasses: Record<AlertItem["level"], string> = {
  info: "border-cyan-400/20 bg-cyan-400/10 text-cyan-200",
  warning: "border-amber-400/20 bg-amber-400/10 text-amber-200",
  critical: "border-red-400/20 bg-red-400/10 text-red-200",
};

export function AlertsList({ alerts }: AlertsListProps) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/10 backdrop-blur-xl">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.2em] text-white/45">
          Alertas recentes
        </p>
        <h3 className="mt-2 text-xl font-semibold">Ocorrências detectadas</h3>
      </div>

      <div className="space-y-3">
        {alerts.map((alert, index) => (
          <article
            key={`${alert.assetId}-${index}`}
            className={`rounded-2xl border p-4 ${toneClasses[alert.level]}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold">{alert.assetId}</p>
                <p className="mt-1 text-sm opacity-90">{alert.message}</p>
              </div>
              <span className="text-xs opacity-70">{alert.time}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}