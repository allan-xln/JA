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
    <header className="glass-header sticky top-0 z-30 border-b border-white/10 px-3 py-3 text-slate-100 md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold md:text-xl">
            {title}
          </h2>
          {subtitle ? <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p> : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {userLabel ? (
            <div className="hidden rounded-md border border-white/10 bg-white/[0.055] px-3 py-1.5 text-xs font-semibold text-slate-200 sm:block">
              {userRole === "admin" ? "Admin" : userLabel}
            </div>
          ) : null}
          <div
            className={`rounded-md border px-3 py-1.5 text-xs font-semibold ${
              connected
                ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
                : "border-amber-400/25 bg-amber-400/10 text-amber-200"
            }`}
          >
            {connected ? "Canal online" : "Canal pendente"}
          </div>
          {onLogout ? (
            <button
              type="button"
              onClick={onLogout}
              className="rounded-md border border-white/10 bg-white/[0.055] px-3 py-1.5 text-xs font-semibold text-white/75 transition hover:bg-white/[0.08]"
            >
              Sair
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
