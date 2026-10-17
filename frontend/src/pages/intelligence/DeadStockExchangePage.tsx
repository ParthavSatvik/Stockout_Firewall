import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, Recycle, X } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label, Select } from "../../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { Tabs } from "../../components/ui/tabs";
import { useToast } from "../../components/ui/toast";
import { api, ApiError } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { Product } from "../../lib/types";

interface SurplusOffer {
  id: string;
  listing_id: string;
  qty_requested_base_unit: number;
  offered_price_per_base_unit: number;
  status: "pending" | "accepted" | "declined";
  offerer_name: string;
}

interface SurplusListing {
  id: string;
  product_id: string;
  product_name: string;
  qty_base_unit: number;
  asking_price_per_base_unit: number;
  status: "open" | "matched" | "closed";
  lister_type: "merchant" | "supplier";
  lister_name: string;
  is_mine: boolean;
  pending_offer_count: number;
  my_offer: SurplusOffer | null;
}

const OFFER_BADGE = { pending: "warning", accepted: "success", declined: "default" } as const;

function useErrorToast() {
  const { toast } = useToast();
  return (e: unknown) => toast({ title: "Not done", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" });
}

function MyListing({ listing }: { listing: SurplusListing }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const fail = useErrorToast();
  const offers = useQuery({ queryKey: ["surplus-offers", listing.id], queryFn: () => api.get<SurplusOffer[]>(`/api/catalog/surplus/${listing.id}/offers`) });
  const refresh = () => ["surplus", "surplus-offers"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "accept" | "decline" }) => api.post(`/api/catalog/surplus/offers/${id}/${action}`),
    onSuccess: (_, v) => { refresh(); toast({ title: v.action === "accept" ? "Offer accepted — listing matched" : "Offer declined", variant: v.action === "accept" ? "success" : "info" }); },
    onError: fail,
  });
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{listing.product_name}</CardTitle>
        <Badge variant={listing.status === "open" ? "info" : "success"}>{listing.status === "open" ? `${listing.pending_offer_count} pending offer(s)` : listing.status}</Badge>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-slate-600 dark:text-slate-300">You listed {listing.qty_base_unit} units at {formatINR(listing.asking_price_per_base_unit, true)}/unit</p>
        {offers.isPending && <Spinner label="Loading offers…" />}
        {offers.data && offers.data.length === 0 && <p className="text-xs text-slate-500">No offers yet.</p>}
        {offers.data && offers.data.length > 0 && (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {offers.data.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                <span><span className="font-medium">{o.offerer_name}</span> — {o.qty_requested_base_unit} units @ {formatINR(o.offered_price_per_base_unit, true)}
                  <span className="text-xs text-slate-500"> ({formatINR(o.qty_requested_base_unit * o.offered_price_per_base_unit)})</span></span>
                {o.status === "pending" && listing.status === "open" ? (
                  <span className="flex gap-1.5">
                    <Button size="sm" variant="success" disabled={decide.isPending} onClick={() => decide.mutate({ id: o.id, action: "accept" })}><Check className="h-3.5 w-3.5" aria-hidden />Accept</Button>
                    <Button size="sm" variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate({ id: o.id, action: "decline" })}><X className="h-3.5 w-3.5" aria-hidden />Decline</Button>
                  </span>
                ) : <Badge variant={OFFER_BADGE[o.status]}>{o.status}</Badge>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function MarketListing({ listing }: { listing: SurplusListing }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const fail = useErrorToast();
  const [qty, setQty] = useState(String(listing.my_offer?.qty_requested_base_unit ?? listing.qty_base_unit));
  const [price, setPrice] = useState(String(listing.my_offer?.offered_price_per_base_unit ?? listing.asking_price_per_base_unit));
  const offer = useMutation({
    mutationFn: () => api.post(`/api/catalog/surplus/${listing.id}/offers`, { qty_requested_base_unit: Number(qty), offered_price_per_base_unit: Number(price) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["surplus"] }); toast({ title: listing.my_offer ? "Offer updated" : "Offer sent", description: "The lister will accept or decline it.", variant: "success" }); },
    onError: fail,
  });
  const mine = listing.my_offer;
  const canOffer = listing.status === "open" && (!mine || mine.status === "pending" || mine.status === "declined");
  const invalid = !qty || !price || Number(qty) <= 0 || Number(price) <= 0 || Number(qty) > listing.qty_base_unit;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{listing.product_name}</CardTitle>
        <Badge variant={listing.lister_type === "merchant" ? "info" : "default"}>{listing.lister_type}</Badge>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-slate-600 dark:text-slate-300">{listing.qty_base_unit} units at {formatINR(listing.asking_price_per_base_unit, true)}/unit — from {listing.lister_name}</p>
        {mine && (
          <p className="flex items-center gap-2 text-xs">Your offer: {mine.qty_requested_base_unit} @ {formatINR(mine.offered_price_per_base_unit, true)} <Badge variant={OFFER_BADGE[mine.status]}>{mine.status}</Badge></p>
        )}
        {canOffer && (
          <form className="flex flex-wrap items-end gap-2 pt-1" onSubmit={(e) => { e.preventDefault(); if (!invalid) offer.mutate(); }}>
            <div className="space-y-1"><Label htmlFor={`q-${listing.id}`}>Qty (max {listing.qty_base_unit})</Label>
              <Input id={`q-${listing.id}`} type="number" min={0} max={listing.qty_base_unit} step="any" className="w-24" value={qty} onChange={(e) => setQty(e.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor={`p-${listing.id}`}>Offer ₹/unit</Label>
              <Input id={`p-${listing.id}`} type="number" min={0} step="0.5" className="w-28" value={price} onChange={(e) => setPrice(e.target.value)} /></div>
            <Button type="submit" size="sm" variant="outline" disabled={invalid || offer.isPending}>{mine?.status === "pending" ? "Update offer" : "Make offer"}</Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export function DeadStockExchangePage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const fail = useErrorToast();
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const { data: listings, isLoading, error } = useQuery({ queryKey: ["surplus"], queryFn: () => api.get<SurplusListing[]>("/api/catalog/surplus"), refetchInterval: 10_000 });
  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [tab, setTab] = useState("market");

  const createMutation = useMutation({
    mutationFn: () => api.post("/api/catalog/surplus", { product_id: productId, qty_base_unit: Number(qty), asking_price_per_base_unit: Number(price) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["surplus"] });
      setQty(""); setPrice(""); setProductId(""); setTab("mine");
      toast({ title: "Listed", description: "Your surplus is now visible to the network.", variant: "success" });
    },
    onError: fail,
  });

  const mine = listings?.filter((l) => l.is_mine) ?? [];
  const market = listings?.filter((l) => !l.is_mine) ?? [];
  const pendingForMe = mine.reduce((n, l) => n + (l.status === "open" ? l.pending_offer_count : 0), 0);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Recycle className="h-5 w-5 text-brand-500" /> Dead-Stock Rescue Exchange
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          List excess stock for the network, or make an offer on someone else's. Nothing changes hands until the lister accepts an offer.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>List your surplus</CardTitle></CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); createMutation.mutate(); }}>
            <div className="min-w-48 flex-1 space-y-1">
              <Label htmlFor="ds-product">Product</Label>
              <Select id="ds-product" value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="">Select…</option>
                {products?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.base_unit})</option>)}
              </Select>
            </div>
            <div className="w-28 space-y-1"><Label htmlFor="ds-qty">Quantity</Label><Input id="ds-qty" type="number" min={0} value={qty} onChange={(e) => setQty(e.target.value)} /></div>
            <div className="w-36 space-y-1"><Label htmlFor="ds-price">Asking price (₹/unit)</Label><Input id="ds-price" type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} /></div>
            <Button type="submit" disabled={!productId || !(Number(qty) > 0) || !(Number(price) > 0) || createMutation.isPending}>List it</Button>
          </form>
        </CardContent>
      </Card>

      <Tabs value={tab} onChange={setTab} items={[
        { value: "market", label: "Market", badge: market.filter((l) => l.status === "open").length },
        { value: "mine", label: "Your listings & offers received", badge: pendingForMe },
      ]} />
      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load the exchange." />}
      {tab === "market" && listings && (market.length === 0
        ? <EmptyState title="No surplus from others right now" />
        : <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{market.map((l) => <MarketListing key={l.id} listing={l} />)}</div>)}
      {tab === "mine" && listings && (mine.length === 0
        ? <EmptyState title="You have not listed anything" hint="Use the form above to list excess stock." />
        : <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{mine.map((l) => <MyListing key={l.id} listing={l} />)}</div>)}
    </div>
  );
}
