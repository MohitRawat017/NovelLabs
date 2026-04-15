"""
Local TTS provider abstraction.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import httpx
import numpy as np
import soundfile as sf

from ..config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_BASE_URL,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_OUTPUT_FORMAT,
    ELEVENLABS_TIMEOUT,
    ELEVENLABS_VOICE_ID,
    QWEN_TTS_API_STYLE,
    QWEN_TTS_BASE_URL,
    QWEN_TTS_LANGUAGE,
    QWEN_TTS_MODEL,
    QWEN_TTS_TIMEOUT,
    SUPPORTED_TTS_PROVIDERS,
    TTS_DEVICE,
    TTS_PROVIDER,
    TTS_VOICE,
)

logger = logging.getLogger(__name__)

ENGLISH_VOICES = {
    "American English (Female)": [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    ],
    "American English (Male)": [
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa",
    ],
    "British English (Female)": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    ],
    "British English (Male)": [
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ],
}


class TTSProvider(ABC):
    sample_rate = 24000
    supports_voice_cloning = False

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        profile: Optional[dict] = None,
    ) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Dict[str, object]:
        raise NotImplementedError

    def list_voices(self) -> Dict[str, list[str]]:
        return ENGLISH_VOICES

    def list_voice_choices(self) -> list[dict]:
        voices = []
        for group, group_voices in self.list_voices().items():
            for voice in group_voices:
                voices.append({"id": voice, "label": voice, "group": group})
        return voices

    def transcribe_reference_audio(self, audio_bytes: bytes, filename: str) -> Optional[str]:
        return None


class KokoroProvider(TTSProvider):
    def __init__(self):
        try:
            import torch
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro dependencies are not installed. Install requirements for local TTS."
            ) from exc

        self._torch = torch
        self.device = self._resolve_device()
        self.default_voice = TTS_VOICE
        self._pipeline = KPipeline(repo_id="hexgrad/Kokoro-82M", lang_code="a", device=self.device)
        self._lock = threading.Lock()  # KPipeline holds CUDA state and is NOT thread-safe
        logger.info("Loaded Kokoro provider on %s", self.device)

    def _resolve_device(self) -> str:
        if TTS_DEVICE == "cpu":
            return "cpu"
        if TTS_DEVICE == "cuda":
            if not self._torch.cuda.is_available():
                raise RuntimeError("TTS_DEVICE=cuda but CUDA is not available")
            return "cuda"
        return "cuda" if self._torch.cuda.is_available() else "cpu"

    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        profile: Optional[dict] = None,
    ) -> np.ndarray:
        with self._lock:
            chunks = []
            for _, _, audio in self._pipeline(text, voice=voice or self.default_voice):
                if isinstance(audio, self._torch.Tensor):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))

            if not chunks:
                raise RuntimeError("Kokoro returned no audio chunks")

            if len(chunks) == 1:
                return chunks[0]
            return np.concatenate(chunks)

    def health(self) -> Dict[str, object]:
        gpu_name: Optional[str] = None
        gpu_available = self._torch.cuda.is_available()
        if gpu_available:
            gpu_name = self._torch.cuda.get_device_name(0)

        return {
            "provider": "kokoro",
            "available": True,
            "device": self.device,
            "gpu_available": gpu_available,
            "gpu_name": gpu_name,
            "default_voice": self.default_voice,
            "sample_rate": self.sample_rate,
        }


class Qwen3Provider(TTSProvider):
    supports_voice_cloning = True

    def __init__(self):
        self.base_url = QWEN_TTS_BASE_URL
        self.model = QWEN_TTS_MODEL
        self.api_style = QWEN_TTS_API_STYLE
        self.default_voice = "alloy"
        self.default_language = QWEN_TTS_LANGUAGE
        self.timeout = httpx.Timeout(QWEN_TTS_TIMEOUT)
        self.sample_rate = 24000  # Updated by _decode_audio when actual server rate is known

    def _decode_audio(self, audio_bytes: bytes) -> np.ndarray:
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
        self.sample_rate = sample_rate
        if isinstance(audio, np.ndarray) and audio.ndim > 1:
            audio = audio.mean(axis=1)
        return np.asarray(audio, dtype=np.float32)

    def _decode_demo_stream(self, response: httpx.Response) -> np.ndarray:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type and response.text.lstrip().startswith("data:") is False:
            return self._decode_audio(response.content)

        chunks: list[np.ndarray] = []
        errors: list[str] = []

        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue

            payload_text = line[5:].strip()
            if not payload_text:
                continue

            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue

            event_type = payload.get("type")
            if event_type == "chunk":
                audio_b64 = payload.get("audio_b64")
                if not audio_b64:
                    continue
                chunk_bytes = base64.b64decode(audio_b64)
                chunks.append(self._decode_audio(chunk_bytes))
            elif event_type == "error":
                message = payload.get("message") or payload.get("detail") or "Unknown Qwen3 demo server error"
                errors.append(message)
            elif event_type == "done":
                break

        if errors:
            raise RuntimeError(f"Qwen3 demo stream failed: {' | '.join(errors)}")
        if not chunks:
            raise RuntimeError("Qwen3 demo stream returned no audio chunks")
        if len(chunks) == 1:
            return chunks[0]
        return np.concatenate(chunks)

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(f"{context}: {detail or exc}") from exc

    def _get_demo_status(self) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/status")
        self._raise_for_status(response, "Qwen3 service status check failed")
        return response.json()

    def _require_demo_voice_clone_support(self) -> dict:
        status = self._get_demo_status()
        model_type = str(status.get("model_type") or "").strip().lower()
        if model_type == "custom_voice":
            raise RuntimeError(
                "The running Qwen3 demo server is using a CustomVoice model, which does not support "
                "reference-audio voice cloning in this app. Start a Base model instead, for example: "
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
            )
        return status

    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        profile: Optional[dict] = None,
    ) -> np.ndarray:
        if self.api_style == "openai":
            payload = {
                "model": self.model,
                "input": text,
                "voice": (profile or {}).get("voice_name") or voice or self.default_voice,
                "response_format": "wav",
                "speed": speed,
            }
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/v1/audio/speech", json=payload)
            self._raise_for_status(response, "Qwen3 speech synthesis failed")
            return self._decode_audio(response.content)

        if not profile or not profile.get("ref_audio_path"):
            raise RuntimeError("Qwen3 demo mode requires a saved voice profile with reference audio")

        self._require_demo_voice_clone_support()

        ref_audio_path = Path(profile["ref_audio_path"])
        if not ref_audio_path.exists():
            raise RuntimeError(f"Saved Qwen3 reference audio not found: {ref_audio_path}")

        form = {
            "text": text,
            "language": profile.get("language") or self.default_language,
            "mode": "voice_clone",
            "ref_text": profile.get("ref_text") or "",
            "speaker": profile.get("voice_name") or "",
            "xvec_only": "true",
        }

        with ref_audio_path.open("rb") as handle:
            files = {
                "ref_audio": (ref_audio_path.name, handle, "audio/wav"),
            }
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/generate/stream", data=form, files=files)

        self._raise_for_status(response, "Qwen3 speech synthesis failed")
        return self._decode_demo_stream(response)

    def health(self) -> Dict[str, object]:
        try:
            if self.api_style == "demo":
                status = self._get_demo_status()
                return {
                    "provider": "qwen3",
                    "available": bool(status.get("loaded")),
                    "service_style": self.api_style,
                    "base_url": self.base_url,
                    "model": status.get("model") or self.model,
                    "loading": status.get("loading", False),
                    "supports_voice_cloning": True,
                    "sample_rate": self.sample_rate,
                    "speakers": status.get("speakers", []),
                    "preset_refs": status.get("preset_refs", []),
                    "gpu_available": True,
                    "gpu_name": "Managed by local Qwen3 service",
                    "device": "cuda",
                }

            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}/")
            available = response.status_code < 500
            return {
                "provider": "qwen3",
                "available": available,
                "service_style": self.api_style,
                "base_url": self.base_url,
                "model": self.model,
                "supports_voice_cloning": False,
                "sample_rate": self.sample_rate,
                "gpu_available": True,
                "gpu_name": "Managed by local Qwen3 service",
                "device": "cuda",
            }
        except Exception as exc:
            return {
                "provider": "qwen3",
                "available": False,
                "service_style": self.api_style,
                "base_url": self.base_url,
                "model": self.model,
                "supports_voice_cloning": self.api_style == "demo",
                "sample_rate": self.sample_rate,
                "gpu_available": True,
                "gpu_name": None,
                "device": "cuda",
                "error": str(exc),
            }

    def list_voices(self) -> Dict[str, list[str]]:
        if self.api_style == "demo":
            try:
                status = self._get_demo_status()
                groups: Dict[str, list[str]] = {}
                if status.get("speakers"):
                    groups["Qwen3 Speakers"] = [str(item) for item in status["speakers"]]
                if status.get("preset_refs"):
                    groups["Qwen3 Presets"] = [str(item["id"]) for item in status["preset_refs"]]
                if groups:
                    return groups
            except Exception:
                pass
            return {"Qwen3 Voice Clone": ["novel-default"]}

        return {"Qwen3 Voices": [self.default_voice]}

    def transcribe_reference_audio(self, audio_bytes: bytes, filename: str) -> Optional[str]:
        if self.api_style != "demo":
            return None

        files = {
            "audio": (filename, io.BytesIO(audio_bytes), "audio/wav"),
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/transcribe", files=files)
        self._raise_for_status(response, "Qwen3 reference transcription failed")
        payload = response.json()
        return payload.get("text")


class ElevenLabsProvider(TTSProvider):
    def __init__(self):
        self.base_url = ELEVENLABS_BASE_URL
        self.api_key = ELEVENLABS_API_KEY
        self.model = ELEVENLABS_MODEL_ID
        self.output_format = ELEVENLABS_OUTPUT_FORMAT
        self.timeout = httpx.Timeout(ELEVENLABS_TIMEOUT)
        self.default_voice = ELEVENLABS_VOICE_ID
        self.sample_rate = self._sample_rate_from_output_format(self.output_format)

        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    @staticmethod
    def _sample_rate_from_output_format(output_format: str) -> int:
        parts = (output_format or "").split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 24000

    def _headers(self) -> dict:
        return {
            "xi-api-key": self.api_key,
            "Accept": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(f"{context}: {detail or exc}") from exc

    def _list_voice_records(self) -> list[dict]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v2/voices",
                headers=self._headers(),
                params={"page_size": 100, "include_total_count": "false"},
            )
        self._raise_for_status(response, "ElevenLabs voice listing failed")
        payload = response.json()
        return payload.get("voices", []) or []

    def _resolve_voice_id(self, voice: str) -> str:
        candidate = (voice or self.default_voice or "").strip()
        if candidate:
            return candidate

        voices = self._list_voice_records()
        if voices:
            voice_id = str(voices[0].get("voice_id") or "").strip()
            if voice_id:
                return voice_id

        raise RuntimeError(
            "No ElevenLabs voice is configured. Choose an ElevenLabs voice in the app or set ELEVENLABS_VOICE_ID."
        )

    def _decode_audio(self, audio_bytes: bytes) -> np.ndarray:
        if self.output_format.startswith("pcm_"):
            if len(audio_bytes) % 2 != 0:
                raise RuntimeError("ElevenLabs PCM payload had an unexpected byte length")
            audio = np.frombuffer(audio_bytes, dtype="<i2").astype(np.float32) / 32768.0
            return np.asarray(audio, dtype=np.float32)

        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
        self.sample_rate = sample_rate
        if isinstance(audio, np.ndarray) and audio.ndim > 1:
            audio = audio.mean(axis=1)
        return np.asarray(audio, dtype=np.float32)

    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        profile: Optional[dict] = None,
    ) -> np.ndarray:
        voice_id = self._resolve_voice_id(voice)
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "speed": speed,
            },
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/text-to-speech/{voice_id}",
                headers=self._headers(),
                params={"output_format": self.output_format},
                json=payload,
            )
        self._raise_for_status(response, "ElevenLabs speech synthesis failed")
        return self._decode_audio(response.content)

    def health(self) -> Dict[str, object]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v2/voices",
                    headers=self._headers(),
                    params={"page_size": 1, "include_total_count": "false"},
                )
            self._raise_for_status(response, "ElevenLabs health check failed")
            return {
                "provider": "elevenlabs",
                "available": True,
                "base_url": self.base_url,
                "model": self.model,
                "default_voice": self.default_voice or None,
                "sample_rate": self.sample_rate,
                "output_format": self.output_format,
                "supports_voice_cloning": False,
                "gpu_available": False,
                "gpu_name": None,
                "device": "cloud",
            }
        except Exception as exc:
            return {
                "provider": "elevenlabs",
                "available": False,
                "base_url": self.base_url,
                "model": self.model,
                "default_voice": self.default_voice or None,
                "sample_rate": self.sample_rate,
                "output_format": self.output_format,
                "supports_voice_cloning": False,
                "gpu_available": False,
                "gpu_name": None,
                "device": "cloud",
                "error": str(exc),
            }

    def list_voices(self) -> Dict[str, list[str]]:
        records = self._list_voice_records()
        groups: Dict[str, list[str]] = {}
        for record in records:
            voice_id = str(record.get("voice_id") or "").strip()
            if not voice_id:
                continue
            category = str(record.get("category") or "other").strip().title()
            group_name = f"ElevenLabs {category}"
            groups.setdefault(group_name, []).append(voice_id)

        if groups:
            return groups
        return {"ElevenLabs Voices": [self.default_voice]} if self.default_voice else {"ElevenLabs Voices": []}

    def list_voice_choices(self) -> list[dict]:
        records = self._list_voice_records()
        voices = []
        for record in records:
            voice_id = str(record.get("voice_id") or "").strip()
            if not voice_id:
                continue
            name = str(record.get("name") or voice_id).strip()
            category = str(record.get("category") or "other").strip().title()
            voices.append(
                {
                    "id": voice_id,
                    "label": f"{name} ({voice_id[:8]})",
                    "name": name,
                    "group": f"ElevenLabs {category}",
                }
            )
        return voices


@lru_cache(maxsize=8)
def get_tts_provider(provider_name: Optional[str] = None) -> TTSProvider:
    resolved_provider = (provider_name or TTS_PROVIDER).strip().lower()
    if resolved_provider not in SUPPORTED_TTS_PROVIDERS:
        raise RuntimeError(f"Unsupported TTS provider: {resolved_provider}")
    if resolved_provider == "kokoro":
        return KokoroProvider()
    if resolved_provider == "qwen3":
        return Qwen3Provider()
    if resolved_provider == "elevenlabs":
        return ElevenLabsProvider()
    raise RuntimeError(f"Unsupported TTS provider: {resolved_provider}")
