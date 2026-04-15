"""
Sanitize assistant / LLM output before Text-to-Speech (ElevenLabs, OpenAI TTS).

Removes system markers, markdown, emojis, and line breaks so they are not spoken aloud.
"""

from __future__ import annotations

import re

# System / chunk delimiters (must not be spoken)
_SPLIT_MARKERS = re.compile(
    r"\[SPLIT\]|</?split>|<split>|\[CHUNK\]|\[SEGMENT\]",
    re.IGNORECASE,
)

# Markdown: links ![alt](u) and [text](url) — keep visible text only
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Line-leading # headers, horizontal rules
_MD_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$", re.MULTILINE)

# Bold / italic / code / strikethrough markers
_MD_WRAPPERS = re.compile(r"\*{1,3}|_{1,3}|`{1,3}|~{2}")

# Common emoji ranges (Unicode symbols & pictographs)
_EMOJI = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # regional indicators / flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors (often with emoji)
    "\U0001F3FB-\U0001F3FF"  # skin tones
    "]+",
    flags=re.UNICODE,
)

_COLLAPSE_WS = re.compile(r"\s+")


def clean_text_for_tts(text: str) -> str:
    """
    Strip content that should never be read by TTS: SPLIT markers, markdown noise,
    emojis, and newlines (collapsed to spaces).
    """
    if text is None:
        return ""
    s = str(text)
    s = _SPLIT_MARKERS.sub(" ", s)
    s = _MD_IMAGE.sub(r"\1", s)
    s = _MD_LINK.sub(r"\1", s)
    s = _MD_HEADER.sub("", s)
    s = _MD_RULE.sub(" ", s)
    s = _MD_WRAPPERS.sub("", s)
    s = _EMOJI.sub("", s)
    s = s.replace("**", "").replace("__", "").replace("~~", "")
    s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    s = _COLLAPSE_WS.sub(" ", s).strip()
    return s
