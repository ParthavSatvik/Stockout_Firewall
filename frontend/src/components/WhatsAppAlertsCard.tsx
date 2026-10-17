import { useT } from "../lib/i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { MessageCircle } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Input, Label } from "./ui/input";
import { useToast } from "./ui/toast";

interface Me { phone_e164: string | null; whatsapp_opt_in: boolean }
interface IntegrationStatus { twilio_whatsapp: boolean; whatsapp_inbound_verifiable: boolean }

/** Opt-in for WhatsApp order updates. Messages are sent only with an explicit opt-in. */
export function WhatsAppAlertsCard({ audience }: { audience: "merchant" | "supplier" }) {
  const { t } = useT();
  const qc = useQueryClient();
  const { toast } = useToast();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/auth/me") });
  const status = useQuery({ queryKey: ["integration-status"], queryFn: () => api.get<IntegrationStatus>("/api/integrations/status") });
  const [phone, setPhone] = useState<string | null>(null);
  const [optIn, setOptIn] = useState<boolean | null>(null);
  const phoneValue = phone ?? me.data?.phone_e164 ?? "";
  const optInValue = optIn ?? me.data?.whatsapp_opt_in ?? false;
  const save = useMutation({
    mutationFn: () => api.put<Me>("/api/auth/me/contact", { phone_e164: phoneValue || null, whatsapp_opt_in: optInValue }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); toast({ title: "WhatsApp preference saved", variant: "success" }); },
    onError: (e) => toast({ title: "Not saved", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" }),
  });
  const what = audience === "merchant"
    ? "supplier confirmations, failure alerts with the re-planned cost, delivery updates and payment receipts. You can also order by sending a message or voice note."
    : "new order requests, relay requests and approvals.";

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2"><MessageCircle className="h-4 w-4 text-emerald-600" aria-hidden />{t("wa.title")}</CardTitle>
        {status.data && <Badge variant={status.data.twilio_whatsapp ? "success" : "warning"}>{status.data.twilio_whatsapp ? t("wa.connected") : t("wa.notConfigured")}</Badge>}
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-slate-500 dark:text-slate-400">Get {what}</p>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="space-y-1">
            <Label htmlFor={`wa-${audience}`}>{t("wa.number")}</Label>
            <Input id={`wa-${audience}`} className="w-48" placeholder="+919876543210" inputMode="tel" value={phoneValue} onChange={(e) => setPhone(e.target.value.trim())} />
          </div>
          <label className="flex h-9 items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={optInValue} onChange={(e) => setOptIn(e.target.checked)} />
            {t("wa.agree")}
          </label>
          <Button type="submit" size="sm" disabled={save.isPending}>{t("common.save")}</Button>
        </form>
        {status.data && !status.data.twilio_whatsapp && <p className="text-[11px] text-amber-700 dark:text-amber-400">Your preference is stored, but no messages are sent until Twilio credentials are configured on the server.</p>}
      </CardContent>
    </Card>
  );
}
