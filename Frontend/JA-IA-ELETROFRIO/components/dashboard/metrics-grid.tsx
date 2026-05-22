import { MetricCard } from "@/components/dashboard/metric-card";
import type { MetricItem } from "@/lib/types";

type MetricsGridProps = {
  metrics: MetricItem[];
};

export function MetricsGrid({ metrics }: MetricsGridProps) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric) => (
        <MetricCard
          key={metric.label}
          label={metric.label}
          value={metric.value}
          helper={metric.helper}
          trend={metric.trend}
        />
      ))}
    </section>
  );
}