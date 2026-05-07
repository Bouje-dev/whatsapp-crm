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
# Whisper-1 prompt budget (~224 tokens); keep aligned with build_whisper_prompt_with_context
WHISPER_PROMPT_MAX_CHARS = 900
DEFAULT_WHISPER_PROMPT = "E-commerce customer. Transcribe exactly as spoken, including any French or English words."

# Router keys (internal) ↔ dictionary lines for Whisper `prompt` biasing (reduces drift, allows code-switching).
WHISPER_DIALECT_MOROCCAN = "moroccan"
WHISPER_DIALECT_GULF = "gulf"
WHISPER_DIALECT_FRENCH = "french"
WHISPER_DIALECT_ENGLISH = "english"
WHISPER_DIALECT_AUTO = "auto"


def get_whisper_prompt(dialect_setting: str) -> str:
    """
    Dictionary router: return a short vocabulary/context string for Whisper `prompt` based on dialect/market.

    dialect_setting: 'Moroccan', 'Saudi', 'Gulf', 'French', 'English', 'Auto' (case-insensitive),
    or internal keys: moroccan, gulf, french, english, auto.
    """
    if not dialect_setting or not str(dialect_setting).strip():
        dialect_setting = WHISPER_DIALECT_AUTO
    d = str(dialect_setting).strip().lower().replace("-", "_")
    if d in ("moroccan", "maghreb", "north_africa", "ar_ma", "ma"):
        return "مرحباً، واش متوفر؟ prix, livraison, commande, شكراً، produit, adresse."
    if d in ("saudi", "gulf", "gcc", "ar_sa", "sa"):
        return "مرحباً طال عمرك، كم السعر؟ متوفر، ابشر، التوصيل، الرياض، شكراً."
    if d in ("french", "fr", "fr_fr"):
        return "commande, livraison, prix, adresse, bonjour, merci, produit."
    if d in ("english", "en", "en_us"):
        return "order, delivery, price, address, shipping, thank you, product."
    # Auto / unknown: bias toward Moroccan–French code-switching (common in MENA storefronts).
    return "مرحباً، واش متوفر؟ prix, livraison, commande, شكراً، produit, adresse."


# Known Whisper Arabic/YouTube-style hallucinations on low-volume audio — never treat as customer intent.
WHISPER_HALLUCINATION_PHRASES = [
    "الاشتراك في القناة",
    "المترجم",
    "شكرا للمشاهدة",
    "ترجمة",
    "Amara.org",
    "Subtitles",
    "Subtitles by",
    "Transcribe the audio exactly as spoken",
    "transcribe the audio",
    "Thank you for watching",
    "like and subscribe",
]

# Returned when audio is unintelligible so caller can show localized fallback
STT_UNINTELLIGIBLE = "__STT_UNINTELLIGIBLE__"

# Map node/channel language hint to Whisper optional `language` API param + base hint.
# Arabic dialects (MA/Gulf/AUTO): language=None → Whisper auto-detect; steering is via prompt only.
WHISPER_LANGUAGE_PROMPTS = {
    "AR-MA": {
        "language": None,
        "prompt": "دارجة مغربية مع كلمات فرنسية أو إنجليزية للتجارة: انسخ النص كما يُسمع بالضبط.",
    },
    "AR-SA": {
        "language": None,
        "prompt": "لهجة خليجية، عملاء تجارة إلكترونية: انسخ الكلام كما هو دون تصريف.",
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
        "prompt": DEFAULT_WHISPER_PROMPT,
    },
}


def get_openai_api_key():
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


def _normalize_voice_language_hint(hint):
    """Map node_language / voice_language to AR-MA, AR-SA, FR-FR, EN-US, or AUTO."""
    if not hint or not (hint or "").strip():
        return "AUTO"
    h = (hint or "").strip().upper().replace("-", "_")
    if (
        h in ("AR_MA", "ARMA", "AR_TN", "AR_DZ")
        or h.startswith(("AR_MA", "AR_TN", "AR_DZ"))
        or "MAGHREB" in h
        or "MAGHRIB" in h
    ):
        return "AR-MA"
    if h in ("AR_SA", "ARSA", "SA") or h.startswith("AR_SA"):
        return "AR-SA"
    if "GCC" in h or h.startswith("AR_GCC") or h.startswith("AR_AE") or h.startswith("AR_QA"):
        return "AR-SA"
    if h in ("FR_FR", "FRFR") or h.startswith("FR"):
        return "FR-FR"
    if h in ("EN_US", "ENUS") or h.startswith("EN_"):
        return "EN-US"
    return "AUTO"


