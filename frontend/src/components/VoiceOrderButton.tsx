import { useT } from "../lib/i18n";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { Button } from "./ui/button";

const MAX_SECONDS = 25; // Sarvam's synchronous endpoint is for clips under 30 s

interface TranscribeResponse { transcript: string; language_code: string | null; source: string }

/** Records a short voice order and returns Sarvam's transcript. Never invents text:
 *  if speech-to-text is unavailable the merchant is told to type instead. */
// Browser speech recognition (Chrome/Edge) used only when Sarvam is not configured.
interface BrowserRecognition { lang: string; interimResults: boolean; maxAlternatives: number; start: () => void; stop: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null; onend: (() => void) | null }
type RecognitionCtor = new () => BrowserRecognition;
const SPEECH_LOCALE: Record<string, string> = { en: "en-IN", hi: "hi-IN", kn: "kn-IN", ta: "ta-IN", te: "te-IN", bn: "bn-IN" };

function browserRecognition(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function VoiceOrderButton({ onTranscript }: { onTranscript: (text: string, language: string | null) => void }) {
  const { t, lang } = useT();
  const status = useQuery({ queryKey: ["integration-status"], queryFn: () => api.get<{ sarvam_stt: boolean }>("/api/integrations/status"), staleTime: 60_000 });
  const browserRec = useRef<BrowserRecognition | null>(null);
  const [engine, setEngine] = useState<"sarvam" | "browser" | null>(null);
  const [state, setState] = useState<"idle" | "recording" | "sending">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  function startBrowser(Ctor: RecognitionCtor) {
    const rec = new Ctor();
    rec.lang = SPEECH_LOCALE[lang] ?? "en-IN";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const text = Array.from(e.results).map((r) => r[0]?.transcript ?? "").join(" ").trim();
      if (text) onTranscript(text, rec.lang); else setMessage("No speech was recognised. Try again or type the order.");
    };
    rec.onerror = (e) => setMessage(e.error === "not-allowed" ? "Microphone permission was not granted. Please type the order." : `Speech recognition stopped (${e.error}). Please type the order.`);
    rec.onend = () => setState("idle");
    browserRec.current = rec;
    setEngine("browser");
    setState("recording");
    rec.start();
  }

  async function start() {
    setMessage(null);
    if (status.data && !status.data.sarvam_stt) {
      const Ctor = browserRecognition();
      if (Ctor) return startBrowser(Ctor);
      setMessage("Voice ordering needs Sarvam (server key) or a browser with speech recognition such as Chrome or Edge. Please type the order.");
      return;
    }
    setEngine("sarvam");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMessage("This browser cannot record audio. Please type the order.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: BlobPart[] = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("sending");
        const form = new FormData();
        form.append("audio", new Blob(chunks, { type: rec.mimeType || "audio/webm" }), "order.webm");
        try {
          const resp = await api.upload<TranscribeResponse>("/api/orders/transcribe", form);
          if (!resp.transcript.trim()) setMessage("No speech was recognised. Try again or type the order.");
          else onTranscript(resp.transcript, resp.language_code);
        } catch (err) {
          setMessage(err instanceof ApiError ? err.message : "Transcription failed. Please type the order.");
        } finally {
          setState("idle");
        }
      };
      recorder.current = rec;
      rec.start();
      setState("recording");
      timer.current = window.setTimeout(stop, MAX_SECONDS * 1000);
    } catch {
      setMessage("Microphone permission was not granted. Please type the order.");
    }
  }

  function stop() {
    if (engine === "browser") { browserRec.current?.stop(); return; }
    if (timer.current) window.clearTimeout(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {state === "recording" ? (
        <Button type="button" variant="destructive" onClick={stop}><Square className="h-4 w-4" aria-hidden />{t("new.stop")}</Button>
      ) : (
        <Button type="button" variant="outline" onClick={start} disabled={state === "sending"}>
          <Mic className="h-4 w-4" aria-hidden />{state === "sending" ? t("new.transcribing") : t("new.speak")}
        </Button>
      )}
      {state === "recording" && <span className="text-xs text-rose-600" role="status">{engine === "browser" ? `Listening (${SPEECH_LOCALE[lang]}, browser speech recognition)…` : t("new.recording", { s: MAX_SECONDS })}</span>}
      {message && <span className="text-xs text-amber-700 dark:text-amber-400" role="alert">{message}</span>}
    </div>
  );
}
