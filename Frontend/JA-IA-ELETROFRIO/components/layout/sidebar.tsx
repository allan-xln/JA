import {
  AlertTriangle,
  BellRing,
  ClipboardList,
  LayoutDashboard,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  SlidersHorizontal,
  Snowflake,
} from "lucide-react";

const items = [
  { id: "dashboard", label: "Visão geral", icon: LayoutDashboard },
  { id: "ativos", label: "Ativos", icon: Snowflake },
  { id: "alertas", label: "Ocorrências", icon: AlertTriangle },
  { id: "inteligentes", label: "Alertas inteligentes", icon: BellRing },
  { id: "operacao", label: "Operação", icon: ClipboardList },
  { id: "regras", label: "Regras", icon: SlidersHorizontal },
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle },
] as const;

export type ViewId = (typeof items)[number]["id"];

type SidebarProps = {
  activeView: ViewId;
  onViewChange: (view: ViewId) => void;
  role?: string;
  totals?: {
    units?: number;
    devices?: number;
    alarms?: number;
  };
  collapsed?: boolean;
  onToggle?: () => void;
};

export function Sidebar({ activeView, onViewChange, role = "admin", totals, collapsed = false, onToggle }: SidebarProps) {
  void totals;
  const visibleItems = role === "admin" ? items : items.filter((item) => item.id !== "operacao");
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      data-collapsed={collapsed ? "true" : "false"}
      className={`app-sidebar fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-white/95 text-slate-700 shadow-xl backdrop-blur-xl lg:static lg:inset-auto lg:z-auto lg:flex-col lg:border-r lg:border-t-0 ${
        collapsed ? "lg:w-[76px]" : "lg:w-[260px]"
      }`}
    >
      <div className="hidden border-b border-white/10 p-3 lg:block">
        <div className={`sidebar-brand-row flex items-center ${collapsed ? "flex-col gap-2" : "justify-between gap-2"}`}>
          <div className={collapsed ? "sidebar-logo flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-sky-100 bg-white p-1.5 shadow-sm" : "sidebar-logo flex min-w-0 flex-1 items-center rounded-lg bg-white px-3 py-2 shadow-sm"}>
            {collapsed ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src="/eletrofrio-mini.png"
                alt="Eletrofrio"
                className="h-9 w-9 shrink-0 object-contain"
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src="/eletrofrio-logo.png"
                alt="Eletrofrio Refrigeração"
                className="h-11 w-full max-w-[176px] object-contain"
              />
            )}
          </div>
          {onToggle ? (
            <button
              type="button"
              onClick={onToggle}
              title={collapsed ? "Abrir menu" : "Recolher menu"}
              aria-label={collapsed ? "Abrir menu" : "Recolher menu"}
              className={`sidebar-toggle hidden shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.6] text-slate-600 transition hover:bg-white lg:inline-flex ${
                collapsed ? "h-9 w-9" : "h-10 w-10"
              }`}
            >
              <ToggleIcon className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      <nav className={`grid w-full grid-cols-7 gap-1 overflow-x-auto p-2 lg:flex lg:w-auto lg:flex-col lg:gap-2 lg:overflow-visible ${collapsed ? "lg:items-center" : "lg:items-stretch"}`}>
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = activeView === item.id;

          return (
            <button
              key={item.label}
              type="button"
              onClick={() => onViewChange(item.id)}
              title={item.label}
              aria-label={item.label}
              aria-current={active ? "page" : undefined}
              className={`sidebar-nav-item group relative flex h-12 min-w-0 items-center gap-3 overflow-hidden rounded-lg border px-3 text-center text-sm font-semibold ${
                collapsed ? "justify-center lg:w-12" : "justify-center lg:justify-start"
              } ${
                active
                  ? "border-sky-300/45 bg-sky-50 text-sky-800 shadow-sm"
                  : "border-transparent text-slate-500 hover:border-white/10 hover:bg-white/[0.72] hover:text-slate-900"
              }`}
            >
              {active ? <span className="sidebar-active-rail" aria-hidden="true" /> : null}
              <Icon className={`relative z-10 h-5 w-5 shrink-0 transition-transform duration-200 ${active ? "scale-105" : "group-hover:scale-105"}`} />
              <span
                className={`relative z-10 hidden min-w-0 overflow-hidden whitespace-nowrap text-left transition-all duration-200 lg:block ${
                  collapsed ? "lg:max-w-0 lg:translate-x-1 lg:opacity-0" : "lg:max-w-[170px] lg:translate-x-0 lg:opacity-100"
                }`}
              >
                {item.label}
              </span>
              <span className="sidebar-tooltip pointer-events-none absolute left-[calc(100%+10px)] top-1/2 z-50 hidden -translate-y-1/2 whitespace-nowrap rounded-md border border-sky-100 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 opacity-0 shadow-lg lg:block">
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
