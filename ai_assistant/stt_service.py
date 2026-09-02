"""
Speech-to-Text service for incoming WhatsApp voice/audio messages.
Uses OpenAI transcription APIs (gpt-4o-mini-transcribe with whisper-1 fallback).
Converts OGG/Opus to mono 16 kHz MP3, rejects emoji/noise hallucinations, optional GPT cleanup.
"""
import logging
import os
import re
import tempfile

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
# Keep prompts short — long sales replies in the Whisper prompt pollute decoding.
WHISPER_PROMPT_MAX_CHARS = 400
DEFAULT_WHISPER_PROMPT = (
    "E-commerce customer voice note. Transcribe exactly as spoken, "
    "including any French or English words. Do not invent text."
)

# Prefer full gpt-4o-transcribe for dialect accuracy (Darija / Maghrebi).
# Fallbacks: mini → whisper-1. Override with OPENAI_STT_MODEL.
DEFAULT_STT_MODEL = "gpt-4o-transcribe"
FALLBACK_STT_MODELS = ("gpt-4o-mini-transcribe", "whisper-1")
MIN_AUDIO_DURATION_MS = 400
MIN_MEANINGFUL_LETTERS = 2

# Router keys (internal) ↔ dictionary lines for Whisper `prompt` biasing.
WHISPER_DIALECT_MOROCCAN = "moroccan"
WHISPER_DIALECT_GULF = "gulf"
WHISPER_DIALECT_FRENCH = "french"
WHISPER_DIALECT_ENGLISH = "english"
WHISPER_DIALECT_AUTO = "auto"


def get_whisper_prompt(dialect_setting: str) -> str:
    """
    Dictionary router: short vocabulary/context string for Whisper `prompt`.

    dialect_setting: 'Moroccan', 'Saudi', 'Gulf', 'French', 'English', 'Auto'
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
    return "مرحباً، واش متوفر؟ prix, livraison, commande, شكراً، produit, adresse."


# Known Whisper Arabic/YouTube-style hallucinations on low-volume audio.
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
    "Thanks for watching",
    "Subscribe to",
    "www.",
    "http://",
    "https://",
]

# Speaker / music symbols Whisper invents on silence / noise (your "Heard: 🔊" bug).
_STT_NOISE_SYMBOLS = frozenset(
    "🔊🔉🔈🎤🎙♪♫🎵🎶🎼🔔🔕…·•▪▫●○◆◇■□▲▼►◄※☆★♥♡❤💥✨"
)

# Returned when audio is unintelligible so caller can show localized fallback
STT_UNINTELLIGIBLE = "__STT_UNINTELLIGIBLE__"

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


def get_stt_model():
    """Primary STT model (override via OPENAI_STT_MODEL)."""
    try:
        configured = getattr(settings, "OPENAI_STT_MODEL", None)
    except Exception:
        configured = None
    return (
        (configured or os.environ.get("OPENAI_STT_MODEL") or DEFAULT_STT_MODEL)
        .strip()
        or DEFAULT_STT_MODEL
    )


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
    """Map normalized hint (+ optional phone) to dialect key."""
    if normalized_hint == "FR-FR":
        return WHISPER_DIALECT_FRENCH
    if normalized_hint == "EN-US":
        return WHISPER_DIALECT_ENGLISH
    if normalized_hint == "AR-MA":
        return WHISPER_DIALECT_MOROCCAN
    if normalized_hint == "AR-SA":
        return WHISPER_DIALECT_GULF
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
    Arabic routes use language=None for auto-detection (prompt carries dialect bias).
    """
    key = _normalize_voice_language_hint(voice_language_hint)
    cfg = WHISPER_LANGUAGE_PROMPTS.get(key) or WHISPER_LANGUAGE_PROMPTS["AUTO"]
    return (cfg.get("language"), cfg.get("prompt") or DEFAULT_WHISPER_PROMPT)


