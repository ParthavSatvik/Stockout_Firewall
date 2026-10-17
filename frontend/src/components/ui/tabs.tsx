import { cn } from "../../lib/utils";

export interface TabItem {
  value: string;
  label: string;
  badge?: number;
}

export function Tabs({
  items, value, onChange, className,
}: { items: TabItem[]; value: string; onChange: (v: string) => void; className?: string }) {
  return (
    <div className={cn("flex gap-1 border-b border-slate-200 dark:border-slate-800", className)}>
      {items.map((item) => (
        <button
          key={item.value}
          onClick={() => onChange(item.value)}
          className={cn(
            "relative flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors",
            value === item.value
              ? "text-brand-700 dark:text-brand-400"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {item.label}
          {item.badge !== undefined && item.badge > 0 && (
            <span className="rounded-full bg-signal-500 px-1.5 text-[10px] font-semibold text-white">{item.badge}</span>
          )}
          {value === item.value && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-brand-600 dark:bg-brand-400" />
          )}
        </button>
      ))}
    </div>
  );
}
