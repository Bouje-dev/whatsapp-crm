"""
Speech-to-Text service for incoming WhatsApp voice/audio messages.
Uses OpenAI Whisper with dynamic language/prompt from AI Node or channel.
Converts OGG/Opus to WAV/MP3 for maximum compatibility. Optional GPT cleanup (Language Harmonizer).
"""
import logging
import tempfile
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_WHISPER_PROMPT = "This is a Moroccan/Arabic customer talking about e-commerce orders."

# Returned when audio is unintelligible so caller can show localized fallback
STT_UNINTELLIGIBLE = "__STT_UNINTELLIGIBLE__"

# Map node/channel language hint to Whisper language code and prompt
WHISPER_LANGUAGE_PROMPTS = {
    "AR-MA": {
        "language": "ar",
        "prompt": "هذا زبون مغربي يتحدث بالدارجة، قد يستعمل كلمات فرنسية مثل 'commande', 'livraison', 'prix'. انسخ الكلام كما هو بالعربي.",
    },
    "AR_MA": {
        "language": "ar",
        "prompt": "هذا زبون مغربي يتحدث بالدارجة، قد يستعمل كلمات فرنسية مثل 'commande', 'livraison', 'prix'. انسخ الكلام كما هو بالعربي.",
    },
    "FR-FR": {
        "language": "fr",
        "prompt": "Client e-commerce parlant français. Transcris exactement : commande, livraison, prix, adresse.",
    },
    "FR_FR": {
        "language": "fr",
        "prompt": "Client e-commerce parlant français. Transcris exactement : commande, livraison, prix, adresse.",
    },
    "EN-US": {"language": "en", "prompt": "E-commerce customer speaking English. Transcribe exactly as spoken."},
    "EN_US": {"language": "en", "prompt": "E-commerce customer speaking English. Transcribe exactly as spoken."},
    "AUTO": {
        "language": None,
        "prompt": "The user might speak Arabic, French, or English. Transcribe the audio exactly as spoken.",
    },
}


def get_openai_api_key():
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


def _normalize_voice_language_hint(hint):
    """Map node_language / voice_language to a key we support (AR-MA, FR-FR, EN-US, AUTO)."""
    if not hint or not (hint or "").strip():
        return "AUTO"
    h = (hint or "").strip().upper().replace("-", "_")
    if h in ("AR_MA", "AR-MA", "ARMA"):
        return "AR-MA"
    if h in ("FR_FR", "FR-FR", "FRFR"):
        return "FR-FR"
    if h in ("EN_US", "EN-US", "ENUS"):
        return "EN-US"
    return "AUTO"


def get_whisper_config(voice_language_hint):
    """
    Return (language, prompt) for Whisper API.
    voice_language_hint: from node.node_language or channel.voice_language (e.g. AR_MA, FR_FR, AUTO).
    """
    key = _normalize_voice_language_hint(voice_language_hint)
    cfg = WHISPER_LANGUAGE_PROMPTS.get(key) or WHISPER_LANGUAGE_PROMPTS["AUTO"]
    return (cfg.get("language"), cfg.get("prompt") or DEFAULT_WHISPER_PROMPT)


