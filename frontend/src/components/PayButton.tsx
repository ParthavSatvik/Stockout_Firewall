import { useT } from "../lib/i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Payment } from "../lib/types";
import { Badge, StatusBadge } from "./ui/badge";
import { Button } from "./ui/button";
import { useToast } from "./ui/toast";

interface PayConfig { provider: "razorpay" | "simulated"; mode: string; key_id: string | null }
interface RzpOrder { payment_id: string; razorpay_order_id: string; key_id: string; amount: number; currency: string; name: string; description: string; mode: string }
interface RzpSuccess { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }
interface RazorpayInstance { open: () => void; on: (event: string, cb: (r: { error?: { description?: string } }) => void) => void }
declare global { interface Window { Razorpay?: new (options: object) => RazorpayInstance } }

function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Razorpay Checkout"));
    document.body.appendChild(s);
  });
}

/** Pays the approved plan. With Razorpay configured the amount comes from a server-created
 *  order and the result counts only after the server verifies the signature; otherwise the
 *  clearly labelled simulated provider is used. */
export function PayButton({ orderId }: { orderId: string }) {
  const { t } = useT();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [result, setResult] = useState<{ status: string; simulated: boolean; mode?: string } | null>(null);
  const config = useQuery({ queryKey: ["payment-config"], queryFn: () => api.get<PayConfig>("/api/payments/config") });
  const fail = (e: unknown) => toast({ title: "Payment not completed", description: e instanceof Error ? e.message : "Request failed", variant: "error" });

  const simulated = useMutation({
    mutationFn: () => api.post<Payment>("/api/payments/initiate", { order_id: orderId }),
    onSuccess: (p) => { setResult({ status: p.status, simulated: true }); qc.invalidateQueries({ queryKey: ["order", orderId] }); },
    onError: fail,
  });

  const razorpay = useMutation({
    mutationFn: async () => {
      const order = await api.post<RzpOrder>("/api/payments/razorpay/order", { order_id: orderId });
      await loadCheckout();
      return new Promise<{ status: string; mode: string }>((resolve, reject) => {
        const rzp = new window.Razorpay!({
          key: order.key_id, amount: order.amount, currency: order.currency, name: order.name,
          description: order.description, order_id: order.razorpay_order_id,
          handler: async (resp: RzpSuccess) => {
            try {
              const v = await api.post<{ status: string }>("/api/payments/razorpay/verify", { payment_id: order.payment_id, ...resp });
              resolve({ status: v.status, mode: order.mode });
            } catch (e) { reject(e); }
          },
          modal: { ondismiss: () => reject(new Error("Checkout closed before payment")) },
        });
        rzp.on("payment.failed", (r) => reject(new Error(r.error?.description ?? "Payment failed")));
        rzp.open();
      });
    },
    onSuccess: (r) => {
      setResult({ status: r.status, simulated: false, mode: r.mode });
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      toast({ title: "Payment verified", description: `Razorpay ${r.mode} mode, signature checked by the server.`, variant: "success" });
    },
    onError: (e) => fail(e instanceof ApiError ? new Error(e.message) : e),
  });

  const live = config.data?.provider === "razorpay";
  const busy = simulated.isPending || razorpay.isPending;
  return (
    <div className="space-y-2">
      <Button onClick={() => (live ? razorpay.mutate() : simulated.mutate())} disabled={busy || config.isPending}>
        {busy ? t("order.processing") : live ? `${t("order.payRazorpay")}${config.data?.mode === "test" ? " (test)" : ""}` : t("order.paySimulated")}
      </Button>
      {result && (
        <p className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          {t("order.paymentStatus")} <StatusBadge status={result.status} />
          {result.simulated ? <Badge variant="info">Simulated — no money moved</Badge> : <Badge variant={result.mode === "live" ? "success" : "info"}>Razorpay {result.mode}</Badge>}
        </p>
      )}
    </div>
  );
}