def _router_key_for_whisper(normalized_hint: str, channel=None, sender=None) -> str:
    """
    Map normalized hint (+ optional phone) to get_whisper_prompt dialect key:
    moroccan | gulf | french | english | auto
    """
    if normalized_hint == "FR-FR":
        return WHISPER_DIALECT_FRENCH
    if normalized_hint == "EN-US":
        return WHISPER_DIALECT_ENGLISH
    if normalized_hint == "AR-MA":
        return WHISPER_DIALECT_MOROCCAN
    if normalized_hint == "AR-SA":
        return WHISPER_DIALECT_GULF
    # AUTO: infer Gulf vs Moroccan from customer phone when possible
    if normalized_hint == "AUTO" and channel and sender:
        try:
            from ai_assistant.services import infer_market_from_phone

            m = infer_market_from_phone(sender or "")
            if m in ("SA", "GCC"):
                return WHISPER_DIALECT_GULF
            if m == "MA":
                return WHISPER_DIALECT_MOROCCAN
        except Exception:
            pass
    return WHISPER_DIALECT_AUTO


def get_whisper_config(voice_language_hint):
    """
    Return (language, prompt) for Whisper API.
    voice_language_hint: from node.node_language or channel.voice_language (e.g. AR_MA, FR_FR, AUTO).
    Arabic routes use language=None for auto-detection (prompt carries dialect bias).
    """
    key = _normalize_voice_language_hint(voice_language_hint)
    cfg = WHISPER_LANGUAGE_PROMPTS.get(key) or WHISPER_LANGUAGE_PROMPTS["AUTO"]
    return (cfg.get("language"), cfg.get("prompt") or DEFAULT_WHISPER_PROMPT)


def build_whisper_prompt_with_context(voice_language_hint, last_ai_message_bodies, channel=None, sender=None):
    """
    Merge recent assistant messages into Whisper's prompt so vocabulary matches the live conversation.
    OpenAI Whisper `prompt` guides style/vocabulary (Darija + French mix, Gulf Arabic, etc.).
    Does not set Whisper `language` — returned second value is legacy compatibility (always None for STT steering).

    Returns:
        (full_prompt_string, None)
    """
    normalized = _normalize_voice_language_hint(voice_language_hint)
    router_key = _router_key_for_whisper(normalized, channel=channel, sender=sender)
    vocab_line = get_whisper_prompt(router_key)
    _, base_prompt = get_whisper_config(voice_language_hint)

    ctx_chunks = []
    for t in (last_ai_message_bodies or [])[-2:]:
        t = (t or "").strip()
        if t and t != "[media]":
            ctx_chunks.append(t[:400])
    if ctx_chunks:
        ctx = "Context: " + " | ".join(ctx_chunks) + ". "
    else:
        ctx = ""

    if router_key == WHISPER_DIALECT_GULF:
        tail = "المتحدث عميل خليجي؛ انسخ الدارجة أو الفصحى كما تُسمع."
    elif router_key == WHISPER_DIALECT_FRENCH:
        tail = "Français e-commerce."
    elif router_key == WHISPER_DIALECT_ENGLISH:
        tail = "English e-commerce speech."
    else:
        tail = "دارجة مغربية أو عربية مع فرنسية للتجارة؛ انسخ كل الكلمات كما نُطقت."

    full = (ctx + vocab_line + " " + (base_prompt or "") + " " + tail).strip()
    if len(full) > WHISPER_PROMPT_MAX_CHARS:
        full = full[:WHISPER_PROMPT_MAX_CHARS]
    return full, None


def is_whisper_hallucination(text):
    """
    True if transcription is empty or matches known Whisper subtitle/artifact hallucinations
    (low-volume audio / Arabic ASR drift). Caller should not pass this text to LLM or sentinel.
    """
    if text is None:
        return True
    t = (text or "").strip()
    if not t:
        return True
    t_lower = t.lower()
    for phrase in WHISPER_HALLUCINATION_PHRASES:
        p = (phrase or "").strip()
        if not p:
            continue
        if p.lower() in t_lower or p in t:
            return True
    return False


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
        language: Optional ISO-639-1 code for Whisper. Omitted for Arabic/Maghreb/Gulf/AUTO so the model
            can auto-detect and handle code-switched (Darija+French) speech; use "fr"/"en" when hint is French/English.
        voice_language_hint: Node/channel hint: AR_MA, AR_SA, FR_FR, EN_US, AUTO. Drives optional language + default prompt.

    Returns:
        Transcribed text string, STT_UNINTELLIGIBLE if unintelligible, or None on hard failure.
    """
    if not media_content:
        return None
    api_key = get_openai_api_key()
    if not api_key:
        logger.warning("stt_service: OPENAI_API_KEY not set")
        return None

    # Always derive language from hint when provided, even if prompt is passed in (context injection).
    if voice_language_hint is not None:
        lang_from_hint, prompt_from_hint = get_whisper_config(voice_language_hint)
        if language is None:
            language = lang_from_hint
        if prompt is None:
            prompt = prompt_from_hint
    if prompt is None:
        prompt = DEFAULT_WHISPER_PROMPT
    prompt = (prompt or "").strip()
    if len(prompt) > WHISPER_PROMPT_MAX_CHARS:
        prompt = prompt[:WHISPER_PROMPT_MAX_CHARS]

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
            # temperature=0: deterministic decoding, fewer hallucinations on quiet audio
            data = {"model": model, "temperature": 0}
            if prompt:
                data["prompt"] = prompt
            # Do not send language for Arabic/auto routes (None): enables multilingual code-switching.
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