def build_whisper_prompt_with_context(voice_language_hint, last_ai_message_bodies, channel=None, sender=None):
    """
    Build a short Whisper prompt: dialect vocab + tiny conversation hint.
    Avoid injecting long AI sales replies (they cause decoding drift / hallucinations).

    Returns:
        (full_prompt_string, None)
    """
    normalized = _normalize_voice_language_hint(voice_language_hint)
    router_key = _router_key_for_whisper(normalized, channel=channel, sender=sender)
    vocab_line = get_whisper_prompt(router_key)
    _, base_prompt = get_whisper_config(voice_language_hint)

    # Only a tiny hint from the last assistant message (vocabulary priming), not full sales copy.
    ctx = ""
    for t in (last_ai_message_bodies or [])[-1:]:
        t = (t or "").strip()
        if t and t != "[media]":
            # Drop emoji / media markers; keep a short slice
            t = re.sub(r"[\U0001F300-\U0001FAFF]", "", t)
            t = re.sub(r"\s+", " ", t).strip()[:80]
            if t:
                ctx = "Recent reply words: " + t + ". "
            break

    if router_key == WHISPER_DIALECT_GULF:
        tail = "عميل خليجي؛ انسخ كما يُسمع فقط."
    elif router_key == WHISPER_DIALECT_FRENCH:
        tail = "Français e-commerce. Transcrire seulement ce qui est dit."
    elif router_key == WHISPER_DIALECT_ENGLISH:
        tail = "English e-commerce. Transcribe only what is spoken."
    else:
        tail = "دارجة أو عربية مع فرنسية؛ انسخ فقط ما يُسمع، بدون رموز أو اختراع."

    full = (ctx + vocab_line + " " + (base_prompt or "") + " " + tail).strip()
    if len(full) > WHISPER_PROMPT_MAX_CHARS:
        full = full[:WHISPER_PROMPT_MAX_CHARS]
    return full, None


def looks_like_speech(text) -> bool:
    """
    True if text looks like real spoken language (letters), not emoji/noise garbage.
    Used before saving transcripts and before clean_transcription.
    """
    if text is None:
        return False
    t = (text or "").strip()
    if not t or t == STT_UNINTELLIGIBLE:
        return False

    letters = sum(1 for c in t if c.isalpha())
    if letters < MIN_MEANINGFUL_LETTERS:
        return False

    non_space = [c for c in t if not c.isspace()]
    if not non_space:
        return False

    letter_ratio = letters / max(len(non_space), 1)
    if letter_ratio < 0.25:
        return False

    noise_hits = sum(1 for c in t if c in _STT_NOISE_SYMBOLS)
    if noise_hits >= 2:
        return False
    if t.count("🔊") >= 1 and letters < 6:
        return False

    # Repeated same non-letter character (🔊🔊🔊 or ......)
    if re.search(r"([^\w\s\u0600-\u06FF])\1{2,}", t, flags=re.UNICODE):
        return False

    return True


def is_whisper_hallucination(text):
    """
    True if transcription is empty, known subtitle artifact, or non-speech garbage
    (emoji-only / speaker symbols — the 'Heard: 🔊' failure mode).
    """
    if text is None:
        return True
    t = (text or "").strip()
    if not t:
        return True
    if t == STT_UNINTELLIGIBLE:
        return True
    if not looks_like_speech(t):
        return True
    t_lower = t.lower()
    for phrase in WHISPER_HALLUCINATION_PHRASES:
        p = (phrase or "").strip()
        if not p:
            continue
        if p.lower() in t_lower or p in t:
            return True
    return False


def _probe_audio_quality(media_content, original_suffix=".ogg"):
    """
    Probe duration / silence without preparing an upload file.
    Returns (duration_ms_or_None, reject_reason_or_None).
    """
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
    except ImportError:
        return None, None

    tmp_in = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix)
        tmp_in.write(media_content)
        tmp_in.close()
        seg = AudioSegment.from_file(tmp_in.name, format=original_suffix.lstrip(".") or "ogg")
        duration_ms = len(seg)
        if duration_ms < MIN_AUDIO_DURATION_MS:
            logger.info("STT audio too short: %sms (min %s)", duration_ms, MIN_AUDIO_DURATION_MS)
            return duration_ms, "too_short"
        try:
            nonsilent = detect_nonsilent(seg, min_silence_len=200, silence_thresh=seg.dBFS - 16)
            if not nonsilent and duration_ms < 3000:
                logger.info("STT audio near-silent: duration=%sms dBFS=%s", duration_ms, round(seg.dBFS, 1))
                return duration_ms, "too_quiet"
        except Exception:
            pass
        return duration_ms, None
    except Exception as e:
        logger.warning("STT audio probe failed: %s", e)
        return None, None
    finally:
        if tmp_in and os.path.exists(tmp_in.name):
            try:
                os.unlink(tmp_in.name)
            except OSError:
                pass


