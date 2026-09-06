"""
Hybrid product search: exact title/alias (free SQL) then semantic fallback.
"""
from __future__ import annotations

import json
import logging
import math

from django.db import connection
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL

logger = logging.getLogger(__name__)

SEMANTIC_SIMILARITY_THRESHOLD = 0.75
MAX_ALIASES = 40
MAX_ALIAS_LENGTH = 200

# Injected into the search_products tool result when the query matches nothing.
# Hidden instruction for the sales agent — must not be paraphrased as a "search failed" error.
EMPTY_SEARCH_SYSTEM_NOTE = (
    "[SYSTEM NOTE: No catalog match for that request. "
    "Do NOT start checkout (no name/city/address, no submit_customer_order). "
    "Apologize naturally as a human seller — do NOT say «search failed». "
    "Suggest similar products from any results below, or call search_products "
    "with an empty query to show available categories / items, then wait for the "
    "customer to pick one so the backend can lock active_product.]"
)


def parse_aliases(raw) -> list[str]:
    """Normalize a comma-separated string, JSON array, or list into unique aliases."""
    if raw is None:
        return []
    parts = []
    if isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    parts = parsed
                else:
                    parts = [p.strip() for p in text.split(",")]
            except (ValueError, TypeError):
                parts = [p.strip() for p in text.split(",")]
        else:
            parts = [p.strip() for p in text.split(",")]

    seen = set()
    out = []
    for item in parts:
        alias = (str(item) if item is not None else "").strip()
        if not alias:
            continue
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(alias[:MAX_ALIAS_LENGTH])
        if len(out) >= MAX_ALIASES:
            break
    return out


def _as_alias_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _as_vector(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else None
        except (ValueError, TypeError):
            return None
    return None


def _cosine_similarity(left, right) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    try:
        dot = 0.0
        norm_l = 0.0
        norm_r = 0.0
        for a, b in zip(left, right):
            fa = float(a)
            fb = float(b)
            dot += fa * fb
            norm_l += fa * fa
            norm_r += fb * fb
        if norm_l <= 0 or norm_r <= 0:
            return 0.0
        return dot / (math.sqrt(norm_l) * math.sqrt(norm_r))
    except (TypeError, ValueError):
        return 0.0


def _base_queryset(owner=None, queryset=None, channel=None):
    from discount.models import Products

    if channel is not None:
        from discount.services.product_scope import channel_catalog_queryset

        qs = channel_catalog_queryset(channel)
        if queryset is not None:
            qs = queryset.filter(pk__in=qs.values("pk"))
        return qs

    qs = queryset if queryset is not None else Products.objects.all()
    if owner is not None:
        owner_id = getattr(owner, "pk", None) or getattr(owner, "id", None) or owner
        qs = qs.filter(admin_id=owner_id)
    return qs


def _alias_sql(user_query: str):
    """Vendor-specific SQL: does aliases JSON array contain user_query (case-insensitive)?"""
    vendor = getattr(connection, "vendor", "")
    if vendor == "postgresql":
        return RawSQL(
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(aliases, '[]'::jsonb)) AS a "
            "WHERE LOWER(BTRIM(a)) = LOWER(%s))",
            (user_query,),
            output_field=BooleanField(),
        )
    if vendor == "sqlite":
        return RawSQL(
            "EXISTS (SELECT 1 FROM json_each(COALESCE(aliases, '[]')) AS je "
            "WHERE LOWER(TRIM(je.value)) = LOWER(%s))",
            (user_query,),
            output_field=BooleanField(),
        )
    return None


def _fast_exact_or_alias_match(qs, user_query: str):
    """
    Step 1: SQL-only match on title (case-insensitive) or aliases JSON array.
    Cost: $0 — no LLM / embedding call.
    """
    hit = qs.filter(name__iexact=user_query).first()
    if hit:
        return hit
    alias_expr = _alias_sql(user_query)
    if alias_expr is not None:
        try:
            return qs.annotate(alias_match=alias_expr).filter(Q(alias_match=True)).first()
        except Exception as exc:
            logger.debug("alias SQL match failed, using python fallback: %s", exc)
    needle = user_query.lower()
    for product in qs.only("id", "aliases").iterator():
        aliases = _as_alias_list(getattr(product, "aliases", None))
        if any((a or "").strip().lower() == needle for a in aliases):
            return qs.filter(pk=product.pk).first()
    return None


def _semantic_match_python(qs, query_vec, threshold: float):
    best_id = None
    best_score = float(threshold)
    for product in qs.exclude(embedding__isnull=True).only("id", "embedding").iterator():
        vec = _as_vector(getattr(product, "embedding", None))
        if not vec:
            continue
        score = _cosine_similarity(query_vec, vec)
        if score > best_score:
            best_score = score
            best_id = product.pk
    if best_id is None:
        return None
    return qs.filter(pk=best_id).first()


