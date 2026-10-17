import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Wallet } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label } from "../../components/ui/input";
import { ErrorState, Spinner } from "../../components/ui/state";
import { api } from "../../lib/api";
import { formatDate, formatINR } from "../../lib/format";

interface CashCycleSummary {
  available_cash: number | null;
  sample_size: number;
  insufficient_data: boolean;
  avg_order_cost: number | null;
  avg_interval_days: number | null;
  last_order_date: string | null;
  projected_next_order_date: string | null;
  cash_coverage_ratio: number | null;
  status: "no_cash_input" | "insufficient_data" | "comfortable" | "tight" | "short";
  explanation: string;
}

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  no_cash_input: "default", insufficient_data: "default", comfortable: "success", tight: "warning", short: "danger",
};

export function CashCyclePage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["cash-cycle"],
    queryFn: () => api.get<CashCycleSummary>("/api/intelligence/cash-cycle"),
  });
  const [cashInput, setCashInput] = useState("");

  const setCashMutation = useMutation({
    mutationFn: () => api.post<CashCycleSummary>("/api/intelligence/cash-cycle/cash-on-hand", { available_cash_on_hand: Number(cashInput) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cash-cycle"] }),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Wallet className="h-5 w-5 text-brand-500" /> Cash-Cycle Buying Planner
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Your cash on hand is an input you provide -- never inferred or assumed from a bank balance. Upcoming spend
          is projected from your real order history, with an explicit "not enough data" fallback.
        </p>
      </div>

      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load cash-cycle data." />}

      {data && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Available cash on hand</CardTitle>
            </CardHeader>
            <CardContent className="flex items-end gap-2">
              <div className="w-48 space-y-1">
                <Label>Amount (₹)</Label>
                <Input type="number" placeholder={data.available_cash?.toString() ?? "e.g. 25000"} value={cashInput} onChange={(e) => setCashInput(e.target.value)} />
              </div>
              <Button disabled={!cashInput || setCashMutation.isPending} onClick={() => setCashMutation.mutate()}>
                Update
              </Button>
              {data.available_cash != null && <span className="ml-2 text-sm text-slate-500">Current: {formatINR(data.available_cash)}</span>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>Cash coverage</CardTitle>
              <Badge variant={STATUS_VARIANT[data.status]}>{data.status.replace(/_/g, " ")}</Badge>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-slate-600 dark:text-slate-300">{data.explanation}</p>
              {!data.insufficient_data && data.avg_order_cost != null && (
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-slate-800">
                  <span>Avg order cost: <strong className="text-slate-700 dark:text-slate-200">{formatINR(data.avg_order_cost)}</strong></span>
                  <span>Usual cycle: <strong className="text-slate-700 dark:text-slate-200">{data.avg_interval_days} days</strong></span>
                  {data.last_order_date && <span>Last order: <strong className="text-slate-700 dark:text-slate-200">{formatDate(data.last_order_date)}</strong></span>}
                  {data.projected_next_order_date && <span>Next expected: <strong className="text-slate-700 dark:text-slate-200">{formatDate(data.projected_next_order_date)}</strong></span>}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
