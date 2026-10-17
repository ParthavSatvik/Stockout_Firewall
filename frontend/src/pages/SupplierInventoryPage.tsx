import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Boxes } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input, Label, Select } from "../components/ui/input";
import { EmptyState } from "../components/ui/state";
import { useToast } from "../components/ui/toast";
import { api, ApiError } from "../lib/api";
import { formatINR, timeAgo } from "../lib/format";
import type { Product, SupplierOffer } from "../lib/types";

function countedWithinDay(iso: string | null): boolean {
  return !!iso && Date.now() - new Date(iso).getTime() < 86_400_000;
}

export function SupplierInventoryPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: offers } = useQuery({
    queryKey: ["supplier-inventory"],
    queryFn: () => api.get<SupplierOffer[]>("/api/suppliers/me/inventory"),
  });
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });

  const [form, setForm] = useState({
    product_id: "", brand: "generic", pack_size: "25",
    price_per_base_unit: "", stock_qty_base_unit: "", moq_base_unit: "0", safety_stock_base_unit: "0",
  });
  // The pack unit is the product's canonical unit; the server rejects anything else.
  const unit = products?.find((p) => p.id === form.product_id)?.base_unit ?? "unit";

  const upsertMutation = useMutation({
    mutationFn: () =>
      api.post("/api/suppliers/me/inventory", {
        product_id: form.product_id, brand: form.brand, pack_size: Number(form.pack_size),
        pack_unit: unit, price_per_base_unit: Number(form.price_per_base_unit),
        stock_qty_base_unit: Number(form.stock_qty_base_unit), moq_base_unit: Number(form.moq_base_unit),
        safety_stock_base_unit: Number(form.safety_stock_base_unit), is_available: true,
      }),
    onSuccess: () => {
      ["supplier-inventory", "promise-ledger", "supplier-copilot"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast({ title: "Offer saved", description: "Counted as a fresh stock count. The price was also recorded for the Local Wholesale Price Index.", variant: "success" });
    },
    onError: (e) => toast({ title: "Offer not saved", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" }),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Boxes className="h-5 w-5 text-brand-500" /> Inventory & Pricing
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Enter physical stock on hand. Merchants are offered only your free-to-promise quantity: on hand minus live commitments and safety stock.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add / update an offer</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <div className="col-span-2 space-y-1 md:col-span-1">
            <Label>Product</Label>
            <Select value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
              <option value="">Select…</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Brand</Label>
            <Input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Pack size ({unit})</Label>
            <Input type="number" value={form.pack_size} onChange={(e) => setForm({ ...form, pack_size: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Price per {unit} (₹)</Label>
            <Input type="number" value={form.price_per_base_unit} onChange={(e) => setForm({ ...form, price_per_base_unit: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Physical stock on hand ({unit})</Label>
            <Input type="number" value={form.stock_qty_base_unit} onChange={(e) => setForm({ ...form, stock_qty_base_unit: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>MOQ ({unit})</Label>
            <Input type="number" value={form.moq_base_unit} onChange={(e) => setForm({ ...form, moq_base_unit: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Safety stock ({unit})</Label>
            <Input type="number" min={0} value={form.safety_stock_base_unit} onChange={(e) => setForm({ ...form, safety_stock_base_unit: e.target.value })} />
          </div>
          <div className="col-span-2 md:col-span-2 md:self-end">
            <Button disabled={!form.product_id || upsertMutation.isPending} onClick={() => upsertMutation.mutate()}>
              Save offer
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>My current offers</CardTitle>
        </CardHeader>
        <CardContent>
          {offers && offers.length > 0 ? (
            <div className="overflow-x-auto"><table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  <th className="py-2">Product</th>
                  <th className="py-2">Pack</th>
                  <th className="py-2">Price</th>
                  <th className="py-2">On hand</th>
                  <th className="py-2">Committed</th>
                  <th className="py-2">Free to promise</th>
                  <th className="py-2">MOQ</th>
                  <th className="py-2">Last count</th>
                </tr>
              </thead>
              <tbody>
                {offers.map((o) => (
                  <tr key={o.id} className="border-b border-slate-50 dark:border-slate-800/60">
                    <td className="py-2">{o.product_name}</td>
                    <td className="py-2">{o.pack_size} {o.pack_unit} ({o.brand})</td>
                    <td className="py-2 font-medium">{formatINR(o.price_per_base_unit, true)}</td>
                    <td className="py-2 tabular-nums">{o.stock_qty_base_unit}</td>
                    <td className="py-2 tabular-nums">{o.committed_qty_base_unit}</td>
                    <td className="py-2 font-semibold tabular-nums">{o.free_to_promise_base_unit}{o.safety_stock_base_unit > 0 && <span className="ml-1 text-xs font-normal text-slate-500">({o.safety_stock_base_unit} safety)</span>}</td>
                    <td className="py-2 tabular-nums">{o.moq_base_unit}</td>
                    <td className="py-2"><Badge variant={countedWithinDay(o.stock_confirmed_at) ? "default" : "warning"}>{o.stock_confirmed_at ? timeAgo(o.stock_confirmed_at) : "never"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <EmptyState title="No offers listed yet" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
