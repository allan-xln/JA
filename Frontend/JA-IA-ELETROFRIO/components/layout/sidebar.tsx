import {
  AlertTriangle,
  ClipboardList,
  SlidersHorizontal,
  LayoutDashboard,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Snowflake,
} from "lucide-react";

const items = [
  { id: "dashboard", label: "Visão geral", icon: LayoutDashboard },
  { id: "ativos", label: "Ativos", icon: Snowflake },
  { id: "alertas", label: "Ocorrências", icon: AlertTriangle },
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
      className={`fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-white/95 text-slate-700 shadow-xl backdrop-blur-xl lg:static lg:inset-auto lg:z-auto lg:flex-col lg:border-r lg:border-t-0 ${
        collapsed ? "lg:w-[76px]" : "lg:w-[260px]"
      }`}
    >
      <div className="hidden border-b border-white/10 p-3 lg:block">
        <div className={`flex items-center gap-3 ${collapsed ? "justify-center" : "justify-between"}`}>
          <div className={collapsed ? "h-10 w-10 overflow-hidden rounded-lg border border-white/10 bg-white p-1.5" : "min-w-0 rounded-lg bg-white px-3 py-2"}>
            {collapsed ? (
              <img
                src="/eletrofrio-logo.png"
                alt="Eletrofrio"
                className="h-7 w-[138px] max-w-none object-contain object-left"
              />
            ) : (
              <img
                src="/eletrofrio-logo.png"
                alt="Eletrofrio Refrigeração"
                className="h-11 w-full max-w-[190px] object-contain"
              />
            )}
          </div>
          {onToggle ? (
            <button
              type="button"
              onClick={onToggle}
              title={collapsed ? "Abrir menu" : "Recolher menu"}
              aria-label={collapsed ? "Abrir menu" : "Recolher menu"}
              className="hidden h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.6] text-slate-600 transition hover:bg-white lg:inline-flex"
            >
              <ToggleIcon className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      <nav className={`grid w-full grid-cols-6 gap-1 p-2 lg:flex lg:w-auto lg:flex-col lg:gap-2 lg:overflow-visible ${collapsed ? "lg:items-center" : "lg:items-stretch"}`}>
        {visibleItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.label}
              type="button"
              onClick={() => onViewChange(item.id)}
              title={item.label}
              aria-label={item.label}
              className={`group flex h-12 min-w-0 items-center gap-3 rounded-lg border px-3 text-center text-sm font-semibold transition hover:scale-[1.01] ${
                collapsed ? "justify-center lg:w-12" : "justify-center lg:justify-start"
              } ${
                activeView === item.id
                  ? "border-sky-300/45 bg-sky-50 text-sky-800 shadow-sm"
                  : "border-transparent text-slate-500 hover:border-white/10 hover:bg-white/[0.72] hover:text-slate-900"
              }`}
            >
              <Icon className="h-5 w-5" />
              {!collapsed ? <span className="hidden truncate lg:block">{item.label}</span> : null}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
