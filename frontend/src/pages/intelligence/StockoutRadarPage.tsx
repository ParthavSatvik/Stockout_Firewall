import { useQuery } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { api } from "../../lib/api";

interface RadarItem {
  product_id: string;
  product_name: string;
  sample_size: number;
  insufficient_data: boolean;
  avg_order_qty: number | null;
  avg_reorder_interval_days: number | null;
  days_since_last_order: number | null;
  network_stock_base_unit: number;
  risk_level: "none" | "low" | "medium" | "high" | "unknown";
  reasons: string[];
  recommended_action: string | null;
}

const RISK_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  high: "danger", medium: "warning", low: "default", none: "success", unknown: "default",
};

export function StockoutRadarPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stockout-radar"],
    queryFn: () => api.get<RadarItem[]>("/api/intelligence/stockout-radar"),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Radar className="h-5 w-5 text-brand-500" /> Predictive Stockout Radar
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Shortage risk estimated from your real order history and live network-wide supplier stock. Products with
          fewer than 2 past orders are marked "insufficient data" rather than given a fabricated risk score.
        </p>
      </div>

      {isLoading && <Spinner label="Analyzing order history…" />}
      {error && <ErrorState message="Could not load the stockout radar." />}
      {data && data.length === 0 && (
        <EmptyState title="Not enough order history yet" hint="Place a few orders for the same products to unlock reorder-risk estimates." />
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {data?.map((item) => (
          <Card key={item.product_id}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>{item.product_name}</CardTitle>
              <Badge variant={item.insufficient_data ? "default" : RISK_VARIANT[item.risk_level]}>
                {item.insufficient_data ? "insufficient data" : `${item.risk_level} risk`}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {item.insufficient_data ? (
                <p className="text-slate-500 dark:text-slate-400">{item.reasons[0]}</p>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <span>Avg order size: <strong className="text-slate-700 dark:text-slate-200">{item.avg_order_qty}</strong></span>
                    <span>Usual cycle: <strong className="text-slate-700 dark:text-slate-200">{item.avg_reorder_interval_days ?? "—"} days</strong></span>
                    <span>Since last order: <strong className="text-slate-700 dark:text-slate-200">{item.days_since_last_order} days</strong></span>
                    <span>Network stock: <strong className="text-slate-700 dark:text-slate-200">{Math.round(item.network_stock_base_unit)}</strong></span>
                  </div>
                  {item.reasons.length > 0 && (
                    <ul className="list-disc list-inside text-xs text-slate-600 dark:text-slate-300">
                      {item.reasons.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  )}
                  {item.recommended_action && (
                    <p className="rounded-md bg-brand-50 px-2 py-1.5 text-xs font-medium text-brand-700 dark:bg-brand-500/10 dark:text-brand-300">
                      {item.recommended_action}
                    </p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
