import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { Button } from "./ui/button";

const MAX_SECONDS = 25; // Sarvam's synchronous endpoint is for clips under 30 s

interface TranscribeResponse { transcript: string; language_code: string | null; source: string }

/** Records a short voice order and returns Sarvam's transcript. Never invents text:
 *  if speech-to-text is unavailable the merchant is told to type instead. */
export function VoiceOrderButton({ onTranscript }: { onTranscript: (text: string, language: string | null) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "sending">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  async function start() {
    setMessage(null);
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
    if (timer.current) window.clearTimeout(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {state === "recording" ? (
        <Button type="button" variant="destructive" onClick={stop}><Square className="h-4 w-4" aria-hidden />Stop recording</Button>
      ) : (
        <Button type="button" variant="outline" onClick={start} disabled={state === "sending"}>
          <Mic className="h-4 w-4" aria-hidden />{state === "sending" ? "Transcribing with Sarvam…" : "Speak order"}
        </Button>
      )}
      {state === "recording" && <span className="text-xs text-rose-600" role="status">Recording… up to {MAX_SECONDS}s</span>}
      {message && <span className="text-xs text-amber-700 dark:text-amber-400" role="alert">{message}</span>}
    </div>
  );
}
