import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";

interface Props {
  sessionId: string;
  participantId: string;
  disabled: boolean;
  onTranscribed: () => void;
}

// Press once to start recording, press again to stop and upload.
// Browser MediaRecorder produces .webm/Opus on Chrome/Firefox and
// .mp4/AAC on Safari — ffmpeg on the backend handles all of them.

type Status = "idle" | "asking" | "recording" | "uploading" | "error";

export function MicButton({ sessionId, participantId, disabled, onTranscribed }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<number>(0);
  const tickRef = useRef<number | null>(null);

  // Ticker for the recording duration display.
  useEffect(() => {
    if (status !== "recording") {
      if (tickRef.current !== null) {
        window.clearInterval(tickRef.current);
        tickRef.current = null;
      }
      setElapsedSec(0);
      return;
    }
    tickRef.current = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 250);
    return () => {
      if (tickRef.current !== null) window.clearInterval(tickRef.current);
    };
  }, [status]);

  async function startRecording() {
    setError(null);
    setStatus("asking");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      console.warn("getUserMedia failed:", e);
      setError(
        "Mic access was blocked. Allow mic permission in your browser, or type instead.",
      );
      setStatus("error");
      return;
    }

    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      // Stop all tracks so the mic indicator goes away.
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;

      const mime = recorder.mimeType || "audio/webm";
      const blob = new Blob(chunksRef.current, { type: mime });
      chunksRef.current = [];
      await uploadBlob(blob, mime);
    };

    recorderRef.current = recorder;
    streamRef.current = stream;
    startedAtRef.current = Date.now();
    recorder.start();
    setStatus("recording");
  }

  function stopRecording() {
    const r = recorderRef.current;
    if (r && r.state !== "inactive") {
      setStatus("uploading");
      r.stop();
    }
  }

  async function uploadBlob(blob: Blob, mime: string) {
    const ext = mime.includes("webm")
      ? "webm"
      : mime.includes("mp4") || mime.includes("aac")
        ? "m4a"
        : mime.includes("ogg")
          ? "ogg"
          : "audio";
    const fd = new FormData();
    fd.append("file", blob, `recording.${ext}`);

    try {
      const r = await fetch(`/api/s/${sessionId}/p/${participantId}/audio`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) {
        let msg = "Couldn't transcribe that. Try again or type instead.";
        try {
          const body = await r.json();
          if (body?.detail?.error) msg = body.detail.error;
        } catch {
          /* not json */
        }
        throw new ApiError(r.status, "audio_failed", msg);
      }
      onTranscribed();
      setStatus("idle");
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : "Couldn't reach the server. Try again?";
      setError(msg);
      setStatus("error");
    }
  }

  function handleClick() {
    if (disabled) return;
    if (status === "recording") {
      stopRecording();
    } else if (status === "idle" || status === "error") {
      startRecording();
    }
  }

  const recording = status === "recording";
  const busy = status === "asking" || status === "uploading";

  return (
    <div className="flex flex-col items-center">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || busy}
        title={recording ? "Stop and send" : "Hold a voice message"}
        className={[
          "flex h-10 w-10 items-center justify-center rounded-full transition",
          recording
            ? "bg-red-600 text-white animate-pulse"
            : "border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50",
          (disabled || busy) && "opacity-50 cursor-not-allowed",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-label={recording ? "Stop recording" : "Start recording"}
      >
        {/* Microphone glyph */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      </button>
      {recording && (
        <div className="mt-1 text-xs text-red-600 tabular-nums">
          {String(Math.floor(elapsedSec / 60)).padStart(2, "0")}:
          {String(elapsedSec % 60).padStart(2, "0")}
        </div>
      )}
      {busy && status === "uploading" && (
        <div className="mt-1 text-xs text-neutral-500">Sending…</div>
      )}
      {status === "error" && error && (
        <div className="mt-1 max-w-[200px] text-xs text-red-600 text-center">
          {error}
        </div>
      )}
    </div>
  );
}
