import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { TrendingDown } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label, Select } from "../../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { Product } from "../../lib/types";

interface MarginLine {
  product_id: string;
  product_name: string;
  selling_price_per_base_unit: number;
  cheapest_cost_per_base_unit: number | null;
  cheapest_supplier_name: string | null;
  margin_pct: number | null;
  margin_per_base_unit: number | null;
  is_leaking: boolean;
  note: string;
}

export function MarginLeakPage() {
  const qc = useQueryClient();
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const { data, isLoading, error } = useQuery({
    queryKey: ["margin-leak"],
    queryFn: () => api.get<MarginLine[]>("/api/intelligence/margin-leak"),
  });

  const [productId, setProductId] = useState("");
  const [price, setPrice] = useState("");

  const upsertMutation = useMutation({
    mutationFn: () => api.post("/api/intelligence/selling-prices", { product_id: productId, selling_price_per_base_unit: Number(price) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["margin-leak"] });
      setPrice("");
    },
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <TrendingDown className="h-5 w-5 text-brand-500" /> Margin Leak Detector
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Enter the price you sell a product at; we compare it against the cheapest current procurement offer. Every
          margin figure traces back to exactly those two numbers -- no hidden model.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Record a selling price</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1 space-y-1">
            <Label>Product</Label>
            <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Select…</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div className="w-40 space-y-1">
            <Label>Selling price (₹ / unit)</Label>
            <Input type="number" value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          <Button disabled={!productId || !price || upsertMutation.isPending} onClick={() => upsertMutation.mutate()}>
            Save
          </Button>
        </CardContent>
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load margin report." />}
      {data && data.length === 0 && (
        <EmptyState title="No selling prices recorded yet" hint="Add a selling price above to see your margin against the cheapest available supplier." />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {data?.map((line) => (
          <Card key={line.product_id} className={line.is_leaking ? "border-rose-200 dark:border-rose-900" : ""}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>{line.product_name}</CardTitle>
              {line.margin_pct != null ? (
                <Badge variant={line.is_leaking ? "danger" : "success"}>{line.margin_pct.toFixed(1)}% margin</Badge>
              ) : (
                <Badge variant="default">no comparison</Badge>
              )}
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p className="text-slate-600 dark:text-slate-300">{line.note}</p>
              {line.margin_per_base_unit != null && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Margin per unit: <strong className="text-slate-700 dark:text-slate-200">{formatINR(line.margin_per_base_unit, true)}</strong>
                  {line.cheapest_supplier_name && <> · cheapest from {line.cheapest_supplier_name}</>}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
