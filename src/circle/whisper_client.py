"""Local speech-to-text via pywhispercpp (whisper.cpp bindings).

PRD section 5.1 wants no audio leaving the laptop, and PRD section 4.2 lists
voice transcription as a component the bot calls into. We use pywhispercpp so
the only external API we depend on is Anthropic; transcription runs locally.

Telegram voice notes arrive as `.ogg/Opus`. Browser MediaRecorder produces
`.webm/Opus` (Chrome, Firefox) or `.mp4/AAC` (Safari). whisper.cpp wants
16 kHz mono PCM WAV, so we shell out to ffmpeg to convert before
transcription — and ffmpeg handles all of those input formats with the same
command. The model is loaded once at startup (loading is the expensive
step) and reused.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pywhispercpp.model import Model

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    pass


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None


class WhisperTranscriber:
    """Wraps a single loaded whisper.cpp model.

    Methods are async-friendly: the heavy CPU-bound work runs in a thread via
    asyncio.to_thread so the bot's event loop stays responsive.
    """

    def __init__(self, model_name: str, models_dir: str | os.PathLike[str]) -> None:
        models_dir_path = Path(models_dir)
        models_dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(
            "loading whisper model name=%s dir=%s (first run will download weights)",
            model_name,
            models_dir_path,
        )
        # print_progress/print_realtime would spam stdout during the session;
        # silence them so the dashboard remains readable.
        self._model = Model(
            model=model_name,
            models_dir=str(models_dir_path),
            print_progress=False,
            print_realtime=False,
        )
        # WHISPER_THREADS env var wins. Otherwise default to a cgroup-aware
        # count, capped at 4 — whisper.cpp gets diminishing returns past
        # that, and on shared-vCPU hosts os.cpu_count() reports the host's
        # cores (not the fraction the container owns), so a naive default
        # spawns 30+ threads on fractional CPU and thrashes catastrophically.
        env_threads = os.environ.get("WHISPER_THREADS", "").strip()
        if env_threads:
            self._n_threads = max(1, int(env_threads))
        else:
            try:
                available = len(os.sched_getaffinity(0))
            except AttributeError:  # macOS, Windows
                available = os.cpu_count() or 4
            self._n_threads = max(1, min(4, available - 1))

    async def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe an audio file in any format ffmpeg understands.

        Converts to 16 kHz mono PCM WAV (whisper.cpp's expected input)
        before invoking the model. Both `audio_path` and the temporary
        WAV are deleted afterward, even on failure.
        """
        wav_path = audio_path.with_suffix(".wav")
        try:
            await asyncio.to_thread(self._convert_to_wav, audio_path, wav_path)
            return await asyncio.to_thread(self._transcribe_sync, wav_path)
        finally:
            for path in (audio_path, wav_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("failed to clean up %s", path, exc_info=True)

    # Backwards-compat alias for older callers.
    transcribe_ogg = transcribe_audio

    @staticmethod
    def _convert_to_wav(ogg_path: Path, wav_path: Path) -> None:
        # 16 kHz mono PCM s16le is what whisper.cpp expects.
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(ogg_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            raise TranscriptionError(f"ffmpeg failed: {stderr.strip()}") from exc
        except FileNotFoundError as exc:
            raise TranscriptionError(
                "ffmpeg binary not found on PATH (required for voice messages)"
            ) from exc

    def _transcribe_sync(self, wav_path: Path) -> TranscriptionResult:
        detected_lang: str | None = None
        try:
            (lang, _prob), _all_probs = self._model.auto_detect_language(str(wav_path))
            detected_lang = lang
        except Exception:
            # Detection is a nice-to-have; transcription itself may still succeed.
            logger.warning("language auto-detection failed; falling back to whisper auto", exc_info=True)

        try:
            segments = self._model.transcribe(
                str(wav_path),
                n_threads=self._n_threads,
                language=detected_lang or "auto",
            )
        except Exception as exc:
            raise TranscriptionError(f"whisper transcription failed: {exc}") from exc

        text = "".join(seg.text for seg in segments).strip()
        if not text:
            raise TranscriptionError("whisper produced an empty transcript")
        return TranscriptionResult(text=text, language=detected_lang)


def make_temp_audio(suffix: str = ".ogg") -> Path:
    """Create a temp file for an incoming audio blob.

    Defaults to `.ogg` for the Telegram path (which always sends Opus
    in an Ogg container). The web adapter passes the browser's actual
    mime/extension when it can; ffmpeg sniffs the format anyway, but
    a correct extension makes debugging easier.
    """
    fd, name = tempfile.mkstemp(prefix="tejido_voice_", suffix=suffix)
    os.close(fd)
    return Path(name)


# Backwards-compat alias.
make_temp_ogg = make_temp_audio
