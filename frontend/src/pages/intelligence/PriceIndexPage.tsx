import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { LineChart } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Label, Select } from "../../components/ui/input";
import { ErrorState, Spinner } from "../../components/ui/state";
import { api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { Product } from "../../lib/types";

interface PriceIndexSummary {
  product_id: string;
  product_name: string;
  sample_size: number;
  insufficient_data: boolean;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  distinct_suppliers: number;
  most_recent_observation: string | null;
  comparability_note: string;
}

export function PriceIndexPage() {
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const [chosen, setProductId] = useState("");
  const productId = chosen || products?.[0]?.id || "";  // open on the first product instead of an empty page

  const { data, isLoading, error } = useQuery({
    queryKey: ["price-index", productId],
    queryFn: () => api.get<PriceIndexSummary>(`/api/intelligence/price-index?product_id=${productId}`),
    enabled: !!productId,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <LineChart className="h-5 w-5 text-brand-500" /> Local Wholesale Price Index
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Built from real supplier price observations (listed offers and confirmed transaction prices), normalized to
          each product's base unit so pack sizes are directly comparable.
        </p>
      </div>

      <Card>
        <CardContent className="flex items-end gap-2 py-4">
          <div className="w-64 space-y-1">
            <Label>Product</Label>
            <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Select a product…</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load the price index." />}

      {data && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>{data.product_name}</CardTitle>
            <Badge variant={data.insufficient_data ? "default" : "info"}>{data.sample_size} observation(s)</Badge>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {data.insufficient_data ? (
              <p className="text-slate-500 dark:text-slate-400">{data.comparability_note}</p>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Average</p>
                    <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{formatINR(data.avg_price!, true)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Lowest</p>
                    <p className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">{formatINR(data.min_price!, true)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Highest</p>
                    <p className="text-lg font-semibold text-rose-600 dark:text-rose-400">{formatINR(data.max_price!, true)}</p>
                  </div>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 pt-2 dark:border-slate-800">
                  Across {data.distinct_suppliers} supplier(s). {data.comparability_note}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
