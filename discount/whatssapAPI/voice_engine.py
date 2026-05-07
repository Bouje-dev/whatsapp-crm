"""
AI Voice Messaging: TTS, cloning, plan guard.
- generate_voice: plan guard, ElevenLabs (fixed multilingual_v2 + voice_settings, cloned_voice_id) or OpenAI.
- clone_voice: upload sample to ElevenLabs, store voice_id.
- get_preview_audio: returns path to temp file (caller must delete after serve).
"""
import os
import logging
import tempfile
import threading
import requests
from django.conf import settings

from discount.services.tts_text import clean_text_for_tts

logger = logging.getLogger(__name__)

# OpenAI voices by gender
OPENAI_VOICE_MALE = "onyx"
OPENAI_VOICE_FEMALE = "nova"
# ElevenLabs: use multilingual v2 for natural Arabic (no foreign accent)
ELEVENLABS_MODEL_MULTILINGUAL_V2 = "eleven_multilingual_v2"
# Fixed TTS payload for Arabic / Moroccan Darija quality (non-English); do not drift from API contract.
ELEVENLABS_TTS_VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}
# Default voice IDs (Rachel = female, Adam = male) – used when no gallery/clone selection
ELEVENLABS_VOICE_FEMALE = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_VOICE_MALE = "pNInz6obpgDQGcFmaJgB"

# Voice Gallery voices: managed in Django Admin (discount.models.VoiceGalleryEntry).
# Static MP3 previews: static/audio/voice-previews/ — see discount/services/voice_catalog.py.


def get_store_settings(channel=None):
    """
    Return an object with .plan = 'PREMIUM' | 'BASIC'.
    Prefer channel.owner subscription if available, else env STORE_PLAN, else 'BASIC'.
    """
    plan = "BASIC"
    if channel and hasattr(channel, "owner") and channel.owner:
        user = channel.owner
        if hasattr(user, "subscription") and user.subscription and hasattr(user.subscription, "plan"):
            name = getattr(user.subscription.plan, "name", None) or ""
            if "premium" in str(name).lower():
                plan = "PREMIUM"
    plan_env = os.environ.get("STORE_PLAN", "").strip().upper()
    if plan_env in ("PREMIUM", "BASIC"):
        plan = plan_env
    return type("StoreSettings", (), {"plan": plan})()


# ---------------------------------------------------------------------------
# TTS: ElevenLabs
# ---------------------------------------------------------------------------

