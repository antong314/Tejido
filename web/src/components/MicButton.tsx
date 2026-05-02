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

// Force a complete EBML cluster to be flushed every TIMESLICE_MS while
// recording. Without this, MediaRecorder only emits one dataavailable
// event at stop() — and short recordings produce a blob with the init
// segment but no clusters, which ffmpeg rejects with "0x00 at pos 36
// invalid as first byte of an EBML number". 250ms is small enough that
// even a fast tap produces a usable file.
const TIMESLICE_MS = 250;

// Reject anything under this duration outright. Below ~600ms we
// observed inconsistent encoder behavior across browsers — even with
// a timeslice, the cluster data can be incomplete. Better to tell the
// user "hold a bit longer" than to send garbage and get a backend error.
const MIN_RECORDING_MS = 600;

// A valid Opus webm with 600ms of audio is comfortably > 3KB. Anything
// under this is almost certainly init-segment-only; reject locally so
// the user gets a fast, accurate error message instead of round-tripping
// to the backend just to be told ffmpeg failed.
const MIN_BLOB_BYTES = 1500;

// Probe the browser for a mime type we know works well end-to-end.
// Order matters: webm/opus is the most reliable across Chrome/Firefox
// and ffmpeg handles it cleanly. Safari falls through to mp4/aac.
// If nothing matches, return "" so MediaRecorder picks the default.
function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

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

    const mime = pickMimeType();
    const recorder = mime
      ? new MediaRecorder(stream, { mimeType: mime })
      : new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      // Stop all tracks so the mic indicator goes away.
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;

      const finalMime = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(chunksRef.current, { type: finalMime });
      chunksRef.current = [];

      // Local sanity check — a webm with only the init segment is ~36
      // bytes; a real recording is always much larger. If we got
      // something tiny, surface a clear "too short" error instead of
      // sending it and getting a generic 422 back.
      if (blob.size < MIN_BLOB_BYTES) {
        setError("Recording was too short. Hold the button for at least a second.");
        setStatus("error");
        return;
      }
      await uploadBlob(blob, finalMime);
    };

    recorderRef.current = recorder;
    streamRef.current = stream;
    startedAtRef.current = Date.now();
    // Pass timeslice so the encoder flushes a complete cluster every
    // 250ms — this is the single biggest fix for "0x00 at pos 36"
    // ffmpeg errors on short recordings.
    recorder.start(TIMESLICE_MS);
    setStatus("recording");
  }

  function stopRecording() {
    const r = recorderRef.current;
    if (!r || r.state === "inactive") return;
    const elapsed = Date.now() - startedAtRef.current;
    if (elapsed < MIN_RECORDING_MS) {
      // Don't honor the stop yet — let the encoder accumulate at least
      // one full cluster's worth of audio. Schedule the real stop for
      // when we hit the floor.
      window.setTimeout(stopRecording, MIN_RECORDING_MS - elapsed);
      return;
    }
    setStatus("uploading");
    // Force a final flush of any in-flight buffer into chunksRef BEFORE
    // stop(). Without this, the trailing audio between the last
    // timeslice tick and the stop() call can land in a partial cluster.
    try {
      r.requestData();
    } catch {
      /* requestData isn't supported in some old browsers — no-op */
    }
    r.stop();
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