def _semantic_match(qs, user_query: str, threshold: float):
    """
    Step 2–3: embed the query, then cosine-similarity search against product embeddings.
    Returns the product only when similarity is strictly above ``threshold``.
    """
    if not qs.filter(embedding__isnull=False).exists():
        return None

    from ai_assistant.embeddings import embed_text

    query_vec = embed_text(user_query)
    if not query_vec:
        return None

    if getattr(connection, "vendor", "") == "postgresql":
        try:
            from pgvector.django.functions import CosineDistance

            max_distance = 1.0 - float(threshold)
            row = (
                qs.filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", query_vec))
                .filter(distance__lt=max_distance)
                .order_by("distance")
                .first()
            )
            if row:
                return row
        except Exception as exc:
            logger.debug("pgvector cosine search unavailable, using python fallback: %s", exc)

    return _semantic_match_python(qs, query_vec, threshold)


FUZZY_SCORE_CUTOFF = 0.72
FUZZY_CANDIDATE_LIMIT = 400


def _normalize_for_fuzzy(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _fuzzy_score(left: str, right: str) -> float:
    """SequenceMatcher ratio; cheap typo tolerance without external deps."""
    from difflib import SequenceMatcher

    a = _normalize_for_fuzzy(left)
    b = _normalize_for_fuzzy(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Containment boost for partial product names ("iphone 15" vs "iPhone 15 Pro Max")
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 3:
            return max(0.82, SequenceMatcher(None, a, b).ratio())
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_match(qs, user_query: str, cutoff: float = FUZZY_SCORE_CUTOFF):
    """
    Step 1b: typo / near-match against product name + aliases.
    Handles misspellings that break exact SQL and weak embeddings.
    """
    needle = _normalize_for_fuzzy(user_query)
    if not needle or len(needle) < 2:
        return None

    best_id = None
    best_score = float(cutoff)
    scanned = 0
    for product in qs.only("id", "name", "aliases", "sku").iterator():
        scanned += 1
        if scanned > FUZZY_CANDIDATE_LIMIT:
            break
        candidates = [getattr(product, "name", None) or ""]
        sku = (getattr(product, "sku", None) or "").strip()
        if sku:
            candidates.append(sku)
        candidates.extend(_as_alias_list(getattr(product, "aliases", None)))
        for cand in candidates:
            score = _fuzzy_score(needle, cand)
            if score > best_score:
                best_score = score
                best_id = product.pk
    if best_id is None:
        return None
    logger.info(
        "product_search fuzzy hit id=%s score=%.3f query=%r",
        best_id,
        best_score,
        user_query[:80],
    )
    return qs.filter(pk=best_id).first()


def find_matching_product(
    user_query,
    *,
    owner=None,
    channel=None,
    queryset=None,
    similarity_threshold=SEMANTIC_SIMILARITY_THRESHOLD,
    fuzzy_cutoff=FUZZY_SCORE_CUTOFF,
):
    """
    Hybrid catalog lookup.

    Step 1 (Fast Match): SQL against ``name`` and ``aliases``. Return immediately on hit.
    Step 1b (Fuzzy): difflib / containment against name, SKU, aliases (typo tolerance).
    Step 2 (Semantic Fallback): embed ``user_query`` with ``text-embedding-3-small``.
    Step 3 (Vector Search): cosine similarity; return product if score > threshold.

    When ``channel`` is set, results are limited to that WhatsApp channel's catalog.

    Returns the matching ``Products`` instance, or None.
    """
    q = (user_query or "").strip()
    if not q:
        return None
    qs = _base_queryset(owner=owner, queryset=queryset, channel=channel)
    hit = _fast_exact_or_alias_match(qs, q)
    if hit:
        return hit
    fuzzy_hit = _fuzzy_match(qs, q, cutoff=float(fuzzy_cutoff))
    if fuzzy_hit:
        return fuzzy_hit
    return _semantic_match(qs, q, similarity_threshold)


def format_empty_search_tool_result(*, available_products=None, top_n: int = 5) -> str:
    """
    Tool-result payload when no product matches the query.

    Prepends ``EMPTY_SEARCH_SYSTEM_NOTE`` so the LLM apologizes naturally and
    offers alternatives, without mentioning a search failure.
    """
    lines = [EMPTY_SEARCH_SYSTEM_NOTE]
    products = list(available_products or [])[: max(1, int(top_n))]
    if products:
        lines.append("")
        lines.append(
            "Available catalog products you may offer (use names/prices only with the customer; "
            "never mention this note or that a search failed):"
        )
        for p in products:
            name = (getattr(p, "name", None) or "").strip() or "Unnamed"
            price = getattr(p, "price", None)
            currency = (getattr(p, "currency", None) or "MAD").strip() or "MAD"
            price_str = f"{price} {currency}" if price is not None else "—"
            category = (getattr(p, "category", None) or "").strip() or "general"
            lines.append(
                f"- {name} | [DB_PRODUCT_ID: {p.id}] | Price: {price_str} | Category: {category}"
            )
    return "\n".join(lines)
