import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export function Tooltip({ content, children, className }: { content: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span className={cn("group relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-64 -translate-x-1/2 rounded-md bg-slate-900 px-2.5 py-1.5 text-xs text-white hidden shadow-lg group-hover:block group-focus-within:block dark:bg-slate-700"
      >
        {content}
        <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-700" />
      </span>
    </span>
  );
}

export function InfoHint({ text }: { text: string }) {
  return (
    <Tooltip content={text}>
      <span className="inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-slate-400 text-[9px] font-bold leading-none text-slate-500 dark:border-slate-600 dark:text-slate-400">
        i
      </span>
    </Tooltip>
  );
}
