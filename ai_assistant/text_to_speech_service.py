"""
ElevenLabs TTS (v3) for WhatsApp voice notes.

Generates a temporary MP3 (or OGG when requested), then the WhatsApp Cloud
API path uploads it to Meta `/media` and sends it as a PTT voice note.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Optional

import requests
from django.conf import settings

from discount.services.tts_text import clean_text_for_tts

logger = logging.getLogger(__name__)

ELEVENLABS_MODEL_V3 = "eleven_v3"
ELEVENLABS_MODEL_MULTILINGUAL_V2 = "eleven_multilingual_v2"
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MAX_CHARS = 5000
VOICE_NOTE_MAX_CHARS = 600

ELEVENLABS_VOICE_FEMALE = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_VOICE_MALE = "pNInz6obpgDQGcFmaJgB"

ELEVENLABS_V3_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
}
ELEVENLABS_V2_VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


def _sanitize_api_key(raw: Optional[str]) -> str:
    key = (raw or "").strip()
    lk = key.lower()
    if lk.startswith("bearer "):
        key = key.split(" ", 1)[1].strip()
        lk = key.lower()
    if lk.startswith("xi-api-key"):
        if ":" in key:
            key = key.split(":", 1)[1].strip()
        else:
            parts = key.split()
            key = parts[-1].strip() if parts else key
    if key and " " in key:
        key = key.split()[-1].strip()
    return key


def resolve_elevenlabs_api_key(store_settings=None) -> str:
    raw = ""
    if store_settings is not None:
        raw = getattr(store_settings, "elevenlabs_api_key", None) or ""
    if not (raw or "").strip():
        raw = getattr(settings, "ELEVENLABS_API_KEY", None) or os.environ.get("ELEVENLABS_API_KEY", "")
    return _sanitize_api_key(raw)


def resolve_elevenlabs_voice_id(store_settings=None) -> str:
    cloned = (getattr(store_settings, "cloned_voice_id", None) or "").strip() if store_settings else ""
    selected = (getattr(store_settings, "selected_voice_id", None) or "").strip() if store_settings else ""
    gender = (getattr(store_settings, "voice_gender", None) or "FEMALE").upper() if store_settings else "FEMALE"
    if gender != "MALE":
        gender = "FEMALE"
    return (
        cloned
        or selected
        or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        or (ELEVENLABS_VOICE_MALE if gender == "MALE" else ELEVENLABS_VOICE_FEMALE)
    )


def synthesize_elevenlabs(
    text: str,
    output_path: str,
    *,
    api_key: Optional[str] = None,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
) -> bool:
    """
    Call ElevenLabs Text-to-Speech and write MPEG audio to ``output_path``.

    Prefers the multilingual v3 model (``eleven_v3``). If that model rejects
    the voice or payload, falls back to ``eleven_multilingual_v2``.
    """
    key = _sanitize_api_key(api_key) or resolve_elevenlabs_api_key()
    vid = (voice_id or "").strip() or os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or ELEVENLABS_VOICE_FEMALE
    script = clean_text_for_tts(str(text or ""))[:ELEVENLABS_MAX_CHARS]
    if not key:
        logger.warning("ElevenLabs TTS skipped: API key missing")
        return False
    if not vid:
        logger.warning("ElevenLabs TTS skipped: voice_id missing")
        return False
    if not script:
        logger.warning("ElevenLabs TTS skipped: empty text")
        return False

    preferred = (model_id or "").strip() or ELEVENLABS_MODEL_V3
    models = [preferred]
    if ELEVENLABS_MODEL_V3 not in models:
        models.append(ELEVENLABS_MODEL_V3)
    if ELEVENLABS_MODEL_MULTILINGUAL_V2 not in models:
        models.append(ELEVENLABS_MODEL_MULTILINGUAL_V2)

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key,
    }
    url = ELEVENLABS_TTS_URL.format(voice_id=vid) + "?output_format=mp3_44100_128"

    last_error = None
    for mid in models:
        payload = {
            "text": script,
            "model_id": mid,
            "voice_settings": (
                dict(ELEVENLABS_V3_VOICE_SETTINGS)
                if mid == ELEVENLABS_MODEL_V3
                else dict(ELEVENLABS_V2_VOICE_SETTINGS)
            ),
        }
        try:
            logger.info(
                "ElevenLabs TTS model=%s voice_id=%s chars=%s",
                mid,
                vid,
                len(script),
            )
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code != 200:
                body = (r.text or "")[:800]
                logger.warning("ElevenLabs TTS %s status=%s body=%s", mid, r.status_code, body)
                last_error = r
                if r.status_code == 401:
                    raise ValueError(
                        "ElevenLabs API key is invalid or expired. "
                        "Set a valid key in Channel Settings → Voice Identity."
                    )
                if r.status_code in (400, 404, 422) and mid != models[-1]:
                    continue
                return False
            with open(output_path, "wb") as fh:
                fh.write(r.content)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
            logger.warning("ElevenLabs TTS wrote empty file model=%s", mid)
        except ValueError:
            raise
        except requests.exceptions.Timeout as exc:
            logger.warning("ElevenLabs TTS timed out model=%s: %s", mid, exc)
            last_error = exc
            if mid != models[-1]:
                continue
            return False
        except requests.RequestException as exc:
            logger.warning("ElevenLabs TTS request failed model=%s: %s", mid, exc)
            last_error = exc
            if mid != models[-1]:
                continue
            return False
        except Exception as exc:
            logger.exception("ElevenLabs TTS failed model=%s: %s", mid, exc)
            return False
    if last_error is not None:
        logger.warning("ElevenLabs TTS exhausted models last_error=%s", last_error)
    return False


def generate_temp_speech(text: str, store_settings=None, *, suffix: str = ".mp3") -> Optional[str]:
    """
    Synthesize ``text`` to a temporary audio file.

    Caller must delete the returned path. Returns None on failure.
    """
    script = clean_text_for_tts(str(text or ""))
    if not script:
        return None
    fd, path = tempfile.mkstemp(suffix=suffix or ".mp3")
    os.close(fd)
    try:
        api_key = resolve_elevenlabs_api_key(store_settings)
        voice_id = resolve_elevenlabs_voice_id(store_settings)
        ok = synthesize_elevenlabs(
            script,
            path,
            api_key=api_key,
            voice_id=voice_id,
            model_id=ELEVENLABS_MODEL_V3,
        )
        if ok and os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    except ValueError as exc:
        logger.warning("generate_temp_speech rejected: %s", exc)
    except Exception as exc:
        logger.exception("generate_temp_speech failed: %s", exc)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    return None


def deliver_whatsapp_voice_note(channel, recipient: str, text: str) -> dict[str, Any]:
    """
    Generate ElevenLabs v3 audio, upload it to Meta WhatsApp media, and send
    it as a native voice note (``audio.voice = true``).
    """
    script = clean_text_for_tts(str(text or "").strip())[:VOICE_NOTE_MAX_CHARS]
    if not channel or not (recipient or "").strip():
        return {"status": "error", "success": False, "message": "Channel or recipient missing."}
    if not script:
        return {"status": "error", "success": False, "message": "Voice note text is empty."}

    try:
        from django.core.exceptions import PermissionDenied
        from discount.services.security_check import FEATURE_AI_VOICE, verify_plan_access

        owner = getattr(channel, "owner", None)
        if owner:
            verify_plan_access(owner, FEATURE_AI_VOICE)
    except PermissionDenied:
        return {
            "status": "error",
            "success": False,
            "message": "Voice notes are not included in this plan.",
        }
    except Exception as exc:
        logger.debug("deliver_whatsapp_voice_note plan check: %s", exc)

    audio_path = generate_temp_speech(script, channel)
    if not audio_path:
        return {
            "status": "error",
            "success": False,
            "message": "Could not generate the voice note. Reply with a short text confirmation instead.",
        }

    try:
        from discount.whatssapAPI.process_messages import send_whatsapp_audio_file

        result = send_whatsapp_audio_file(recipient, audio_path, channel) or {}
    except Exception as exc:
        logger.exception("deliver_whatsapp_voice_note send failed: %s", exc)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except OSError:
            pass
        return {
            "status": "error",
            "success": False,
            "message": "Voice note upload/send failed. Reply with a short text instead.",
        }

    if result.get("ok") is False:
        return {
            "status": "error",
            "success": False,
            "message": result.get("error") or "WhatsApp audio send failed.",
        }
    return {
        "status": "success",
        "success": True,
        "message": "Voice note delivered to the customer.",
        "instruction": (
            "SILENT MODE: The WhatsApp voice note is already in the chat. "
            "Do NOT say that you sent a voice note. Keep any text reply to one short line, "
            "or leave it empty."
        ),
    }