def _write_original_ogg(media_content):
    """
    Write WhatsApp Opus bytes as .ogg (NOT .oga).
    gpt-4o-*-transcribe rejects .oga; whisper accepts both.
    Prefer original bytes — lossy re-encode (mp3 64k) destroys dialect clarity.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    tmp.write(media_content)
    tmp.close()
    return tmp.name


def _convert_to_wav_16k(media_content, original_suffix=".ogg"):
    """
    Lossless-ish STT fallback: mono 16 kHz WAV PCM (no mp3 recompression).
    Used only when the API rejects the original OGG container.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        return None

    tmp_in = None
    tmp_out = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix)
        tmp_in.write(media_content)
        tmp_in.close()
        seg = AudioSegment.from_file(tmp_in.name, format=original_suffix.lstrip(".") or "ogg")
        seg = seg.set_channels(1).set_frame_rate(16000)
        tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_out.close()
        seg.export(tmp_out.name, format="wav")
        return tmp_out.name
    except Exception as e:
        logger.warning("STT WAV convert failed: %s", e)
        if tmp_out and os.path.exists(getattr(tmp_out, "name", "") or ""):
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


def _is_gpt4o_transcribe(model: str) -> bool:
    m = (model or "").lower()
    return "gpt-4o" in m and "transcribe" in m


def _post_transcription(path_to_use, fname, mime, model, prompt, language, api_key):
    """POST one transcription request. Returns (text_or_None, http_status, error_snippet)."""
    with open(path_to_use, "rb") as f:
        files = {"file": (fname, f, mime)}
        data = {"model": model}
        # temperature only reliably supported on whisper-1
        if model == "whisper-1" or model.startswith("whisper"):
            data["temperature"] = "0"
        # gpt-4o-*-transcribe only supports response_format=json
        if _is_gpt4o_transcribe(model):
            data["response_format"] = "json"
        if prompt:
            data["prompt"] = prompt
        if language:
            data["language"] = language
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(WHISPER_API_URL, files=files, data=data, headers=headers, timeout=60)

    if resp.status_code != 200:
        return None, resp.status_code, (resp.text or "")[:400]

    out = resp.json() if resp.content else {}
    text = (out.get("text") or "").strip()
    return text, 200, None


def _stt_models_to_try(primary_model: str):
    models = [primary_model]
    for m in FALLBACK_STT_MODELS:
        if m and m not in models:
            models.append(m)
    return models


