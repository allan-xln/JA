import {
  AlertTriangle,
  ClipboardList,
  SlidersHorizontal,
  LayoutDashboard,
  MessageCircle,
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
};

export function Sidebar({ activeView, onViewChange, role = "admin", totals }: SidebarProps) {
  void totals;
  const visibleItems = role === "admin" ? items : items.filter((item) => item.id !== "operacao");

  return (
    <aside className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-[#0b1118]/95 text-slate-200 shadow-xl lg:static lg:inset-auto lg:z-auto lg:flex-col lg:border-r lg:border-t-0 lg:bg-[#0b1118]/95">
      <div className="hidden border-b border-white/10 p-3 lg:flex lg:items-center lg:justify-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.06] text-sm font-bold text-sky-200">
          EF
        </div>
      </div>

      <nav className="grid w-full grid-cols-6 gap-1 p-2 lg:flex lg:w-auto lg:flex-col lg:items-center lg:gap-2 lg:overflow-visible">
        {visibleItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.label}
              type="button"
              onClick={() => onViewChange(item.id)}
              title={item.label}
              aria-label={item.label}
              className={`group flex h-12 min-w-0 items-center justify-center rounded-lg border text-center transition hover:scale-[1.03] lg:w-12 ${
                activeView === item.id
                  ? "border-sky-300/35 bg-white/[0.08] text-sky-100"
                  : "border-transparent text-slate-500 hover:border-white/10 hover:bg-white/[0.055] hover:text-slate-100"
              }`}
            >
              <Icon className="h-5 w-5" />
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
