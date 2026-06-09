type HeaderProps = {
  title?: string;
  subtitle?: string;
  connected?: boolean;
  userLabel?: string;
  userRole?: string;
  onLogout?: () => void;
};

export function Header({
  title = "Eletrofrio",
  subtitle = "",
  connected,
  userLabel,
  userRole,
  onLogout,
}: HeaderProps) {
  return (
    <header className="glass-header sticky top-0 z-30 border-b border-white/10 px-3 py-3 text-slate-800 md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold md:text-xl">
            {title}
          </h2>
          {subtitle ? <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p> : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {userLabel ? (
            <div className="hidden rounded-md border border-white/10 bg-white/[0.72] px-3 py-1.5 text-xs font-semibold text-slate-700 sm:block">
              {userRole === "admin" ? "Admin" : userLabel}
            </div>
          ) : null}
          <div
            className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${
              connected
                ? "border-emerald-500/20 bg-emerald-50 text-emerald-700"
                : "border-amber-500/20 bg-amber-50 text-amber-700"
            }`}
          >
            {connected ? "Canal online" : "Canal pendente"}
          </div>
          {onLogout ? (
            <button
              type="button"
              onClick={onLogout}
              className="rounded-md border border-white/10 bg-white/[0.72] px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-white"
            >
              Sair
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
