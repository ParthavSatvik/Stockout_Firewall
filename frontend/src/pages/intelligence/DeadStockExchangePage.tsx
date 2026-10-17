import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Recycle } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label, Select } from "../../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { useToast } from "../../components/ui/toast";
import { api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { Product } from "../../lib/types";

interface SurplusListing {
  id: string;
  product_id: string;
  product_name: string;
  qty_base_unit: number;
  asking_price_per_base_unit: number;
  status: string;
  lister_type: "merchant" | "supplier";
  lister_name: string;
}

export function DeadStockExchangePage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const { data: listings, isLoading, error } = useQuery({
    queryKey: ["surplus"],
    queryFn: () => api.get<SurplusListing[]>("/api/catalog/surplus"),
  });

  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [offerQty, setOfferQty] = useState<Record<string, string>>({});
  const [offerPrice, setOfferPrice] = useState<Record<string, string>>({});

  const createMutation = useMutation({
    mutationFn: () => api.post("/api/catalog/surplus", { product_id: productId, qty_base_unit: Number(qty), asking_price_per_base_unit: Number(price) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["surplus"] });
      setQty(""); setPrice(""); setProductId("");
      toast({ title: "Listed", description: "Your surplus is now visible to the network.", variant: "success" });
    },
  });

  const offerMutation = useMutation({
    mutationFn: ({ listingId }: { listingId: string }) =>
      api.post(`/api/catalog/surplus/${listingId}/offers`, {
        qty_requested_base_unit: Number(offerQty[listingId]), offered_price_per_base_unit: Number(offerPrice[listingId]),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["surplus"] });
      toast({ title: "Offer sent", description: "The lister will review and may accept it.", variant: "success" });
    },
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Recycle className="h-5 w-5 text-brand-500" /> Dead-Stock Rescue Exchange
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          List excess inventory for the network to claim, or make an offer on someone else's listing. Nothing is
          transferred automatically -- the lister must accept an offer.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>List your surplus</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1 space-y-1">
            <Label>Product</Label>
            <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Select…</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div className="w-28 space-y-1">
            <Label>Quantity</Label>
            <Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="w-36 space-y-1">
            <Label>Asking price (₹/unit)</Label>
            <Input type="number" value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          <Button disabled={!productId || !qty || !price || createMutation.isPending} onClick={() => createMutation.mutate()}>
            List it
          </Button>
        </CardContent>
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load the exchange." />}
      {listings && listings.length === 0 && <EmptyState title="No surplus listed right now" />}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {listings?.map((listing) => (
          <Card key={listing.id}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>{listing.product_name}</CardTitle>
              <Badge variant={listing.lister_type === "merchant" ? "info" : "default"}>{listing.lister_type}</Badge>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-slate-600 dark:text-slate-300">
                {listing.qty_base_unit} units at {formatINR(listing.asking_price_per_base_unit, true)}/unit — from {listing.lister_name}
              </p>
              <div className="flex items-end gap-2 pt-1">
                <Input type="number" placeholder="Qty" className="w-20" value={offerQty[listing.id] ?? ""} onChange={(e) => setOfferQty((p) => ({ ...p, [listing.id]: e.target.value }))} />
                <Input type="number" placeholder="Offer ₹/unit" className="w-28" value={offerPrice[listing.id] ?? ""} onChange={(e) => setOfferPrice((p) => ({ ...p, [listing.id]: e.target.value }))} />
                <Button
                  size="sm" variant="outline"
                  disabled={!offerQty[listing.id] || !offerPrice[listing.id] || offerMutation.isPending}
                  onClick={() => offerMutation.mutate({ listingId: listing.id })}
                >
                  Make offer
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
