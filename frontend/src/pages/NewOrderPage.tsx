import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input, Label, Select } from "../components/ui/input";
import { ErrorState, Spinner } from "../components/ui/state";
import { InfoHint } from "../components/ui/tooltip";
import { useToast } from "../components/ui/toast";
import { ApiError, api } from "../lib/api";
import type { ObjectiveProfile, Order, ParseResponse, Product } from "../lib/types";

const SAMPLE_TEXTS = [
  { label: "Kannada/English code-mixed", text: "nanage 100 kg akki mattu 20 kg sakkare beku" },
  { label: "Hindi/English code-mixed", text: "mujhe 50 kg chawal aur 10 litre tel chahiye" },
  { label: "English", text: "I need 30 kg toor dal and 15 kg sugar" },
];

interface DraftLine {
  product_id: string;
  product_name: string;
  requested_qty_base_unit: number;
  substitution_allowed: boolean;
}

export function NewOrderPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });

  const [text, setText] = useState("");
  const [parseResult, setParseResult] = useState<ParseResponse | null>(null);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [manualProductId, setManualProductId] = useState("");
  const [manualQty, setManualQty] = useState("");

  const [objectiveProfile, setObjectiveProfile] = useState<ObjectiveProfile>("cheapest");
  const [budgetCap, setBudgetCap] = useState("");
  const [priceTolerance, setPriceTolerance] = useState(15);
  const [minReliability, setMinReliability] = useState(0.5);
  const [maxSuppliers, setMaxSuppliers] = useState(4);
  const [error, setError] = useState<string | null>(null);

  const parseMutation = useMutation({
    mutationFn: () => api.post<ParseResponse>("/api/orders/parse-text", { text, language: "auto" }),
    onSuccess: (resp) => {
      setParseResult(resp);
      const matched = resp.items.filter((i) => i.product_id && i.product_name);
      setLines((prev) => [
        ...prev,
        ...matched.map((i) => ({
          product_id: i.product_id!,
          product_name: i.product_name!,
          requested_qty_base_unit: i.quantity_base_unit,
          substitution_allowed: true,
        })),
      ]);
    },
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<Order>("/api/orders", {
        items: lines.map((l) => ({
          product_id: l.product_id,
          requested_qty_base_unit: l.requested_qty_base_unit,
          substitution_allowed: l.substitution_allowed,
        })),
        objective_profile: objectiveProfile,
        budget_cap: budgetCap ? Number(budgetCap) : null,
        price_tolerance_pct: priceTolerance,
        min_reliability: minReliability,
        max_suppliers: maxSuppliers,
        raw_input_text: text,
      }),
    onSuccess: (order) => {
      toast({ title: "Order created", description: "Generate plans to compare cheapest, fastest, and most reliable options.", variant: "success" });
      navigate(`/merchant/orders/${order.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not create order"),
  });

  function addManualLine() {
    const product = products?.find((p) => p.id === manualProductId);
    if (!product || !manualQty) return;
    setLines((prev) => [
      ...prev,
      { product_id: product.id, product_name: product.name, requested_qty_base_unit: Number(manualQty), substitution_allowed: true },
    ]);
    setManualQty("");
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">New Order</h1>

      <Card>
        <CardHeader>
          <CardTitle>1. Describe what you need (voice input falls back to text without Sarvam credentials)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="w-full rounded-lg border border-slate-300 bg-white p-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            rows={3}
            placeholder="e.g. nanage 100 kg akki beku..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {SAMPLE_TEXTS.map((s) => (
              <button
                key={s.label}
                type="button"
                className="text-xs rounded-full bg-slate-100 px-3 py-1 text-slate-600 hover:bg-slate-200"
                onClick={() => setText(s.text)}
              >
                {s.label}
              </button>
            ))}
          </div>
          <Button data-testid="parse-button" type="button" onClick={() => parseMutation.mutate()} disabled={!text || parseMutation.isPending}>
            {parseMutation.isPending ? "Parsing…" : "Parse (deterministic lexicon, no LLM)"}
          </Button>

          {parseResult && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm space-y-1 dark:bg-slate-800/60">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Overall confidence: {(parseResult.overall_confidence * 100).toFixed(0)}%
                {parseResult.requires_confirmation && (
                  <Badge variant="warning" className="ml-2">
                    Low confidence — please verify items below
                  </Badge>
                )}
              </p>
              {parseResult.items.map((item, idx) => (
                <div key={idx} className="flex justify-between">
                  <span>"{item.matched_text}" → {item.product_name ?? "unrecognized"}</span>
                  <span className="text-slate-500 dark:text-slate-400">{(item.confidence * 100).toFixed(0)}% match</span>
                </div>
              ))}
              {parseResult.unmatched_fragments.length > 0 && (
                <p className="text-amber-600 dark:text-amber-400 text-xs">Unmatched: {parseResult.unmatched_fragments.join(", ")}</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Basket</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {lines.length === 0 && <p className="text-sm text-slate-400 dark:text-slate-500">No items yet. Parse text above or add manually.</p>}
          {lines.map((line, idx) => (
            <div key={idx} className="flex items-center gap-2 text-sm">
              <span className="flex-1">{line.product_name}</span>
              <Input
                type="number"
                className="w-24"
                value={line.requested_qty_base_unit}
                onChange={(e) =>
                  setLines((prev) =>
                    prev.map((l, i) => (i === idx ? { ...l, requested_qty_base_unit: Number(e.target.value) } : l)),
                  )
                }
              />
              <Button type="button" variant="ghost" size="sm" onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}>
                Remove
              </Button>
            </div>
          ))}

          <div className="flex items-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
            <div className="flex-1 space-y-1">
              <Label>Add product manually</Label>
              <Select value={manualProductId} onChange={(e) => setManualProductId(e.target.value)}>
                <option value="">Select product…</option>
                {products?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.base_unit})
                  </option>
                ))}
              </Select>
            </div>
            <div className="w-24 space-y-1">
              <Label>Qty</Label>
              <Input type="number" value={manualQty} onChange={(e) => setManualQty(e.target.value)} />
            </div>
            <Button type="button" variant="outline" onClick={addManualLine}>
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Merchant rules</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label>Default objective</Label>
            <Select value={objectiveProfile} onChange={(e) => setObjectiveProfile(e.target.value as ObjectiveProfile)}>
              <option value="cheapest">Cheapest</option>
              <option value="fastest">Fastest</option>
              <option value="most_reliable">Most reliable</option>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="flex items-center gap-1">
              Budget cap (₹, optional) <InfoHint text="A hard ceiling on total product cost. The optimizer will never exceed it, even if that means leaving part of the basket unfulfilled." />
            </Label>
            <Input type="number" value={budgetCap} onChange={(e) => setBudgetCap(e.target.value)} placeholder="No limit" />
          </div>
          <div className="space-y-1">
            <Label className="flex items-center gap-1">
              Price tolerance (% above cheapest) <InfoHint text="Suppliers priced more than this percentage above the cheapest eligible offer are excluded from consideration." />
            </Label>
            <Input type="number" value={priceTolerance} onChange={(e) => setPriceTolerance(Number(e.target.value))} />
          </div>
          <div className="space-y-1">
            <Label className="flex items-center gap-1">
              Minimum supplier reliability (0-1) <InfoHint text="Suppliers with a lower real reliability score (from actual commitment history) are excluded, regardless of price." />
            </Label>
            <Input
              type="number"
              step="0.05"
              min={0}
              max={1}
              value={minReliability}
              onChange={(e) => setMinReliability(Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <Label className="flex items-center gap-1">
              Max suppliers per order <InfoHint text="Caps how many distinct suppliers the optimizer will split this order across, to limit delivery complexity." />
            </Label>
            <Input type="number" value={maxSuppliers} onChange={(e) => setMaxSuppliers(Number(e.target.value))} />
          </div>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} />}
      <div className="flex justify-end">
        <Button
          data-testid="create-order-button"
          size="lg"
          disabled={lines.length === 0 || createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          {createMutation.isPending ? <Spinner label="Creating…" /> : "Create order & compare plans"}
        </Button>
      </div>
    </div>
  );
}