def _convert_audio_to_wav_or_mp3(media_content, original_suffix=".ogg"):
    """
    Convert OGG/Opus to WAV or MP3 for Whisper compatibility. Uses pydub if available.
    Returns path to converted file (caller must delete), or original path if conversion skipped/failed.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.debug("pydub not installed; sending original audio to Whisper")
        return None

    tmp_in = None
    tmp_out = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix)
        tmp_in.write(media_content)
        tmp_in.close()
        seg = AudioSegment.from_file(tmp_in.name, format=original_suffix.lstrip(".") or "ogg")
        tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_out.close()
        seg.export(tmp_out.name, format="mp3", bitrate="128k")
        return tmp_out.name
    except Exception as e:
        logger.warning("Audio conversion failed: %s", e)
        if tmp_out and os.path.exists(tmp_out.name):
            try:
                os.unlink(tmp_out.name)
            except OSError:
                pass
        return None
    finally:
        if tmp_in and os.path.exists(tmp_in.name):
            try:
                os.unlink(tmp_in.name)
            except OSError:
                pass


def transcribe_audio(media_content, prompt=None, model="whisper-1", language=None, voice_language_hint=None):
    """
    Transcribe audio bytes using OpenAI Whisper.

    Args:
        media_content: bytes of the audio file (e.g. OGG/Opus from WhatsApp).
        prompt: Optional override context prompt. If None and voice_language_hint is set, uses get_whisper_config.
        model: Whisper model (default whisper-1).
        language: Optional Whisper language code (e.g. "ar", "fr"). If None and voice_language_hint set, derived from hint.
        voice_language_hint: Node/channel hint: AR_MA, FR_FR, EN_US, AUTO. Drives language + prompt when prompt/language not given.

    Returns:
        Transcribed text string, STT_UNINTELLIGIBLE if unintelligible, or None on hard failure.
    """
    if not media_content:
        return None
    api_key = get_openai_api_key()
    if not api_key:
        logger.warning("stt_service: OPENAI_API_KEY not set")
        return None

    if voice_language_hint is not None and prompt is None:
        lang_from_hint, prompt_from_hint = get_whisper_config(voice_language_hint)
        if language is None:
            language = lang_from_hint
        if prompt is None:
            prompt = prompt_from_hint
    if prompt is None:
        prompt = DEFAULT_WHISPER_PROMPT
    prompt = (prompt or "").strip()
    if len(prompt) > 500:
        prompt = prompt[:500]

    # Prefer converted format for compatibility
    converted_path = _convert_audio_to_wav_or_mp3(media_content, ".ogg")
    if converted_path:
        path_to_use = converted_path
        mime = "audio/mpeg"
        fname = "audio.mp3"
    else:
        path_to_use = None
        tmp_orig = None
        try:
            tmp_orig = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
            tmp_orig.write(media_content)
            tmp_orig.close()
            path_to_use = tmp_orig.name
            mime = "audio/ogg"
            fname = "audio.ogg"
        except Exception as e:
            logger.warning("stt_service temp file: %s", e)
            if tmp_orig and os.path.exists(tmp_orig.name):
                try:
                    os.unlink(tmp_orig.name)
                except OSError:
                    pass
            return None

    cleanup_paths = [path_to_use]
    if converted_path and converted_path != path_to_use:
        cleanup_paths.append(converted_path)

    try:
        with open(path_to_use, "rb") as f:
            files = {"file": (fname, f, mime)}
            data = {"model": model}
            if prompt:
                data["prompt"] = prompt
            if language:
                data["language"] = language
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.post(WHISPER_API_URL, files=files, data=data, headers=headers, timeout=30)

        if resp.status_code != 200:
            logger.warning("Whisper API error %s: %s", resp.status_code, (resp.text or "")[:300])
            return None

        out = resp.json()
        text = (out.get("text") or "").strip()
        if not text:
            return STT_UNINTELLIGIBLE
        return text
    except requests.exceptions.Timeout:
        logger.warning("Whisper API timeout")
        return None
    except Exception as e:
        logger.exception("transcribe_audio: %s", e)
        return None
    finally:
        for p in cleanup_paths:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning("stt_service cleanup %s: %s", p, e)


def clean_transcription(raw_text, target_language):
    """
    Language Harmonizer: fix obvious transcription errors and make text readable for the AI Sales Agent.
    Does NOT translate; keeps the customer's language as-is.

    Args:
        raw_text: Raw Whisper output.
        target_language: Store primary language (e.g. "AR-MA", "FR-FR", "Arabic", "French") for context.

    Returns:
        Cleaned text string, or raw_text on failure.
    """
    if not raw_text or not (raw_text or "").strip():
        return raw_text or ""
    if raw_text == STT_UNINTELLIGIBLE:
        return raw_text

    api_key = get_openai_api_key()
    if not api_key:
        return raw_text

    lang_label = target_language or "the customer's language"
    if isinstance(lang_label, str) and len(lang_label) > 60:
        lang_label = lang_label[:60]

    instruction = (
        f"You are a linguistic expert. You received this raw transcription: '{raw_text}'. "
        f"The store's primary language is '{lang_label}'. "
        "Correct any obvious transcription errors. "
        "If the text is in a different language, KEEP IT as is (do not translate), but make it readable. "
        "Your output will be used by an AI Sales Agent, so ensure the intent is clear. "
        "Reply with ONLY the corrected text, no explanation."
    )

    url = getattr(settings, "OPENAI_CHAT_URL", None) or "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": instruction}],
        "max_tokens": 500,
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.warning("clean_transcription API %s: %s", resp.status_code, (resp.text or "")[:200])
            return raw_text
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = (choice.get("message", {}).get("content") or "").strip()
        return content if content else raw_text
    except Exception as e:
        logger.warning("clean_transcription: %s", e)
        return raw_text
