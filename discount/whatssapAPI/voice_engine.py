"""
AI Voice Messaging: TTS, cloning, plan guard.
- generate_voice: plan guard, ElevenLabs (stability/similarity, cloned_voice_id) or OpenAI.
- clone_voice: upload sample to ElevenLabs, store voice_id.
- get_preview_audio: returns path to temp file (caller must delete after serve).
"""
import os
import logging
import tempfile
import threading
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# OpenAI voices by gender
OPENAI_VOICE_MALE = "onyx"
OPENAI_VOICE_FEMALE = "nova"
# ElevenLabs: use multilingual v2 for natural Arabic (no foreign accent)
ELEVENLABS_MODEL_MULTILINGUAL_V2 = "eleven_multilingual_v2"
# Default voice IDs (Rachel = female, Adam = male) – used when no gallery/clone selection
ELEVENLABS_VOICE_FEMALE = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_VOICE_MALE = "pNInz6obpgDQGcFmaJgB"

# Voice Gallery: native-friendly voices for Arabic (multilingual_v2 recommended)
VOICE_GALLERY = [
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "label": "Rachel – Professional", "gender": "FEMALE", "tags": ["Multilingual", "High Quality", "Natural"], "native_arabic": True},
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "label": "Adam – Clear & Calm", "gender": "MALE", "tags": ["Multilingual", "High Quality"], "native_arabic": True},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "label": "Bella – Soft & Warm", "gender": "FEMALE", "tags": ["Multilingual", "Natural"], "native_arabic": True},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "label": "Antoni – Friendly", "gender": "MALE", "tags": ["Multilingual", "High Quality"], "native_arabic": False},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli", "label": "Elli – Professional Arabic", "gender": "FEMALE", "tags": ["Multilingual", "High Quality", "Natural"], "native_arabic": True},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "label": "Josh – Confident", "gender": "MALE", "tags": ["Multilingual", "Natural"], "native_arabic": False},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold", "label": "Arnold – Authoritative", "gender": "MALE", "tags": ["Multilingual", "High Quality"], "native_arabic": False},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "label": "Daniel – British", "gender": "MALE", "tags": ["Multilingual", "Natural"], "native_arabic": False},
    {"id": "D38z5RcWu1voky8WS1ja", "name": "Lily", "label": "Lily – French-friendly", "gender": "FEMALE", "tags": ["Multilingual", "French", "Natural"], "native_arabic": False},
    {"id": "flq6f7yk4E4fJM5XTYuZ", "name": "Michael", "label": "Michael – Neutral", "gender": "MALE", "tags": ["Multilingual", "High Quality"], "native_arabic": False},
]


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
    """Convert text to speech using ElevenLabs API. Uses eleven_multilingual_v2 by default for natural Arabic.
    Auth: xi-api-key header. voice_settings: stability, similarity_boost, speed (0.5–1.5).
    """
    raw = (api_key or "").strip() or getattr(settings, "ELEVENLABS_API_KEY", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    key = (raw or "").strip()
    if not key:
        logger.warning("ELEVENLABS_API_KEY not set; skipping ElevenLabs TTS")
        return False
    vid = (voice_id or os.environ.get("ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_FEMALE) or "").strip()
    if not vid:
        logger.warning("ElevenLabs voice_id missing")
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": key}
    model = (model_id or "").strip() or os.environ.get("ELEVENLABS_MODEL_ID", ELEVENLABS_MODEL_MULTILINGUAL_V2)
    payload = {"text": text[:5000], "model_id": model}
    if stability is not None:
        payload["voice_settings"] = payload.get("voice_settings") or {}
        payload["voice_settings"]["stability"] = max(0.0, min(1.0, float(stability)))
    if similarity_boost is not None:
        payload["voice_settings"] = payload.get("voice_settings") or {}
        payload["voice_settings"]["similarity_boost"] = max(0.0, min(1.0, float(similarity_boost)))
    if speed is not None:
        payload["voice_settings"] = payload.get("voice_settings") or {}
        payload["voice_settings"]["speed"] = max(0.5, min(2.0, float(speed)))
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        print(r.json())
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
        return True
    except requests.exceptions.HTTPError as e:
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
    except Exception as e:
        logger.exception("ElevenLabs TTS failed: %s", e)
        return False


# OpenAI TTS only accepts these voice names (not ElevenLabs IDs)
OPENAI_TTS_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}


# ---------------------------------------------------------------------------
# TTS: OpenAI
# ---------------------------------------------------------------------------

def _tts_openai(text, output_path, voice=None, response_format="mp3"):
    """
    Convert text to speech using OpenAI TTS (tts-1).
    voice: alloy, echo, fable, onyx, nova, shimmer (invalid values fall back to alloy).
    response_format: mp3 (default) for unified WhatsApp delivery.
    Returns True if file written.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; skipping OpenAI TTS")
        return False
    raw_voice = (voice or os.environ.get("OPENAI_TTS_VOICE", "alloy")).strip().lower()
    voice = raw_voice if raw_voice in OPENAI_TTS_VOICES else "alloy"
    if raw_voice and raw_voice not in OPENAI_TTS_VOICES:
        logger.debug("OpenAI TTS: voice %r not valid, using 'alloy'", raw_voice)
    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "tts-1",
        "input": text[:4096],
        "voice": voice,
        "response_format": response_format or "mp3",
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
    Uses ElevenLabs (with stability, similarity, cloned_voice_id) or OpenAI.
    Returns path to temporary MP3 file or None on failure.
    """
    if not (text and str(text).strip()):
        return None
    _verify_plan_ai_voice(store_settings)
    return generate_audio_file(text, store_settings)


def generate_audio_file(text, store_settings):
    """
    Generate speech from text. Returns path to temporary MP3 file or None.
    Unified MP3 output for WhatsApp.

    - If persona.provider == 'ELEVENLABS' (or channel voice_provider): ElevenLabs API with eleven_multilingual_v2.
    - If persona.provider == 'OPENAI': OpenAI tts-1 with the persona voice_id (e.g. shimmer, alloy, nova, onyx).
    """
    if not (text and str(text).strip()):
        return None
    text = str(text).strip()
    suffix = ".mp3"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        provider = (getattr(store_settings, "ai_voice_provider", None) or getattr(store_settings, "voice_provider", None) or "ELEVENLABS").strip().upper()
        gender = (getattr(store_settings, "voice_gender", None) or "FEMALE").upper()
        if gender != "MALE":
            gender = "FEMALE"
        stability = getattr(store_settings, "voice_stability", None)
        similarity = getattr(store_settings, "voice_similarity", None)
        speed = getattr(store_settings, "voice_speed", None)
        cloned_id = getattr(store_settings, "cloned_voice_id", None) or None
        if cloned_id:
            cloned_id = (cloned_id or "").strip() or None
        selected_id = getattr(store_settings, "selected_voice_id", None) or None
        if selected_id:
            selected_id = (selected_id or "").strip() or None
        model_id = getattr(store_settings, "elevenlabs_model_id", None) or ELEVENLABS_MODEL_MULTILINGUAL_V2
        ok = False

        if provider == "OPENAI":
            # OpenAI tts-1 with persona voice_id (shimmer, alloy, nova, onyx); output MP3
            openai_voice = selected_id or os.environ.get("OPENAI_TTS_VOICE") or (OPENAI_VOICE_MALE if gender == "MALE" else OPENAI_VOICE_FEMALE)
            ok = _tts_openai(text, path, voice=openai_voice, response_format="mp3")
        else:
            # ELEVENLABS with eleven_multilingual_v2; output MP3
            api_key = getattr(store_settings, "elevenlabs_api_key", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
            voice_id = cloned_id or selected_id or os.environ.get("ELEVENLABS_VOICE_ID") or (ELEVENLABS_VOICE_MALE if gender == "MALE" else ELEVENLABS_VOICE_FEMALE)
            ok = _tts_elevenlabs(text, path, api_key=api_key, voice_id=voice_id, stability=stability, similarity_boost=similarity, model_id=model_id, speed=speed)
            if not ok:
                openai_voice = selected_id or os.environ.get("OPENAI_TTS_VOICE") or (OPENAI_VOICE_MALE if gender == "MALE" else OPENAI_VOICE_FEMALE)
                ok = _tts_openai(text, path, voice=openai_voice, response_format="mp3")
                if ok:
                    logger.info("ElevenLabs failed; used OpenAI TTS fallback (MP3).")

        if ok and os.path.exists(path):
            return path
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return None
    except Exception as e:
        logger.exception("generate_audio_file failed: %s", e)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return None


def generate_voice_response(text, store_settings):
    """Alias for generate_audio_file for backward compatibility."""
    return generate_audio_file(text, store_settings)


def process_and_send_voice(phone_number, text, store_settings, send_callback):
    """
    Generate audio (with plan guard), wait voice_delay_seconds (10–30), then call send_callback.
    send_callback is responsible for sending and deleting the temp file.
    Runs in a background thread so it does not block.
    """
    audio_path = generate_voice(text, store_settings)
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
    default_preview = "مرحباً، أنا مساعدك الذكي، كيف يمكنني مساعدتك اليوم؟"
    text = (text or default_preview).strip()[:500]
    return generate_audio_file(text or default_preview, store_settings)


def generate_voice_sample(voice_id, text, api_key=None, model_id=None, stability=0.5, similarity_boost=0.75, speed=1.0):
    """
    Generate a short sample for the Voice Gallery (specific voice_id + multilingual_v2).
    Returns (path, None) on success or (None, error_message) on failure (caller must delete temp file).
    """
    text = (text or "مرحباً، أنا مساعدك الذكي.").strip()[:500]
    model_id = (model_id or "").strip() or ELEVENLABS_MODEL_MULTILINGUAL_V2
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        ok = _tts_elevenlabs(
            text, path, api_key=api_key, voice_id=voice_id,
            stability=stability, similarity_boost=similarity_boost, model_id=model_id, speed=speed
        )
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
