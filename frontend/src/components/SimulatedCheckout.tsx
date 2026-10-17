import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { createPortal } from "react-dom";
import { Building2, CheckCircle2, CreditCard, Lock, Smartphone, X, XCircle } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { formatINR } from "../lib/format";
import type { Payment } from "../lib/types";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input, Label, Select } from "./ui/input";

// Published-style test instruments only. The checkout never accepts real card numbers.
const TEST_CARDS = [
  { value: "Visa •••• 1111", label: "4111 1111 1111 1111 — test card (succeeds)" },
  { value: "Visa •••• 0002", label: "4000 0000 0000 0002 — test card (declines)" },
];
const BANKS = ["HDFC Bank", "State Bank of India", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank"];
type Method = "upi" | "card" | "netbanking";
type Stage = "choose" | "processing" | "done";

interface Receipt { payment: Payment; method: Method; instrument: string }

/** A realistic checkout for demos: method choice, authorisation step and a receipt with
 *  transaction and bank references. It calls the real backend, which records the payment
 *  with the clearly labelled simulated provider. No money moves. */
export function SimulatedCheckout({ orderId, amount, onClose, onPaid }: { orderId: string; amount: number; onClose: () => void; onPaid: () => void }) {
  const [method, setMethod] = useState<Method>("upi");
  const [vpa, setVpa] = useState("success@upi");
  const [card, setCard] = useState(TEST_CARDS[0].value);
  const [bank, setBank] = useState(BANKS[0]);
  const [stage, setStage] = useState<Stage>("choose");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const instrument = method === "upi" ? vpa : method === "card" ? card : bank;

  const pay = useMutation({
    mutationFn: async () => {
      setStage("processing");
      await new Promise((r) => setTimeout(r, 1600)); // authorisation step, as a real gateway shows
      return api.post<Payment>("/api/payments/initiate", { order_id: orderId, method, instrument });
    },
    onSuccess: (payment) => { setReceipt({ payment, method, instrument }); setStage("done"); onPaid(); },
    onError: (e) => { setError(e instanceof ApiError ? e.message : "Payment could not be started"); setStage("choose"); },
  });

  const tabs: { id: Method; label: string; icon: typeof Smartphone }[] = [
    { id: "upi", label: "UPI", icon: Smartphone }, { id: "card", label: "Card", icon: CreditCard }, { id: "netbanking", label: "Net banking", icon: Building2 },
  ];
  const ok = receipt?.payment.status === "success";

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Checkout">
      <div className="absolute inset-0 bg-slate-900/60" onClick={stage === "processing" ? undefined : onClose} />
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900">
        <div className="flex items-start justify-between bg-gradient-to-r from-brand-700 to-brand-500 px-5 py-4 text-white">
          <div>
            <p className="text-xs opacity-80">Stockout Firewall · Order #{orderId.slice(0, 8)}</p>
            <p className="text-2xl font-semibold tabular-nums">{formatINR(amount, true)}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-amber-300 px-1.5 py-0.5 text-[10px] font-bold text-amber-950">TEST MODE</span>
            {stage !== "processing" && <button onClick={onClose} aria-label="Close checkout" className="rounded p-1 hover:bg-white/15"><X className="h-4 w-4" /></button>}
          </div>
        </div>

        {stage === "choose" && (
          <div className="space-y-4 p-5">
            <div className="grid grid-cols-3 gap-2" role="tablist">
              {tabs.map(({ id, label, icon: Icon }) => (
                <button key={id} role="tab" aria-selected={method === id} onClick={() => setMethod(id)}
                  className={cn("flex flex-col items-center gap-1 rounded-lg border px-2 py-2 text-xs font-medium",
                    method === id ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300" : "border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300")}>
                  <Icon className="h-4 w-4" aria-hidden />{label}
                </button>
              ))}
            </div>
            {method === "upi" && (
              <div className="space-y-1">
                <Label htmlFor="sim-vpa">UPI ID</Label>
                <Input id="sim-vpa" value={vpa} onChange={(e) => setVpa(e.target.value)} />
                <p className="text-[11px] text-slate-500">Test IDs: <code>success@upi</code> succeeds, <code>failure@upi</code> declines.</p>
              </div>
            )}
            {method === "card" && (
              <div className="space-y-1">
                <Label htmlFor="sim-card">Test card</Label>
                <Select id="sim-card" value={card} onChange={(e) => setCard(e.target.value)}>
                  {TEST_CARDS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </Select>
                <p className="text-[11px] text-slate-500">Test mode accepts only these test cards; never enter a real card here.</p>
              </div>
            )}
            {method === "netbanking" && (
              <div className="space-y-1">
                <Label htmlFor="sim-bank">Bank</Label>
                <Select id="sim-bank" value={bank} onChange={(e) => setBank(e.target.value)}>{BANKS.map((b) => <option key={b}>{b}</option>)}</Select>
              </div>
            )}
            {error && <p className="text-sm text-rose-600" role="alert">{error}</p>}
            <Button className="w-full" disabled={method === "upi" && !/^[\w.-]+@[\w]+$/.test(vpa)} onClick={() => { setError(null); pay.mutate(); }}>
              <Lock className="h-4 w-4" aria-hidden /> Pay {formatINR(amount, true)}
            </Button>
            <p className="text-center text-[11px] text-slate-500">Simulated gateway — no money moves. Configure Razorpay test keys to use the real checkout.</p>
          </div>
        )}

        {stage === "processing" && (
          <div className="flex flex-col items-center gap-3 p-10" role="status" aria-live="polite">
            <span className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600" />
            <p className="text-sm font-medium">Authorising with {method === "netbanking" ? bank : method === "card" ? "card network" : "UPI app"}…</p>
            <p className="text-xs text-slate-500">Please don't close this window</p>
          </div>
        )}

        {stage === "done" && receipt && (
          <div className="space-y-4 p-5">
            <div className="flex flex-col items-center gap-1 text-center">
              {ok ? <CheckCircle2 className="h-12 w-12 text-emerald-500" aria-hidden /> : <XCircle className="h-12 w-12 text-rose-500" aria-hidden />}
              <p className="text-lg font-semibold">{ok ? "Payment successful" : "Payment declined"}</p>
              <Badge variant="warning">Simulated — no money moved</Badge>
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
              <dt className="text-slate-500">Amount</dt><dd className="text-right font-semibold tabular-nums">{formatINR(receipt.payment.amount, true)}</dd>
              <dt className="text-slate-500">Method</dt><dd className="text-right">{receipt.method.toUpperCase()} · {receipt.instrument}</dd>
              <dt className="text-slate-500">Transaction ID</dt><dd className="text-right font-mono">{receipt.payment.provider_txn_id ?? "—"}</dd>
              <dt className="text-slate-500">Gateway order</dt><dd className="text-right font-mono">{receipt.payment.provider_order_id}</dd>
              <dt className="text-slate-500">Bank reference</dt><dd className="text-right font-mono">{String(receipt.payment.raw_provider_response?.bank_reference ?? "—")}</dd>
              <dt className="text-slate-500">Time</dt><dd className="text-right">{receipt.payment.created_at ? new Date(receipt.payment.created_at).toLocaleString("en-IN") : "—"}</dd>
            </dl>
            {ok ? <Button className="w-full" onClick={onClose}>Done</Button>
              : <Button className="w-full" variant="outline" onClick={() => { setStage("choose"); setReceipt(null); }}>Try another method</Button>}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
