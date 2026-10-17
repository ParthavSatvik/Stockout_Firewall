import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { CheckCheck, Send } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

interface ThreadMessage { direction: "in" | "out"; kind: string; body: string; status: "queued" | "sending" | "sent" | "failed" | "skipped" | "simulated"; detail: string; at: string }
interface Thread { messages: ThreadMessage[]; twilio_configured: boolean; phone: string | null; opted_in: boolean; simulator_available: boolean }

const STATUS_TEXT: Record<ThreadMessage["status"], string> = {
  sent: "delivered to Twilio", failed: "send failed", skipped: "not sent", queued: "queued", sending: "sending", simulated: "simulator",
};

/** Phone-style view of every WhatsApp message for this user, with its true delivery status.
 *  Merchants in demo mode can also send messages through the same order logic as the
 *  Twilio webhook; those are clearly marked as simulator traffic. */
export function WhatsAppThread() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const thread = useQuery({ queryKey: ["wa-thread"], queryFn: () => api.get<Thread>("/api/whatsapp/thread"), refetchInterval: 8000 });
  const send = useMutation({
    mutationFn: () => api.post<{ reply: string }>("/api/whatsapp/simulate", { text }),
    onSuccess: () => { setText(""); setError(null); ["wa-thread", "orders", "dashboard-summary"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not send"),
  });
  const count = thread.data?.messages.length ?? 0;
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [count]);
  if (!thread.data) return null;
  const { messages, simulator_available, twilio_configured } = thread.data;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
      <div className="flex items-center justify-between bg-emerald-700 px-3 py-2 text-white">
        <span className="text-sm font-semibold">Stockout Firewall</span>
        <span className="text-[10px] opacity-90">{twilio_configured ? "WhatsApp via Twilio" : "Preview — Twilio not configured"}</span>
      </div>
      <div className="max-h-80 space-y-1.5 overflow-y-auto bg-[#efeae2] p-3 dark:bg-slate-950" aria-live="polite">
        {messages.length === 0 && <p className="py-6 text-center text-xs text-slate-500">No messages yet. Order updates will appear here.</p>}
        {messages.map((m, i) => (
          <div key={i} className={cn("flex", m.direction === "in" ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[85%] rounded-lg px-2.5 py-1.5 text-sm shadow-sm",
              m.direction === "in" ? "bg-[#d9fdd3] text-slate-900" : "bg-white text-slate-900 dark:bg-slate-800 dark:text-slate-100")}>
              <p className="whitespace-pre-wrap break-words">{m.body.replace(/^Stockout Firewall: /, "")}</p>
              <p className="mt-0.5 flex items-center justify-end gap-1 text-[10px] text-slate-500">
                {new Date(m.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                {m.direction === "out" && (
                  <span title={m.detail || STATUS_TEXT[m.status]} className={cn(m.status === "sent" ? "text-sky-600" : m.status === "failed" ? "text-rose-600" : "text-amber-700")}>
                    {m.status === "sent" ? <CheckCheck className="inline h-3 w-3" aria-label="sent" /> : `· ${STATUS_TEXT[m.status]}`}
                  </span>
                )}
              </p>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      {simulator_available && (
        <form className="flex gap-2 border-t border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.mutate(); }}>
          <Input aria-label="Message (simulator)" placeholder="Try: 25 kg sakkare  ·  then: YES" value={text} onChange={(e) => setText(e.target.value)} />
          <Button type="submit" size="sm" disabled={!text.trim() || send.isPending} aria-label="Send"><Send className="h-4 w-4" aria-hidden /></Button>
        </form>
      )}
      {simulator_available && <p className="bg-white px-2 pb-2 text-[10px] text-slate-500 dark:bg-slate-900">Demo simulator: runs the same order logic as real WhatsApp messages, but nothing is sent through WhatsApp.</p>}
      {error && <p className="bg-white px-2 pb-2 text-xs text-rose-600 dark:bg-slate-900" role="alert">{error}</p>}
    </div>
  );
}
