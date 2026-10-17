import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Boxes } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input, Label, Select } from "../components/ui/input";
import { EmptyState } from "../components/ui/state";
import { useToast } from "../components/ui/toast";
import { api } from "../lib/api";
import { formatINR } from "../lib/format";
import type { Product, SupplierOffer } from "../lib/types";

export function SupplierInventoryPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: offers } = useQuery({
    queryKey: ["supplier-inventory"],
    queryFn: () => api.get<SupplierOffer[]>("/api/suppliers/me/inventory"),
  });
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });

  const [form, setForm] = useState({
    product_id: "", brand: "generic", pack_size: "25", pack_unit: "kg",
    price_per_base_unit: "", stock_qty_base_unit: "", moq_base_unit: "0",
  });

  const upsertMutation = useMutation({
    mutationFn: () =>
      api.post("/api/suppliers/me/inventory", {
        product_id: form.product_id, brand: form.brand, pack_size: Number(form.pack_size),
        pack_unit: form.pack_unit, price_per_base_unit: Number(form.price_per_base_unit),
        stock_qty_base_unit: Number(form.stock_qty_base_unit), moq_base_unit: Number(form.moq_base_unit),
        is_available: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["supplier-inventory"] });
      toast({ title: "Offer saved", description: "This price was also recorded for the Local Wholesale Price Index.", variant: "success" });
    },
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Boxes className="h-5 w-5 text-brand-500" /> Inventory & Pricing
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">What you list here is exactly what the optimizer sees for every merchant's order.</p>
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
            <Label>Pack size (base unit)</Label>
            <Input type="number" value={form.pack_size} onChange={(e) => setForm({ ...form, pack_size: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Price per base unit (₹)</Label>
            <Input type="number" value={form.price_per_base_unit} onChange={(e) => setForm({ ...form, price_per_base_unit: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Stock (base unit)</Label>
            <Input type="number" value={form.stock_qty_base_unit} onChange={(e) => setForm({ ...form, stock_qty_base_unit: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>MOQ (base unit)</Label>
            <Input type="number" value={form.moq_base_unit} onChange={(e) => setForm({ ...form, moq_base_unit: e.target.value })} />
          </div>
          <div className="col-span-2 md:col-span-3">
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
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  <th className="py-2">Product</th>
                  <th className="py-2">Pack</th>
                  <th className="py-2">Price</th>
                  <th className="py-2">Stock</th>
                  <th className="py-2">MOQ</th>
                  <th className="py-2">Freshness</th>
                </tr>
              </thead>
              <tbody>
                {offers.map((o) => (
                  <tr key={o.id} className="border-b border-slate-50 dark:border-slate-800/60">
                    <td className="py-2">{o.product_name}</td>
                    <td className="py-2">{o.pack_size} {o.pack_unit} ({o.brand})</td>
                    <td className="py-2 font-medium">{formatINR(o.price_per_base_unit, true)}</td>
                    <td className="py-2">{o.stock_qty_base_unit}</td>
                    <td className="py-2">{o.moq_base_unit}</td>
                    <td className="py-2"><Badge variant={o.freshness_source === "stale" ? "warning" : "default"}>{o.freshness_source}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="No offers listed yet" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
