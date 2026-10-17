import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Store } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";
import { Label, Select } from "../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../components/ui/state";
import { api } from "../lib/api";
import { formatINR, timeAgo } from "../lib/format";
import type { Product, SupplierOffer } from "../lib/types";

const FRESH = { fresh: "success", aging: "info", stale: "danger", unknown: "warning" } as const;

/** Merchant view of what suppliers can sell right now: free-to-promise stock (never
 *  safety stock or stock already promised to others), price, MOQ and evidence. */
export function MarketInventoryPage() {
  const [productId, setProductId] = useState("");
  const products = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const offers = useQuery({
    queryKey: ["market-offers", productId],
    queryFn: () => api.get<SupplierOffer[]>(`/api/catalog/offers${productId ? `?product_id=${productId}` : ""}`),
    refetchInterval: 30_000,
  });
  const cheapest = useMemo(() => {
    const best: Record<string, number> = {};
    // Only listings the planner can actually use: free stock and counted within 24h.
    for (const o of offers.data ?? []) if (o.free_to_promise_base_unit > 0 && o.freshness_source !== "stale") best[o.product_id] = Math.min(best[o.product_id] ?? Infinity, o.price_per_base_unit);
    return best;
  }, [offers.data]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100"><Store className="h-5 w-5 text-brand-500" /> Market Inventory & Pricing</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">What every supplier can sell you right now. Quantities are free to promise: stock already promised to other shops and suppliers' safety stock are excluded.</p>
        </div>
        <div className="w-56 space-y-1">
          <Label htmlFor="mi-product">Product</Label>
          <Select id="mi-product" value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="">All products</option>
            {products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </div>
      </div>
      {offers.isPending && <Spinner label="Loading supplier offers…" />}
      {offers.isError && <ErrorState message="Could not load supplier offers." />}
      {offers.data && offers.data.length === 0 && <EmptyState title="No supplier is offering this product right now" />}
      {offers.data && offers.data.length > 0 && (
        <Card>
          <CardContent className="overflow-x-auto pt-4">
            <table className="w-full min-w-[46rem] text-sm">
              <thead><tr className="border-b border-slate-100 text-left text-xs text-slate-500 dark:border-slate-800">
                <th className="py-2">Product</th><th>Supplier</th><th>Pack</th><th className="text-right">Price</th><th className="text-right">Available</th>
                <th className="text-right">MOQ</th><th>Stock counted</th><th>Reliability</th>
              </tr></thead>
              <tbody>{offers.data.map((o) => (
                <tr key={o.id} className="border-b border-slate-50 dark:border-slate-800/60">
                  <td className="py-2 font-medium">{o.product_name}</td>
                  <td><Link to={`/merchant/suppliers/${o.supplier_id}/passport`} className="text-brand-700 hover:underline dark:text-brand-400">{o.supplier_name}</Link></td>
                  <td className="text-slate-600 dark:text-slate-300">{o.pack_size} {o.pack_unit} · {o.brand}</td>
                  <td className="text-right tabular-nums">
                    {formatINR(o.price_per_base_unit, true)}/{o.pack_unit}
                    {cheapest[o.product_id] === o.price_per_base_unit && <Badge variant="success" className="ml-1.5">cheapest</Badge>}
                  </td>
                  <td className={`text-right tabular-nums ${o.free_to_promise_base_unit <= 0 ? "text-rose-600" : ""}`}>{o.free_to_promise_base_unit} {o.pack_unit}</td>
                  <td className="text-right tabular-nums">{o.moq_base_unit}</td>
                  <td><Badge variant={FRESH[o.freshness_source as keyof typeof FRESH] ?? "default"}>{o.stock_confirmed_at ? timeAgo(o.stock_confirmed_at) : "never"}</Badge></td>
                  <td className="tabular-nums">{Math.round(o.reliability_score * 100)}% <span className="text-xs text-slate-500">({o.reliability_confidence}, n={o.reliability_sample_size})</span></td>
                </tr>
              ))}</tbody>
            </table>
            <p className="mt-2 text-[11px] text-slate-500">Listings not counted in 24h are not offered by the planner. Reliability is the planner's score; open a supplier for the full Trust Passport.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
