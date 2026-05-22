import type { AssetRow } from "@/lib/types";

type AssetsTableProps = {
  assets: AssetRow[];
};

const statusClasses: Record<AssetRow["status"], string> = {
  normal: "bg-emerald-400/15 text-emerald-300",
  warning: "bg-amber-400/15 text-amber-300",
  critical: "bg-red-400/15 text-red-300",
};

export function AssetsTable({ assets }: AssetsTableProps) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/10 backdrop-blur-xl">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.2em] text-white/45">
          Ativos monitorados
        </p>
        <h3 className="mt-2 text-xl font-semibold">Status atual dos equipamentos</h3>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-y-2">
          <thead>
            <tr className="text-left text-sm text-white/45">
              <th className="px-3 py-2">Ativo</th>
              <th className="px-3 py-2">Setor</th>
              <th className="px-3 py-2">Temperatura</th>
              <th className="px-3 py-2">Corrente</th>
              <th className="px-3 py-2">Pressão</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => (
              <tr key={asset.assetId} className="rounded-2xl bg-white/[0.04] text-sm">
                <td className="rounded-l-2xl px-3 py-4 font-medium text-white">
                  {asset.assetId}
                </td>
                <td className="px-3 py-4 text-white/70">{asset.sector}</td>
                <td className="px-3 py-4 text-white/70">{asset.temperature}</td>
                <td className="px-3 py-4 text-white/70">{asset.current}</td>
                <td className="px-3 py-4 text-white/70">{asset.pressure}</td>
                <td className="rounded-r-2xl px-3 py-4">
                  <span
                    className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusClasses[asset.status]}`}
                  >
                    {asset.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}