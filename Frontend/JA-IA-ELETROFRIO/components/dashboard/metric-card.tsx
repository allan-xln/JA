type MetricCardProps = {
  label: string;
  value: string;
  helper: string;
  trend: "up" | "down" | "neutral";
};

export function MetricCard({
  label,
  value,
  helper,
  trend,
}: MetricCardProps) {
  const trendClasses = {
    up: "text-emerald-300",
    down: "text-red-300",
    neutral: "text-cyan-300",
  };

  return (
    <article className="rounded-3xl border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/10 backdrop-blur-xl">
      <p className="text-sm text-white/55">{label}</p>
      <h3 className="mt-3 text-3xl font-bold tracking-tight">{value}</h3>
      <p className={`mt-3 text-sm ${trendClasses[trend]}`}>{helper}</p>
    </article>
  );
}