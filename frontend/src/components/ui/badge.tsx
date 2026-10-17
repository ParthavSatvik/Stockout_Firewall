import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { statusKey, useT } from "../../lib/i18n";
import { cn } from "../../lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
      success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
      warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-400",
      danger: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400",
      info: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-400",
      signal: "bg-signal-500/15 text-signal-600 dark:text-signal-400",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  pulse?: boolean;
}

export function Badge({ className, variant, pulse, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {pulse && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {children}
    </span>
  );
}

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger" | "info"> = {
  draft: "default",
  planned: "info",
  awaiting_confirmation: "warning",
  confirmed: "info",
  replanning: "warning",
  partially_fulfilled: "warning",
  fulfilled: "success",
  infeasible: "danger",
  cancelled: "default",
  proposed: "default",
  rejected: "danger",
  expired: "danger",
  short_supply: "warning",
  superseded: "default",
};

const LIVE_STATUSES = new Set(["replanning", "awaiting_confirmation"]);

export function StatusBadge({ status }: { status: string }) {
  const { t } = useT();
  const key = statusKey(status);
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "default"} pulse={LIVE_STATUSES.has(status)}>
      {key ? t(key) : status.replace(/_/g, " ")}
    </Badge>
  );
}
