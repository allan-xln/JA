type HeaderProps = {
  title?: string;
  subtitle?: string;
  connected?: boolean;
};

export function Header({
  title = "Eletrofrio",
  subtitle = "",
  connected,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/10 bg-[#0b1118]/95 px-3 py-3 text-slate-100 md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold md:text-xl">
            {title}
          </h2>
          {subtitle ? <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p> : null}
        </div>

        <div className="shrink-0">
          <div
            className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${
              connected
                ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
                : "border-amber-400/25 bg-amber-400/10 text-amber-200"
            }`}
          >
            {connected ? "Canal online" : "Canal pendente"}
          </div>
        </div>
      </div>
    </header>
  );
}
