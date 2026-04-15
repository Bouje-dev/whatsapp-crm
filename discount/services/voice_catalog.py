"""
Voice gallery catalog: map ElevenLabs voice IDs to preview MP3 URLs.

Previews come from (in order of preference):
  1) ``VoiceGalleryEntry.preview_audio_file`` (uploaded in Django Admin → MEDIA)
  2) ``VoiceGalleryEntry.preview_file`` under static: ``static/audio/voice-previews/<filename>``

Play Sample in the UI uses these URLs only — it does **not** call ElevenLabs for gallery previews.
"""

from typing import Any, Dict, List, Optional

from django.templatetags.static import static

from discount.models import VoiceGalleryEntry, dialect_key_to_display

STATIC_PREVIEWS_PREFIX = "audio/voice-previews"


def normalize_language_code(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().replace("-", "_").upper()
    return s


def serialize_voices_for_api(request, provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return voice rows for JSON APIs and UIs: voice_id, name, preview_audio_url, etc.

    If ``provider`` is set (ELEVENLABS or OPENAI), only gallery entries for that TTS backend are returned.
    """
    out: List[Dict[str, Any]] = []
    qs = VoiceGalleryEntry.objects.filter(is_active=True)
    if provider and str(provider).strip():
        qs = qs.filter(provider=str(provider).strip().upper())
    qs = qs.order_by("sort_order", "id")
    for row in qs:
        preview_file = (row.preview_file or "").strip()
        preview_audio_url = None
        # Prefer uploaded preview file (if provided), otherwise fall back to static preview_file.
        if getattr(row, "preview_audio_file", None):
            try:
                rel_or_abs = row.preview_audio_file.url  # e.g. /media/voice_gallery_previews/foo.mp3
            except Exception:
                rel_or_abs = None
            if rel_or_abs:
                preview_audio_url = request.build_absolute_uri(rel_or_abs) if request is not None else rel_or_abs
        if not preview_audio_url and preview_file and request is not None:
            rel_path = static(f"{STATIC_PREVIEWS_PREFIX}/{preview_file}")
            preview_audio_url = request.build_absolute_uri(rel_path)
        vid = row.elevenlabs_voice_id
        display_name = (row.name or "").strip() or vid
        label = (row.label or "").strip() or display_name
        tags = list(row.tags) if isinstance(row.tags, list) else []
        lang_code = normalize_language_code(getattr(row, "language_code", None) or "")
        dkey = getattr(row, "dialect", None) or ""
        out.append(
            {
                "id": vid,
                "voice_id": vid,
                "provider": getattr(row, "provider", None) or "ELEVENLABS",
                "name": display_name,
                "label": label,
                "gender": row.gender,
                "tags": tags,
                "native_arabic": bool(row.native_arabic),
                "language_code": lang_code,
                "dialect": dkey,
                "dialect_display": dialect_key_to_display(dkey),
                "preview_audio_url": preview_audio_url,
                "preview_file": preview_file or None,
            }
        )
    return out