def _tts_elevenlabs(text, output_path, api_key=None, voice_id=None, stability=None, similarity_boost=None, model_id=None, speed=None):
    """Convert text to speech using ElevenLabs API.

    Always sends ``model_id`` = ``eleven_multilingual_v2`` and ``voice_settings`` =
    :data:`ELEVENLABS_TTS_VOICE_SETTINGS` (tuned for Arabic / dialect quality).
    Legacy kwargs ``stability``, ``similarity_boost``, ``model_id``, ``speed`` are ignored
    so all call sites share one consistent payload.

    Auth: ``xi-api-key`` header.
    """
    raw = (api_key or "").strip() or getattr(settings, "ELEVENLABS_API_KEY", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    key = (raw or "").strip()
    # Tolerate common copy/paste formats like:
    # - "Bearer <key>"
    # - "xi-api-key: <key>"
    # - "<key>" with accidental trailing/leading whitespace
    lk = (key or "").lower()
    if lk.startswith("bearer "):
        key = key.split(" ", 1)[1].strip()
        lk = key.lower()
    if lk.startswith("xi-api-key"):
        if ":" in key:
            key = key.split(":", 1)[1].strip()
        else:
            parts = key.split()
            key = parts[-1].strip() if parts else key
        lk = key.lower()
    if key and " " in key:
        # If someone pasted a full header line, keep the last token as the raw key.
        parts = key.split()
        key = parts[-1].strip() if parts else key
    if not key:
        logger.warning("ELEVENLABS_API_KEY not set; skipping ElevenLabs TTS")
        return False
    # Voice ID note:
    # Replace `ELEVENLABS_VOICE_ID` in `.env` with your Custom Cloned Voice ID
    # for the best localized accent (unless Channel Settings provides `voice_id`).
    vid = (voice_id or os.environ.get("ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_FEMALE) or "").strip()
    if not vid:
        logger.warning("ElevenLabs voice_id missing")
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": key}
    payload = {
        "text": text[:5000],
        "model_id": ELEVENLABS_MODEL_MULTILINGUAL_V2,
        "voice_settings": dict(ELEVENLABS_TTS_VOICE_SETTINGS),
    }
    try:
        # Debug metadata (avoid printing full key)
        try:
            logger.warning(
                "ElevenLabs TTS debug: voice_id=%s model=%s xi-api-key len=%s last4=%s",
                vid,
                ELEVENLABS_MODEL_MULTILINGUAL_V2,
                len(key),
                key[-4:],
            )
        except Exception:
            pass
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        # ElevenLabs TTS returns audio on success (not JSON). For failures, it usually returns JSON.
        if r.status_code != 200:
            try:
                print("ElevenLabs TTS response (json):", r.json())
            except Exception:
                try:
                    print("ElevenLabs TTS response (text):", (r.text or "")[:2000])
                except Exception:
                    pass
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
        return True
    except requests.exceptions.Timeout as e:
        logger.warning("ElevenLabs TTS request timed out: %s", e)
        return False
    except requests.exceptions.HTTPError as e:
        if e.response is not None:
            try:
                print(
                    "ElevenLabs TTS HTTPError status=",
                    e.response.status_code,
                    "body(json)=",
                    e.response.json(),
                )
            except Exception:
                try:
                    print(
                        "ElevenLabs TTS HTTPError status=",
                        e.response.status_code,
                        "body(text)=",
                        (e.response.text or "")[:2000],
                    )
                except Exception:
                    pass
        if e.response is not None and e.response.status_code == 401:
            try:
                body = e.response.json() if e.response.content else {}
                detail = (body.get("detail") or body.get("message") or {}).get("message", "") or str(body)[:200]
            except Exception:
                detail = ""
            msg = "ElevenLabs API key is invalid or expired. Please set a valid key in Channel Settings → Voice Identity → ElevenLabs API Key."
            if detail and "invalid" in detail.lower():
                msg = "ElevenLabs API key is invalid or expired. Get a key from elevenlabs.io → Profile → API Keys. Then set it in Channel Settings → Voice Identity."
            raise ValueError(msg)
        logger.exception("ElevenLabs TTS failed: %s", e)
        return False
    except requests.exceptions.RequestException as e:
        logger.warning("ElevenLabs TTS request failed: %s", e)
        return False
    except Exception as e:
        logger.exception("ElevenLabs TTS failed: %s", e)
        return False


# OpenAI TTS only accepts these voice names (not ElevenLabs IDs)
OPENAI_TTS_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}


def _resolve_effective_tts_provider(store_settings):
    """
    Prefer Voice Gallery row provider when selected_voice_id matches a gallery entry;
    otherwise fall back to channel ai_voice_provider / voice_provider.
    """
    selected = (getattr(store_settings, "selected_voice_id", None) or "").strip()
    if selected:
        try:
            from discount.models import VoiceGalleryEntry

            row = VoiceGalleryEntry.objects.filter(elevenlabs_voice_id=selected).only("provider").first()
            if row and getattr(row, "provider", None):
                return str(row.provider).strip().upper()
        except Exception as e:
            logger.debug("resolve TTS provider from gallery: %s", e)
    return (
        getattr(store_settings, "ai_voice_provider", None)
        or getattr(store_settings, "voice_provider", None)
        or "ELEVENLABS"
    ).strip().upper()


# ---------------------------------------------------------------------------
# TTS: OpenAI
# ---------------------------------------------------------------------------

def _tts_openai(text, output_path, voice=None, response_format="mp3"):
    """
    Convert text to speech using OpenAI TTS (tts-1) via the official SDK (audio.speech.create).
    voice: alloy, echo, fable, onyx, nova, shimmer (invalid values fall back to alloy).
    response_format: mp3 (default) for unified WhatsApp delivery.
    Returns True if file written.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; skipping OpenAI TTS")
        return False
    raw_voice = (voice or os.environ.get("OPENAI_TTS_VOICE", "alloy")).strip().lower()
    voice_name = raw_voice if raw_voice in OPENAI_TTS_VOICES else "alloy"
    if raw_voice and raw_voice not in OPENAI_TTS_VOICES:
        logger.debug("OpenAI TTS: voice %r not valid, using 'alloy'", raw_voice)
    fmt = (response_format or "mp3").strip().lower()
    if fmt not in ("mp3", "opus", "aac", "flac", "wav", "pcm"):
        fmt = "mp3"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        speech = client.audio.speech.create(
            model="tts-1",
            voice=voice_name,
            input=text[:4096],
            response_format=fmt,
        )
        if hasattr(speech, "stream_to_file"):
            speech.stream_to_file(output_path)
        else:
            data = getattr(speech, "content", None)
            if data is None and hasattr(speech, "read"):
                data = speech.read()
            with open(output_path, "wb") as f:
                f.write(data if isinstance(data, (bytes, bytearray)) else b"")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.warning("OpenAI TTS SDK failed (%s), falling back to HTTP: %s", type(e).__name__, e)
    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "tts-1",
        "input": text[:4096],
        "voice": voice_name,
        "response_format": fmt,
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        if not r.ok:
            body = (r.text or "")[:500]
            logger.warning(
                "OpenAI TTS %s: %s %s",
                r.status_code,
                getattr(r.reason, "phrase", None) or "Error",
                body,
            )
            return False
        with open(output_path, "wb") as f:
            f.write(r.content)
        return True
    except requests.RequestException as e:
        logger.warning("OpenAI TTS request failed: %s", e)
        return False
    except Exception as e:
        logger.exception("OpenAI TTS failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Plan guard (backend re-verify before every API call)
# ---------------------------------------------------------------------------

def _verify_plan_ai_voice(store_settings):
    """Raise PermissionDenied if store's plan does not allow ai_voice."""
    store = getattr(store_settings, "owner", None)
    if not store:
        return
    from discount.services.security_check import verify_plan_access, FEATURE_AI_VOICE
    verify_plan_access(store, FEATURE_AI_VOICE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_voice(text, store_settings):
    """
    Generate speech from text. Plan guard: verifies store.plan.can_use_ai_voice.
    Uses ElevenLabs (fixed multilingual_v2 + voice_settings, cloned_voice_id) or OpenAI.
    Returns path to temporary MP3 file or None on failure.
    """
    if not (text and str(text).strip()):
        return None
    _verify_plan_ai_voice(store_settings)
    path, _ = generate_audio_file_with_text_fallback(text, store_settings)
    return path


def generate_audio_file_with_text_fallback(text, store_settings):
    """
    Generate speech from text. Returns (mp3_path, text_fallback).

    - On success: (path, None).
    - On TTS failure (ElevenLabs error/timeout/4xx/5xx, or OpenAI TTS failure): (None, cleaned_script).
      Caller should send text_fallback as WhatsApp text (e.g. after remove_arabic_diacritics).
      Does NOT call OpenAI Chat again — only uses the script already produced by the sales agent.

    When ElevenLabs fails we no longer fall back to OpenAI TTS; we return the script for text delivery instead.
    """
    if not (text and str(text).strip()):
        return (None, None)
    raw_clean = clean_text_for_tts(str(text))
    if not raw_clean:
        return (None, None)
    text = raw_clean
    suffix = ".mp3"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        gender = (getattr(store_settings, "voice_gender", None) or "FEMALE").upper()
        if gender != "MALE":
            gender = "FEMALE"
        cloned_id = getattr(store_settings, "cloned_voice_id", None) or None
        if cloned_id:
            cloned_id = (cloned_id or "").strip() or None
        selected_id = getattr(store_settings, "selected_voice_id", None) or None
        if selected_id:
            selected_id = (selected_id or "").strip() or None
        ok = False

        provider = _resolve_effective_tts_provider(store_settings)
        if provider == "OPENAI":
            openai_voice = selected_id or os.environ.get("OPENAI_TTS_VOICE") or (OPENAI_VOICE_MALE if gender == "MALE" else OPENAI_VOICE_FEMALE)
            ok = _tts_openai(text, path, voice=openai_voice, response_format="opus")
        else:
            api_key = getattr(store_settings, "elevenlabs_api_key", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
            voice_id = cloned_id or selected_id or os.environ.get("ELEVENLABS_VOICE_ID") or (ELEVENLABS_VOICE_MALE if gender == "MALE" else ELEVENLABS_VOICE_FEMALE)
            try:
                ok = _tts_elevenlabs(text, path, api_key=api_key, voice_id=voice_id)
            except ValueError as e:
                logger.warning("ElevenLabs TTS rejected: %s", e)
                ok = False

        if ok and os.path.exists(path):
            return (path, None)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        if provider == "ELEVENLABS":
            logger.warning(
                "ElevenLabs TTS failed. Successfully fell back to sending the conversational audio-script as a text message."
            )
        else:
            logger.warning(
                "OpenAI TTS failed. Successfully fell back to sending the conversational audio-script as a text message."
            )
        return (None, text)
    except Exception as e:
        logger.exception("generate_audio_file_with_text_fallback failed: %s", e)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        logger.warning(
            "TTS failed. Successfully fell back to sending the conversational audio-script as a text message."
        )
        return (None, text)


def generate_audio_file(text, store_settings):
    """
    Generate speech from text. Returns path to temporary MP3 file or None.
    Unified MP3 output for WhatsApp.

    - If persona.provider == 'ELEVENLABS' (or channel voice_provider): ElevenLabs API with
      ``eleven_multilingual_v2`` and :data:`ELEVENLABS_TTS_VOICE_SETTINGS` (channel DB fields for
      stability/similarity are not applied to the TTS payload).
    - If persona.provider == 'OPENAI': OpenAI tts-1 with the persona voice_id (e.g. shimmer, alloy, nova, onyx).

    On failure, returns None (no OpenAI TTS fallback after ElevenLabs — use
    :func:`generate_audio_file_with_text_fallback` when a text fallback is required).
    """
    path, _ = generate_audio_file_with_text_fallback(text, store_settings)
    return path


def generate_voice_response(text, store_settings):
    """Alias for generate_audio_file for backward compatibility."""
    return generate_audio_file(text, store_settings)


def process_and_send_voice(phone_number, text, store_settings, send_callback, text_fallback_callback=None):
    """
    Generate audio (with plan guard), wait voice_delay_seconds (10–30), then call send_callback.
    send_callback is responsible for sending and deleting the temp file.
    Runs in a background thread so it does not block.

    If TTS fails (e.g. ElevenLabs error), text_fallback_callback is invoked with
    (phone_number, cleaned_script_text, store_settings) so the caller can send WhatsApp text
    (typically after remove_arabic_diacritics). No second OpenAI Chat call.
    """
    if not (text and str(text).strip()):
        return
    try:
        _verify_plan_ai_voice(store_settings)
    except Exception:
        return
    audio_path, text_fb = generate_audio_file_with_text_fallback(text, store_settings)
    if text_fb and not audio_path:
        if text_fallback_callback:
            text_fallback_callback(phone_number, text_fb, store_settings)
        return
    if not audio_path:
        return
    delay = getattr(store_settings, "voice_delay_seconds", 20)
    delay = max(10, min(30, int(delay)))

    def _delayed():
        try:
            send_callback(phone_number, audio_path, store_settings)
        except Exception as e:
            logger.exception("process_and_send_voice callback failed: %s", e)
            try:
                if audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)
            except OSError:
                pass

    t = threading.Timer(delay, _delayed)
    t.daemon = True
    t.start()


# ---------------------------------------------------------------------------
# Voice cloning (ElevenLabs Add Voice)
# ---------------------------------------------------------------------------

def clone_voice(store, file, voice_name="Cloned Voice"):
    """
    Upload audio sample to ElevenLabs Add Voice API and save returned voice_id to store (channel).
    store must have .owner with plan allowing cloning, and elevenlabs_api_key or env ELEVENLABS_API_KEY.
    Returns (voice_id, None) on success or (None, error_message).
    """
    from discount.services.security_check import verify_plan_access, FEATURE_VOICE_CLONING
    store_user = getattr(store, "owner", None) or store
    verify_plan_access(store_user, FEATURE_VOICE_CLONING)
    api_key = getattr(store, "elevenlabs_api_key", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return None, "ElevenLabs API key not set"
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": api_key}
    try:
        if hasattr(file, "read"):
            files = {"files": (getattr(file, "name", "sample.mp3"), file.read(), "audio/mpeg")}
        else:
            with open(file, "rb") as f:
                files = {"files": (os.path.basename(file), f.read(), "audio/mpeg")}
        data = {"name": voice_name}
        r = requests.post(url, headers=headers, data=data, files=files, timeout=60)
        r.raise_for_status()
        out = r.json()
        voice_id = out.get("voice_id")
        if not voice_id:
            return None, "No voice_id in response"
        if hasattr(store, "cloned_voice_id"):
            store.cloned_voice_id = voice_id
            store.save(update_fields=["cloned_voice_id"])
        return voice_id, None
    except requests.exceptions.HTTPError as e:
        if e.response is not None:
            try:
                print(
                    "ElevenLabs clone_voice HTTPError status=",
                    e.response.status_code,
                    "body(json)=",
                    e.response.json(),
                )
            except Exception:
                try:
                    print(
                        "ElevenLabs clone_voice HTTPError status=",
                        e.response.status_code,
                        "body(text)=",
                        (e.response.text or "")[:2000],
                    )
                except Exception:
                    pass
        msg = e.response.text if e.response else str(e)
        logger.exception("ElevenLabs clone_voice failed: %s", msg)
        return None, msg or str(e)
    except Exception as e:
        logger.exception("clone_voice failed: %s", e)
        return None, str(e)


def get_preview_audio(store_settings, text=None):
    """
    Generate a short preview audio with current store settings. No plan guard (preview only).
    Returns path to temporary MP3 file; caller must delete after serving.
    """
    default_preview ="مرحبا كيف اساعدك "
    text = clean_text_for_tts((text or default_preview).strip())[:500] or default_preview.strip()
    return generate_audio_file(text, store_settings)


def generate_voice_sample(voice_id, text, api_key=None, model_id=None, stability=0.5, similarity_boost=0.75, speed=1.0):
    """
    Generate a short sample for the Voice Gallery (specific ``voice_id``).
    Uses the same fixed ``eleven_multilingual_v2`` + :data:`ELEVENLABS_TTS_VOICE_SETTINGS` as production TTS.
    ``model_id`` / ``stability`` / etc. are kept for call compatibility but ignored.

    Returns (path, None) on success or (None, error_message) on failure (caller must delete temp file).
    """
    text = clean_text_for_tts((text or "مرحبا كيف اساعدك ").strip())[:500]
    if not text:
        text = "مرحبا كيف اساعدك "
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        ok = _tts_elevenlabs(text, path, api_key=api_key, voice_id=voice_id)
        if ok and os.path.exists(path):
            return (path, None)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return (None, "Could not generate sample.")
    except ValueError as e:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return (None, str(e))
    except Exception as e:
        logger.exception("generate_voice_sample failed: %s", e)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return (None, str(e) or "Could not generate sample.")