def transcribe_audio(media_content, prompt=None, model=None, language=None, voice_language_hint=None):
    """
    Transcribe WhatsApp voice bytes with gpt-4o-transcribe (primary).

    Sends ORIGINAL OGG/Opus (filename .ogg) to preserve quality — do not re-encode to low-bitrate MP3.
    Falls back to WAV 16k only on format errors, then to weaker models.

    Returns:
        Transcribed text, STT_UNINTELLIGIBLE, or None on hard failure.
    """
    if not media_content:
        logger.warning("STT: empty media_content")
        return None
    api_key = get_openai_api_key()
    if not api_key:
        logger.warning("stt_service: OPENAI_API_KEY not set")
        return None

    primary_model = (model or get_stt_model()).strip() or DEFAULT_STT_MODEL

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

    duration_ms, reject_reason = _probe_audio_quality(media_content, ".ogg")
    if reject_reason in ("too_short", "too_quiet"):
        logger.info(
            "STT reject before API: reason=%s duration_ms=%s bytes=%s",
            reject_reason,
            duration_ms,
            len(media_content),
        )
        return STT_UNINTELLIGIBLE

    # Prefer original Opus/OGG — WhatsApp voice quality is already good for STT.
    path_to_use = None
    wav_path = None
    cleanup_paths = []
    try:
        path_to_use = _write_original_ogg(media_content)
        cleanup_paths.append(path_to_use)
        mime = "audio/ogg"
        fname = "audio.ogg"  # critical: not .oga

        models_to_try = _stt_models_to_try(primary_model)
        last_err = None
        format_retry_done = False

        for attempt_model in models_to_try:
            try:
                text, status, err = _post_transcription(
                    path_to_use, fname, mime, attempt_model, prompt, language, api_key
                )
            except requests.exceptions.Timeout:
                logger.warning("STT timeout model=%s", attempt_model)
                last_err = "timeout"
                continue
            except Exception as e:
                logger.warning("STT request failed model=%s: %s", attempt_model, e)
                last_err = str(e)
                continue

            # Format rejected → convert once to WAV 16k and retry same model
            if status == 400 and not format_retry_done and err and (
                "format" in err.lower() or "unsupported" in err.lower() or "oga" in err.lower()
            ):
                logger.warning("STT format error model=%s; converting to WAV 16k. err=%s", attempt_model, err)
                wav_path = _convert_to_wav_16k(media_content, ".ogg")
                if wav_path:
                    cleanup_paths.append(wav_path)
                    path_to_use = wav_path
                    mime = "audio/wav"
                    fname = "audio.wav"
                    format_retry_done = True
                    try:
                        text, status, err = _post_transcription(
                            path_to_use, fname, mime, attempt_model, prompt, language, api_key
                        )
                    except Exception as e:
                        logger.warning("STT WAV retry failed model=%s: %s", attempt_model, e)
                        last_err = str(e)
                        continue

            if status != 200:
                logger.warning("STT API error model=%s status=%s: %s", attempt_model, status, err)
                last_err = err
                continue

            logger.info(
                "STT ok model=%s duration_ms=%s bytes=%s chars=%s file=%s preview=%r",
                attempt_model,
                duration_ms,
                len(media_content),
                len(text or ""),
                fname,
                (text or "")[:120],
            )

            if not text:
                # try next model — empty from a strong model is rare
                continue

            if is_whisper_hallucination(text):
                logger.info("STT hallucination rejected model=%s preview=%r", attempt_model, text[:80])
                # try next model before giving up
                last_err = "hallucination"
                continue

            return text

        if last_err == "hallucination":
            return STT_UNINTELLIGIBLE
        logger.warning("STT all models failed last_err=%s", last_err)
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
    Light post-pass only. MUST NOT rewrite Darija into MSA or invent words —
    aggressive "correction" was making wrong transcripts worse.
    """
    if not raw_text or not (raw_text or "").strip():
        return raw_text or ""
    if raw_text == STT_UNINTELLIGIBLE:
        return raw_text
    if is_whisper_hallucination(raw_text) or not looks_like_speech(raw_text):
        logger.info("clean_transcription skipped junk preview=%r", (raw_text or "")[:60])
        return STT_UNINTELLIGIBLE

    api_key = get_openai_api_key()
    if not api_key:
        return raw_text

    lang_label = target_language or "AUTO"
    if isinstance(lang_label, str) and len(lang_label) > 60:
        lang_label = lang_label[:60]

    # Conservative: keep dialect (Darija / Franco-Arabic / French mix) as spoken.
    instruction = (
        "You fix ONLY clear ASR spelling glitches in a WhatsApp voice-note transcript.\n"
        f"Store language hint: {lang_label}.\n"
        "STRICT RULES:\n"
        "- Do NOT translate.\n"
        "- Do NOT convert Moroccan Darija / Maghrebi / Gulf dialect into Modern Standard Arabic.\n"
        "- Do NOT replace dialect words with 'more correct' words.\n"
        "- Do NOT invent missing words or change the customer's meaning.\n"
        "- Keep French/English product words mixed in as they appear.\n"
        "- If the text is already readable, return it UNCHANGED.\n"
        "- If the input is nonsense/symbols only, reply exactly: UNINTELLIGIBLE\n"
        f"Transcript:\n{raw_text}\n"
        "Reply with ONLY the final text."
    )

    url = getattr(settings, "OPENAI_CHAT_URL", None) or "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": instruction}],
        "max_tokens": 500,
        "temperature": 0,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.warning("clean_transcription API %s: %s", resp.status_code, (resp.text or "")[:200])
            return raw_text
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = (choice.get("message", {}).get("content") or "").strip()
        if not content:
            return raw_text
        if content.upper() == "UNINTELLIGIBLE" or is_whisper_hallucination(content):
            return STT_UNINTELLIGIBLE
        if not looks_like_speech(content):
            return raw_text  # keep original rather than empty
        # If cleaner drastically rewrote (>60% different length or very different), keep original
        if abs(len(content) - len(raw_text)) > max(40, int(len(raw_text) * 0.6)):
            logger.info("clean_transcription rejected large rewrite; keeping raw")
            return raw_text
        return content
    except Exception as e:
        logger.warning("clean_transcription: %s", e)
        return raw_text
