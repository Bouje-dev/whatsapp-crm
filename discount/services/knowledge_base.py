"""
Knowledge-gap escalation and auto-learning for the WhatsApp sales agent.

When the model cannot answer from the product description or ProductKnowledgeBase,
it calls ``escalate_missing_info``. The merchant answers via Copilot or a magic-link
email. If the customer is still waiting, we WhatsApp immediately; otherwise the
next AI turn weaves the answer in naturally.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

_MAX_KB_PROMPT_ENTRIES = 30
MAGIC_LINK_MAX_AGE_SECONDS = 2 * 60 * 60  # 2 hours
MAGIC_LINK_SALT = "knowledge-gap-escalation-v1"


def _nonempty(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_question(text: str) -> str:
    t = _nonempty(text).lower()
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ة", "ه").replace("ى", "ي")
    t = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", t)
    t = re.sub(r"[?!؟.،,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_QUESTION_STOPWORDS = {
    "واش", "هل", "شنو", "كيفاش", "علاش", "هاد", "هذا", "هذه", "هادشي",
    "الكريم", "كريم", "المنتج", "منتج", "ديال", "ديالنا", "ديالو", "عندنا",
    "عافاك", "فضلك", "ضروري", "سول", "ليا", "لييا", "على", "من", "في", "الى",
    "والى", "و", "او", "ولا", "يا", "هو", "هي", "باش", "غير", "حتى", "مع",
    "هاد", "بالنسبة", "the", "a", "an", "is", "are", "for", "does", "do",
    "can", "this", "that", "cream", "product", "our", "please", "ask", "about",
}


def _stem_question_token(tok: str) -> str:
    t = tok
    for prefix in ("وال", "ولل", "بال", "فال", "لل", "ال"):
        if t.startswith(prefix) and len(t) > len(prefix) + 1:
            t = t[len(prefix):]
            break
    return t


def _intent_tokens(text: str, product=None) -> set:
    t = normalize_question(text)
    if product is not None:
        pname = normalize_question(getattr(product, "name", None) or "")
        if pname:
            t = t.replace(pname, " ")
            for w in pname.split():
                if len(w) >= 3:
                    t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
    tokens = set()
    for raw in t.split():
        if not raw or raw in _QUESTION_STOPWORDS or len(raw) < 2:
            continue
        stemmed = _stem_question_token(raw)
        if stemmed in _QUESTION_STOPWORDS or len(stemmed) < 2:
            continue
        tokens.add(stemmed)
    return tokens


def _edit_distance(a: str, b: str, limit: int = 1) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            v = min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            if v < row_min:
                row_min = v
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _fuzzy_token_overlap(ta: set, tb: set) -> tuple:
    tb_left = set(tb)
    matched = 0
    for x in ta:
        if x in tb_left:
            tb_left.discard(x)
            matched += 1
            continue
        found = None
        if len(x) >= 4:
            for y in list(tb_left):
                if len(y) >= 4 and _edit_distance(x, y, 1) <= 1:
                    found = y
                    break
        if found is not None:
            tb_left.discard(found)
            matched += 1
    union = matched + (len(ta) - matched) + len(tb_left)
    return matched, union


def _atomic_questions_match(a: str, b: str, product=None) -> bool:
    na, nb = normalize_question(a), normalize_question(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 12 and shorter in longer:
        return True
    ta, tb = _intent_tokens(a, product), _intent_tokens(b, product)
    if not ta or not tb:
        return False
    matched, union = _fuzzy_token_overlap(ta, tb)
    smaller = min(len(ta), len(tb))
    if matched == smaller and smaller >= 2:
        return True
    return bool(union) and matched >= 2 and (matched / union) >= 0.72


def _questions_match(a: str, b: str, product=None) -> bool:
    na, nb = normalize_question(a), normalize_question(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    a_atoms = split_atomic_questions(a)
    b_atoms = split_atomic_questions(b)
    if len(a_atoms) >= 2 or len(b_atoms) >= 2:
        return any(
            _atomic_questions_match(x, y, product=product)
            for x in a_atoms
            for y in b_atoms
        )
    return _atomic_questions_match(a, b, product=product)


def split_atomic_questions(text: str) -> list:
    """
    Split a customer message that contains more than one question.
    Uses repeated question markers (واش / هل / does / is), not product topics.
    """
    raw = _nonempty(text)
    if not raw:
        return []
    parts = re.split(
        r"(?=\s*[,،]?\s*واش\b)"
        r"|(?=\s+هل\b)"
        r"|(?=\s+شنو\b)"
        r"|\s+و\s+(?=واش\b|هل\b|شنو\b)"
        r"|[؟?](?=\s*(?:واش|هل|شنو)\b)"
        r"|\s+and\s+(?=(?:is|does|can|will)\b)"
        r"|[?](?=\s*(?:is|does|can|will)\b)"
        r"|\s+et\s+(?=(?:est-ce|est|peut|convient)\b)",
        raw,
        flags=re.I,
    )
    cleaned = []
    for part in parts:
        p = re.sub(r"\s+", " ", (part or "").strip(" \t،,.-"))
        if not p:
            continue
        if re.search(r"[\u0600-\u06FF]", p) and not re.match(r"^(واش|هل|شنو)\b", p):
            p = "واش " + p
        p = p.rstrip("؟?").strip()
        if len(normalize_question(p)) >= 8:
            cleaned.append(p[:4000])
    unique = []
    for p in cleaned:
        if any(_atomic_questions_match(p, u) for u in unique):
            continue
        unique.append(p)
    if len(unique) >= 2:
        return unique
    return [raw]


_CHECKING_TEAM_RE = re.compile(
    r"(نتأكد|نأكد|نتأكدو|من الفريق|الفريق ديالنا|غادي نرجع ليك|"
    r"المعلومات الكاملة|غادي نتحقق|"
    r"checking with.{0,24}team|ask.{0,12}team|i['’]?ll check|"
    r"v[ée]rifie.{0,24}[ée]quipe|je (vais |vais )?v[ée]rifier)",
    re.I | re.S,
)

# (customer-question pattern, strings that must already appear in product context)
_UNVERIFIED_FACT_TOPICS = [
    (
        re.compile(
            r"بشرة\s*حساس|حساس[ةه]|sensitive\s*skin|peau\s*sensible|"
            r"pour\s+(la\s+)?peau\s+sensible|للبشرة الحساس",
            re.I,
        ),
        ("حساس", "sensitive", "sensible"),
    ),
    (
        re.compile(r"حساسي[ةه]|allerg", re.I),
        ("حساسي", "allerg"),
    ),
    (
        re.compile(r"حامل|حوامل|pregnan|grossesse", re.I),
        ("حامل", "pregnan", "grossesse"),
    ),
    (
        re.compile(r"آثار\s*جانبي|side\s*effect|effet\s*secondaire", re.I),
        ("side effect", "آثار جانبي", "effet secondaire"),
    ),
    (
        re.compile(r"للأطفال|للرضع|for\s+kids|for\s+babies|enfants|b[ée]b[ée]", re.I),
        ("أطفال", "رضع", "kids", "babies", "enfant", "bébé", "bebe"),
    ),
    (
        re.compile(
            r"شحال ديال الوقت|قداش وقت|متى (تظهر|يبان|تجي)|وقتاش (تبان|يبان)|"
            r"يعطي نتائج|how long|how soon|when (will|do) (i|it)|"
            r"combien de temps|résultats?",
            re.I,
        ),
        ("أيام", "أسابيع", "نتيجة خلال", "نتائج خلال", "days", "weeks", "results in"),
    ),
]


def _question_topic_indexes(text: str) -> list:
    found = []
    blob = _nonempty(text)
    if not blob:
        return found
    for i, (ask_re, _covered) in enumerate(_UNVERIFIED_FACT_TOPICS):
        if ask_re.search(blob):
            found.append(i)
    return found


def _answer_grounded_in_merchant(merchant_msg: str, answer: str) -> bool:
    """True when the answer is the merchant's own words, not an invented extra fact."""
    m = normalize_question(merchant_msg)
    a = normalize_question(answer)
    if not m or not a:
        return False
    if a in m or m in a:
        return True
    mt, at = _intent_tokens(merchant_msg), _intent_tokens(answer)
    if not at:
        return False
    if len(at) <= 2:
        return at <= mt
    return (len(at & mt) / len(at)) >= 0.65


def merchant_may_resolve_escalation(merchant_msg: str, answer: str, question: str) -> tuple:
    """
    Copilot may resolve only the question the merchant actually answered.
    Returns (ok, error_message).
    """
    if not _nonempty(merchant_msg):
        return False, "No merchant message to ground this answer."
    if not _nonempty(answer):
        return False, "merchant_answer is empty."
    if not _answer_grounded_in_merchant(merchant_msg, answer):
        return (
            False,
            "Use only the merchant's own words from this turn. "
            "Do not invent answers for other pending questions.",
        )
    q_topics = _question_topic_indexes(question)
    if q_topics:
        covered = set(_question_topic_indexes(merchant_msg)) | set(_question_topic_indexes(answer))
        if not any(t in covered for t in q_topics):
            return (
                False,
                "This reply does not answer that pending question. "
                "Leave it pending until the merchant answers it.",
            )
    return True, ""


def reply_claims_checking_with_team(ai_reply: str) -> bool:
    return bool(_CHECKING_TEAM_RE.search(_nonempty(ai_reply)))


def _merchant_fact_blob(product, product_context: str = "") -> str:
    """Catalog + learned KB only — never the prompt's knowledge-gap rule examples."""
    parts = []
    if product is not None:
        for attr in ("name", "description", "how_to_use", "offer"):
            parts.append(_nonempty(getattr(product, attr, None)))
        price = getattr(product, "price", None)
        if price is not None:
            currency = _nonempty(getattr(product, "currency", None)) or "MAD"
            parts.append(f"price {price} {currency}")
        parts.append(_nonempty(getattr(product, "delivery_options", None)))
        parts.append(_nonempty(getattr(product, "return_policy", None)))
        try:
            parts.append(knowledge_prompt_block(product))
        except Exception:
            pass
    else:
        raw = product_context or ""
        raw = re.split(r"Knowledge-gap rule:", raw, maxsplit=1)[0]
        parts.append(raw)
    return "\n".join(p for p in parts if p)


def customer_asked_unverified_fact(customer_question: str, product_context: str = "", product=None) -> bool:
    """True when the customer asked a safety/suitability fact not in the product copy."""
    q = _nonempty(customer_question)
    if not q:
        return False
    blob = _merchant_fact_blob(product, product_context).lower()
    for ask_re, covered in _UNVERIFIED_FACT_TOPICS:
        if not ask_re.search(q):
            continue
        if any((token or "").lower() in blob for token in covered):
            return False
        return True
    return False


_CLAIM_NEAR_TOPIC_RE = re.compile(
    r"مزيان|مناسب|آمن|امن|طبيعي|خفيفه|خفيفة|yes|safe|good|"
    r"oui|convient|parfait|idéal|ideal",
    re.I,
)
_DURATION_HINT_RE = re.compile(
    r"وقت|نتائج|نتيجه|ايام|يوم|اسابيع|اسبوع|hours?|days?|weeks?|"
    r"long|soon|temps|durée|duree",
    re.I,
)


def _clause_matches_labels(question: str, labels: tuple) -> bool:
    """True when the clause is about these field labels (substring or fuzzy token)."""
    qn = normalize_question(question)
    if not qn:
        return False
    for lab in labels:
        ln = normalize_question(lab)
        if ln and ln in qn:
            return True
    qt = _intent_tokens(question)
    lt = set()
    for lab in labels:
        lt |= _intent_tokens(lab)
    if not lt or not qt:
        return False
    matched, _union = _fuzzy_token_overlap(lt, qt)
    return matched >= 1


def _asks_price(question: str) -> bool:
    if _clause_matches_labels(
        question,
        ("ثمن", "سعر", "price", "prix", "cost", "بكم", "بشحال", "ثمنو", "التمن"),
    ):
        return True
    if _clause_matches_labels(question, ("شحال", "كام", "how much", "combien")):
        return not _DURATION_HINT_RE.search(normalize_question(question))
    return False


def _asks_delivery(question: str) -> bool:
    return _clause_matches_labels(
        question,
        ("توصيل", "شحن", "delivery", "shipping", "livraison", "livrer"),
    )


def _asks_warranty(question: str) -> bool:
    return _clause_matches_labels(
        question,
        ("ضمان", "كفاله", "كفالة", "warranty", "garantie", "ارجاع", "رجوع"),
    )


_PERSONAL_DATIVE_RE = re.compile(
    r"\b(ليا|لييا|عندي|معايا|for me|pour moi)\b",
    re.I,
)
_OUTCOME_VERB_RE = re.compile(
    r"يخدم|ينفع|يفيد|يصلح|work|marche|نتيجه|نتائج|effective|efficac",
    re.I,
)
_RESULTS_GUARANTEE_RE = re.compile(
    r"guaranteed(?:\s+to\s+work)?|is it guaranteed|"
    r"مضمون(?:ه|ة)?(?:\s*(?:100|النتيجه|النتائج|يخدم))?|"
    r"garantie de r[ée]sultat",
    re.I,
)
_INGREDIENT_SPEC_RE = re.compile(
    r"مكونات|مركبات|يحتوي|تركيب|ingredients?|composition|paraben|بارابين",
    re.I,
)


def is_factual_product_spec_gap(
    question: str,
    product=None,
    product_context: str = "",
) -> bool:
    """True for a missing product spec (ingredients, medical compatibility, etc.)."""
    q = _nonempty(question)
    if not q:
        return False
    if find_catalog_answer(product, q):
        return False
    if customer_asked_unverified_fact(q, product_context=product_context, product=product):
        return True
    if _INGREDIENT_SPEC_RE.search(q):
        blob = _merchant_fact_blob(product, product_context).lower()
        if any(tok in blob for tok in ("مكونات", "ingredient", "يحتوي", "تركيب")):
            return False
        return True
    return False


def is_subjective_sales_clause(question: str, product=None) -> bool:
    """Reassurance / personal efficacy — handle with sales, never a knowledge ticket."""
    q = _nonempty(question)
    if not q:
        return False
    if is_factual_product_spec_gap(q, product):
        return False
    if _asks_price(q) or _asks_delivery(q) or _asks_warranty(q):
        return False
    if _question_topic_indexes(q):
        return False
    if _PERSONAL_DATIVE_RE.search(q) and _OUTCOME_VERB_RE.search(q):
        return True
    if _RESULTS_GUARANTEE_RE.search(q) and not _asks_warranty(q):
        return True
    return False


def is_store_policy_clause(question: str) -> bool:
    """Shipping / return-warranty are store policies, not product-spec gaps."""
    q = _nonempty(question)
    if not q:
        return False
    if _question_topic_indexes(q):
        return False
    return _asks_delivery(q) or _asks_warranty(q)


def _clause_skip_ticket_status(question: str, product=None) -> dict[str, Any] | None:
    """Return a tool result when this clause must not open a knowledge-gap ticket."""
    q = _nonempty(question)
    if not q:
        return None
    if is_factual_product_spec_gap(q, product):
        return None
    if is_subjective_sales_clause(q, product):
        return {
            "success": True,
            "status": "sales_objection",
            "question": q,
            "message": (
                "DO NOT ESCALATE. This is a sales objection / reassurance request "
                "(e.g. personal efficacy, 'will it work for me', 'is it guaranteed'). "
                "Handle it yourself with empathy and the product's general benefits "
                "from PRODUCT CONTEXT. Do NOT say you are checking with the team."
            ),
        }
    if is_store_policy_clause(q):
        return {
            "success": True,
            "status": "store_policy",
            "question": q,
            "message": (
                "DO NOT ESCALATE as missing product knowledge. This is a store policy "
                "(shipping / returns). Quote the Delivery or Return/Warranty line from "
                "PRODUCT CONTEXT if present. If it is missing, handle it as a seller "
                "(ask city, explain standard delivery) — do NOT open a product-spec ticket "
                "and do NOT invent 'free for all cities'."
            ),
        }
    return None


def find_catalog_answer(product, question: str) -> str:
    """
    Map a clause to a product-row field (price, delivery_options, return_policy).
    Empty string means this clause does not map to a filled catalog field.
    """
    if not product or not _nonempty(question):
        return ""
    q = _nonempty(question)
    if _asks_price(q):
        price = getattr(product, "price", None)
        if price is None:
            return ""
        currency = _nonempty(getattr(product, "currency", None)) or "MAD"
        return f"الثمن هو {price} {currency}."
    if _asks_delivery(q):
        delivery = _nonempty(getattr(product, "delivery_options", None))
        if not delivery:
            return ""
        return f"التوصيل: {delivery}."
    if _asks_warranty(q):
        policy = _nonempty(getattr(product, "return_policy", None))
        if policy:
            return f"سياسة الضمان / الإرجاع: {policy}."
        return (
            "سياسة الضمان: المعاينة قبل الأداء ما كايناش إلا إذا سمحت شركة التوصيل."
        )
    return ""


def _answer_reflected_in_text(reply: str, answer: str) -> bool:
    if not _nonempty(reply) or not _nonempty(answer):
        return False
    digits = re.findall(r"\d+(?:[.,]\d+)?", answer)
    if digits and all(d in reply for d in digits):
        return True
    rn, an = normalize_question(reply), normalize_question(answer)
    if an and an in rn:
        return True
    at, rt = _intent_tokens(answer), _intent_tokens(reply)
    if not at:
        return False
    matched, union = _fuzzy_token_overlap(at, rt)
    need = min(2, len(at))
    return matched >= need and (not union or matched / union >= 0.4)


def _catalog_answers_missing_from_reply(reply: str, outcome: dict | None) -> bool:
    parts = (outcome or {}).get("parts") or []
    knowns = [
        _nonempty(p.get("answer"))
        for p in parts
        if p.get("status") == "already_known"
    ]
    if not knowns and (outcome or {}).get("status") == "already_known":
        knowns = [_nonempty((outcome or {}).get("answer"))]
    knowns = [a for a in knowns if a]
    if not knowns:
        return False
    if not _nonempty(reply):
        return True
    return any(not _answer_reflected_in_text(reply, ans) for ans in knowns)


def _known_answers_from_outcome(outcome: dict | None) -> list:
    parts = (outcome or {}).get("parts") or []
    found = [
        _nonempty(p.get("answer"))
        for p in parts
        if p.get("status") == "already_known" and p.get("answer")
    ]
    if found:
        return found
    if (outcome or {}).get("status") == "already_known":
        ans = _nonempty((outcome or {}).get("answer"))
        return [ans] if ans else []
    return []


def _gap_questions_from_outcome(outcome: dict | None) -> list:
    parts = (outcome or {}).get("parts") or []
    gaps = [
        _nonempty(p.get("question"))
        for p in parts
        if p.get("status") in ("escalated", "already_pending")
    ]
    return [g for g in gaps if g]


def customer_reply_from_escalate_outcome(outcome: dict | None, customer_question: str = "") -> str:
    """Customer-facing text: catalog facts first, then waiting copy for real gaps."""
    bits = list(_known_answers_from_outcome(outcome))
    gaps = _gap_questions_from_outcome(outcome)
    status = (outcome or {}).get("status")
    if gaps:
        bits.append(waiting_for_merchant_reply("، ".join(gaps)))
    elif status in ("escalated", "already_pending"):
        bits.append(waiting_for_merchant_reply(customer_question))
    elif not bits and status == "already_known":
        bits.extend(_known_answers_from_outcome(outcome))
    return "\n\n".join(b for b in bits if b)


def _merge_catalog_into_reply(reply: str, outcome: dict | None) -> str:
    intros = [
        ans
        for ans in _known_answers_from_outcome(outcome)
        if not _answer_reflected_in_text(reply, ans)
    ]
    body = _nonempty(reply)
    if not intros:
        return body
    if not body:
        return "\n\n".join(intros)
    return "\n\n".join(intros + [body])


def _reply_invents_unverified_fact(
    reply: str,
    question: str,
    product=None,
    product_context: str = "",
) -> bool:
    """True when the reply asserts an unverified safety/suitability fact."""
    q = _nonempty(question)
    r = _nonempty(reply)
    if not q or not r:
        return False
    blob = _merchant_fact_blob(product, product_context).lower()
    for ask_re, covered in _UNVERIFIED_FACT_TOPICS:
        if not ask_re.search(q):
            continue
        if any((token or "").lower() in blob for token in covered):
            continue
        for match in ask_re.finditer(r):
            window = r[max(0, match.start() - 70) : match.end() + 70]
            if _CLAIM_NEAR_TOPIC_RE.search(window):
                return True
    return False


def _strip_checking_team_copy(reply: str) -> str:
    text = _nonempty(reply)
    if not text:
        return ""
    chunks = re.split(r"(?<=[.!?؟\n])\s+", text)
    kept = [c.strip() for c in chunks if c.strip() and not _CHECKING_TEAM_RE.search(c)]
    return "\n".join(kept).strip()


def waiting_for_merchant_reply(customer_question: str) -> str:
    q = _nonempty(customer_question)
    if re.search(r"[\u0600-\u06FF]", q):
        return (
            "هاد سؤال مهم بزاف! غادي نتأكد من الفريق ديالنا باش نعطيك جواب دقيق، "
            "ونرجع ليك دابا. 👍"
        )
    if re.search(r"[éèêàùçœ]|peau|sensible|convient|équipe", q, re.I):
        return (
            "Bonne question. Je vérifie ça avec l'équipe et je te reviens "
            "avec une réponse précise."
        )
    return "Good question — I'll check with the team and get you an accurate answer shortly."


def ensure_knowledge_gap_recorded(
    *,
    channel,
    customer_phone: str,
    customer_question: str,
    ai_reply: str,
    tool_names=None,
    product=None,
    product_context: str = "",
) -> str:
    """
    Persist pending gaps, answer catalog fields the model skipped, and strip
    unverified claims (e.g. sensitive-skin guesses) from the customer reply.
    """
    names = set()
    for n in tool_names or []:
        if isinstance(n, dict):
            names.add(str(n.get("name") or ""))
        else:
            names.add(str(n or ""))

    question = _nonempty(customer_question)
    reply = ai_reply or ""
    if not question:
        return reply

    tool_called = "escalate_missing_info" in names
    verbal = reply_claims_checking_with_team(reply)
    missing_fact = customer_asked_unverified_fact(
        question, product_context=product_context, product=product
    )
    catalog_asked = bool(product) and (
        _asks_price(question) or _asks_delivery(question) or _asks_warranty(question)
    )
    if not tool_called and not verbal and not missing_fact and not catalog_asked:
        return reply

    try:
        outcome = handle_escalate_missing_info(
            channel,
            customer_phone,
            question,
            product=product,
        )
    except Exception:
        logger.exception("ensure_knowledge_gap_recorded failed")
        return reply

    status = (outcome or {}).get("status")
    composed = customer_reply_from_escalate_outcome(outcome, question)
    gaps = _gap_questions_from_outcome(outcome)
    halluc = _reply_invents_unverified_fact(
        reply, question, product=product, product_context=product_context
    )
    catalog_missing = _catalog_answers_missing_from_reply(reply, outcome)
    logger.info(
        "knowledge gap safety-net status=%s verbal=%s missing_fact=%s "
        "tool=%s halluc=%s catalog_missing=%s channel=%s phone=%s",
        status,
        verbal,
        missing_fact,
        tool_called,
        halluc,
        catalog_missing,
        getattr(channel, "id", None),
        customer_phone,
    )
    print(
        f"📌 Knowledge gap safety-net: {status} "
        f"(verbal={verbal}, missing_fact={missing_fact}, tool={tool_called}, "
        f"halluc={halluc}, catalog_missing={catalog_missing}) q={question[:80]!r}"
    )

    if halluc:
        if gaps:
            return composed or waiting_for_merchant_reply(question)
        return composed or _merge_catalog_into_reply("", outcome) or _strip_checking_team_copy(reply)
    body = reply
    if not gaps and verbal:
        body = _strip_checking_team_copy(reply)
    if catalog_missing:
        merged = _merge_catalog_into_reply(body, outcome)
        return merged or composed or body
    if not _nonempty(body):
        if gaps:
            return composed or waiting_for_merchant_reply(question)
        return composed or ""
    if missing_fact and not verbal and not tool_called:
        return composed or (waiting_for_merchant_reply(question) if gaps else body)
    return body


def empty_sales_reply_fallback(
    customer_question: str = "",
    *,
    market: str = "MA",
    product=None,
    tool_names=None,
) -> str:
    """
    Last-resort WhatsApp text when the LLM returned empty after tools.
    Never asks to pick a product or send checkout fields if a product is already active.
    """
    names = set()
    for n in tool_names or []:
        if isinstance(n, dict):
            names.add(str(n.get("name") or ""))
        else:
            names.add(str(n or ""))
    if "escalate_missing_info" in names:
        if is_factual_product_spec_gap(customer_question, product):
            return waiting_for_merchant_reply(customer_question)
        # Sales objections / store policy must not produce a "checking with the team" stub.

    product_name = (getattr(product, "name", None) or "").strip()
    darija = (market or "MA") == "MA"
    if product_name:
        if darija:
            return f"واخا، أنا معاك على {product_name}. شنو بغيتي تعرف؟"
        return f"تمام، نحن معك بخصوص {product_name}. كيف يمكنني مساعدتك؟"
    if darija:
        return "واش تقدر توضّح ليا شنو كتقلّب عليه؟ نقدر نعاونك على المنتج أو أي سؤال عندك."
    return "هل يمكنك توضيح ما تبحث عنه؟ يمكنني مساعدتك في اختيار المنتج أو الإجابة على سؤالك."


def find_learned_answer(product, question: str) -> str:
    """Return a ProductKnowledgeBase answer if this question was already taught."""
    from discount.models import ProductKnowledgeBase

    if not product or not _nonempty(question):
        return ""
    entries = list(
        ProductKnowledgeBase.objects.filter(product=product)
        .exclude(answer="")
        .order_by("-updated_at")[:80]
    )
    q = _nonempty(question)
    for entry in entries:
        if _questions_match(entry.question, q, product=product) and _nonempty(entry.answer):
            return _nonempty(entry.answer)
    return ""


def knowledge_prompt_block(product) -> str:
    """Authoritative learned Q&A for injection into PRODUCT CONTEXT."""
    from discount.models import ProductKnowledgeBase

    if not product:
        return ""
    rows = list(
        ProductKnowledgeBase.objects.filter(product=product)
        .exclude(answer="")
        .order_by("-updated_at")[:_MAX_KB_PROMPT_ENTRIES]
    )
    if not rows:
        return ""
    lines = [
        "",
        "## ProductKnowledgeBase (authoritative learned Q&A — do not contradict)",
        "These answers were confirmed by the merchant. Use them verbatim in meaning.",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(f"Q{i}: {_nonempty(row.question)}")
        lines.append(f"A{i}: {_nonempty(row.answer)}")
    return "\n".join(lines)


def serialize_escalation(esc) -> dict:
    product = getattr(esc, "product", None)
    phones = getattr(esc, "_asker_phones", None)
    dup_count = int(getattr(esc, "_duplicate_count", 1) or 1)
    return {
        "id": esc.id,
        "status": esc.status,
        "customer_phone": esc.customer_phone,
        "product_id": getattr(product, "id", None),
        "product_name": (getattr(product, "name", None) or "").strip() or None,
        "question": esc.question,
        "question_text": esc.question,
        "answer": esc.answer or "",
        "created_at": esc.created_at.isoformat() if esc.created_at else None,
        "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None,
        "duplicate_count": dup_count,
        "asker_count": len(phones) if phones else 1,
    }


def _collapse_pending_escalations(rows: list) -> list:
    """Keep one pending ticket per product + semantic question (newest first)."""
    unique = []
    for esc in rows:
        merged = False
        for kept in unique:
            same_product = getattr(esc, "product_id", None) == getattr(kept, "product_id", None)
            if not same_product:
                continue
            if _questions_match(esc.question, kept.question, product=esc.product or kept.product):
                phones = getattr(kept, "_asker_phones", None) or {kept.customer_phone}
                phones.add(esc.customer_phone)
                kept._asker_phones = phones
                kept._duplicate_count = int(getattr(kept, "_duplicate_count", 1) or 1) + 1
                merged = True
                break
        if not merged:
            esc._asker_phones = {esc.customer_phone}
            esc._duplicate_count = 1
            unique.append(esc)
    return unique


def registered_owner_email(channel) -> str:
    """Account email only — never a caller-supplied address."""
    owner = getattr(channel, "owner", None)
    return _nonempty(getattr(owner, "email", None)).lower()


def _magic_signer():
    # Dot separator stays URL-path safe (Django's default ":" is not).
    return signing.TimestampSigner(salt=MAGIC_LINK_SALT, sep=".")


def build_magic_token(escalation_id: int, owner_id: int, nonce: str) -> str:
    return _magic_signer().sign_object(
        {"eid": int(escalation_id), "oid": int(owner_id), "n": str(nonce)}
    )


def decode_magic_token(token: str) -> dict:
    """
    Validate signature and 2-hour expiry. Does not consume the nonce;
    one-time use is enforced when status becomes resolved.
    """
    raw = (token or "").strip()
    if not raw:
        raise signing.BadSignature("empty token")
    payload = _magic_signer().unsign_object(raw, max_age=MAGIC_LINK_MAX_AGE_SECONDS)
    if not isinstance(payload, dict):
        raise signing.BadSignature("invalid payload")
    return payload


def _public_origin() -> str:
    return (getattr(settings, "APP_URL", None) or "https://app.waselytics.com").rstrip("/")


def magic_link_url(token: str) -> str:
    path = reverse("ai_assistant:knowledge_gap_magic", kwargs={"token": token})
    return f"{_public_origin()}{path}"


def send_escalation_magic_email(escalation) -> bool:
    """
    Email a one-time magic link to the channel owner's registered email only.
    Never accepts a custom recipient.
    """
    from discount.models import KnowledgeGapEscalation

    channel = getattr(escalation, "channel", None)
    if channel is not None and getattr(channel, "owner_id", None) and not getattr(channel, "owner", None):
        try:
            escalation = (
                KnowledgeGapEscalation.objects.select_related("channel__owner", "product")
                .filter(pk=escalation.pk)
                .first()
            ) or escalation
            channel = escalation.channel
        except Exception:
            pass
    owner = getattr(channel, "owner", None) if channel else None
    owner_id = getattr(owner, "id", None) or getattr(channel, "owner_id", None)
    to_email = registered_owner_email(channel)
    if not to_email or not owner_id:
        logger.warning(
            "knowledge gap email skipped: no registered owner email channel=%s",
            getattr(channel, "id", None),
        )
        return False

    nonce = uuid.uuid4().hex
    escalation.magic_token_nonce = nonce
    escalation.save(update_fields=["magic_token_nonce"])
    token = build_magic_token(escalation.id, int(owner_id), nonce)
    link = magic_link_url(token)
    from django.utils.html import escape

    product_name = (getattr(getattr(escalation, "product", None), "name", None) or "your product").strip()
    question = _nonempty(escalation.question)[:500]
    phone = _nonempty(escalation.customer_phone)
    masked = ("…" + phone[-4:]) if len(phone) >= 4 else phone
    product_h = escape(product_name)
    question_h = escape(question)
    masked_h = escape(masked)
    email_h = escape(to_email)
    link_h = escape(link)

    subject = f"Customer question needs an answer — {product_name}"
    text = (
        f"The WhatsApp AI could not answer a product question and needs you.\n\n"
        f"Product: {product_name}\n"
        f"Customer: {masked}\n"
        f"Question: {question}\n\n"
        f"Reply here (link expires in 2 hours, one-time use):\n{link}\n\n"
        f"This email was sent only to your account address ({to_email})."
    )
    html = (
        f"<p>The WhatsApp AI could not answer a product question and needs you.</p>"
        f"<p><strong>Product:</strong> {product_h}<br>"
        f"<strong>Customer:</strong> {masked_h}<br>"
        f"<strong>Question:</strong> {question_h}</p>"
        f"<p><a href=\"{link_h}\" style=\"display:inline-block;padding:12px 18px;"
        f"background:#7c3aed;color:#fff;border-radius:10px;text-decoration:none;"
        f"font-weight:600\">Answer this question</a></p>"
        f"<p style=\"color:#64748b;font-size:13px\">This link expires in <strong>2 hours</strong> "
        f"and can be used once. It was sent only to your registered account email "
        f"({email_h}).</p>"
        f"<p style=\"color:#94a3b8;font-size:12px\">If the button does not work, copy:<br>{link_h}</p>"
    )
    try:
        sent = send_mail(
            subject=subject,
            message=text,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[to_email],
            fail_silently=False,
            html_message=html,
        )
        logger.info(
            "knowledge gap magic email sent to owner=%s escalation=%s",
            to_email,
            escalation.id,
        )
        return bool(sent)
    except Exception as exc:
        logger.warning("knowledge gap magic email failed: %s", exc)
        return False


def load_escalation_from_magic_token(token: str):
    """
    Return (escalation, None) or (None, error_code).
    error_code: missing | expired | invalid | used | mismatch
    """
    from discount.models import KnowledgeGapEscalation

    try:
        payload = decode_magic_token(token)
    except signing.SignatureExpired:
        return None, "expired"
    except (signing.BadSignature, TypeError, ValueError):
        return None, "invalid"

    try:
        eid = int(payload.get("eid"))
        oid = int(payload.get("oid"))
    except (TypeError, ValueError):
        return None, "invalid"
    nonce = str(payload.get("n") or "")
    if not nonce:
        return None, "invalid"

    esc = (
        KnowledgeGapEscalation.objects.select_related("channel__owner", "product")
        .filter(pk=eid)
        .first()
    )
    if esc is None:
        return None, "invalid"
    if esc.status != KnowledgeGapEscalation.STATUS_PENDING:
        return None, "used"
    if (esc.magic_token_nonce or "") != nonce:
        return None, "used"
    owner_id = getattr(esc.channel, "owner_id", None)
    if owner_id != oid:
        return None, "mismatch"
    return esc, None


def mark_customer_not_waiting(channel, customer_phone: str) -> None:
    """Inbound customer message: they are chatting again, so do not barge in later."""
    from discount.models import WhatsAppCheckoutState

    if not channel or not customer_phone:
        return
    WhatsAppCheckoutState.objects.filter(
        channel=channel,
        customer_phone=str(customer_phone).strip(),
        is_waiting_for_answer=True,
    ).update(is_waiting_for_answer=False)


def _set_waiting_for_answer(channel, customer_phone: str, question: str) -> None:
    from discount.services.checkout_state import get_or_create_checkout_state

    state = get_or_create_checkout_state(channel, customer_phone)
    if state is None:
        return
    state.is_waiting_for_answer = True
    state.pending_knowledge_question = _nonempty(question)[:4000]
    state.pending_knowledge_answer = ""
    state.save(
        update_fields=[
            "is_waiting_for_answer",
            "pending_knowledge_question",
            "pending_knowledge_answer",
            "updated_at",
        ]
    )


def peek_deferred_knowledge_prompt(channel, customer_phone: str) -> str:
    """Read queued merchant answer for this LLM turn (does not consume)."""
    from discount.services.checkout_state import get_or_create_checkout_state

    if not channel or not customer_phone:
        return ""
    state = get_or_create_checkout_state(channel, str(customer_phone).strip())
    if state is None:
        return ""
    answer = _nonempty(getattr(state, "pending_knowledge_answer", ""))
    question = _nonempty(getattr(state, "pending_knowledge_question", ""))
    if not answer:
        return ""
    q_line = f"The customer had asked: {question}\n" if question else ""
    return (
        "MERCHANT KNOWLEDGE UPDATE (integrate naturally in this reply — do not say "
        "you just received a note from the team unless it fits the dialect):\n"
        f"{q_line}"
        f"Confirmed answer: {answer}\n"
        "Weave this fact into the conversation naturally. Do not dump it as a raw memo."
    )


def clear_deferred_knowledge_answer(channel, customer_phone: str) -> None:
    """Consume the queued merchant answer after the AI has used it in a reply."""
    from discount.models import WhatsAppCheckoutState

    if not channel or not customer_phone:
        return
    WhatsAppCheckoutState.objects.filter(
        channel=channel,
        customer_phone=str(customer_phone).strip(),
    ).exclude(pending_knowledge_answer="").update(
        pending_knowledge_answer="",
        pending_knowledge_question="",
        is_waiting_for_answer=False,
    )


def handle_escalate_missing_info(
    channel,
    customer_phone: str,
    customer_question: str,
    product=None,
) -> dict[str, Any]:
    """
    Sales-agent tool handler. Opens a KnowledgeGapEscalation only for factual
    product-spec gaps. Compound messages are split; catalog facts, store
    policies, and sales objections never become tickets.
    """
    from discount.models import ChatSession

    question = _nonempty(customer_question)
    if not question:
        return {
            "success": False,
            "status": "error",
            "message": (
                "customer_question is empty. Call escalate_missing_info again with "
                "the customer's exact question."
            ),
        }
    if not channel or not customer_phone:
        return {
            "success": False,
            "status": "error",
            "message": "Channel or customer phone missing. Tell the customer you will check with the team.",
        }

    phone = str(customer_phone).strip()
    if product is None:
        try:
            session = (
                ChatSession.objects.filter(
                    channel=channel,
                    customer_phone=phone,
                    is_expired=False,
                    is_completed=False,
                )
                .select_related("active_product")
                .first()
            )
            product = getattr(session, "active_product", None) if session else None
        except Exception:
            product = None

    atoms = split_atomic_questions(question)
    if len(atoms) == 1:
        return _escalate_single_question(channel, phone, atoms[0], product, notify=True)

    parts = [
        _escalate_single_question(channel, phone, atom, product, notify=False)
        for atom in atoms
    ]
    created = [p for p in parts if p.get("status") == "escalated"]
    known = [p for p in parts if p.get("status") == "already_known"]
    pending = [p for p in parts if p.get("status") in ("escalated", "already_pending")]
    sales = [p for p in parts if p.get("status") == "sales_objection"]
    policies = [p for p in parts if p.get("status") == "store_policy"]
    gap_questions = [p.get("question") for p in pending if p.get("question")]
    if created:
        first_id = created[0].get("escalation_id")
        try:
            from discount.models import KnowledgeGapEscalation

            esc = KnowledgeGapEscalation.objects.filter(pk=first_id).first()
            if esc:
                _notify_new_escalation(
                    esc,
                    note_question="; ".join(gap_questions or atoms)[:180],
                )
        except Exception as notify_err:
            logger.debug("compound knowledge gap notify: %s", notify_err)
        try:
            wait_q = (gap_questions[0] if gap_questions else "") or atoms[0]
            _set_waiting_for_answer(channel, phone, wait_q)
        except Exception:
            pass

    ids = [p.get("escalation_id") for p in parts if p.get("escalation_id")]
    catalog_answers = [
        _nonempty(p.get("answer")) for p in known if p.get("answer")
    ]
    catalog_block = "\n".join(
        f"- {p.get('question')}: {p.get('answer')}"
        for p in known
        if p.get("answer")
    )
    sales_listed = " | ".join(p.get("question") or "" for p in sales if p.get("question"))
    policy_listed = " | ".join(p.get("question") or "" for p in policies if p.get("question"))
    msg_bits = []
    if catalog_block:
        msg_bits.append(
            "CATALOG FACTS — you MUST tell the customer these now. "
            "Do not skip them. Do not escalate them:\n" + catalog_block
        )
    if sales_listed:
        msg_bits.append(
            "SALES OBJECTIONS — do NOT escalate and do NOT say you are checking "
            "with the team. Handle with empathy and the product's general benefits: "
            + sales_listed
        )
    if policy_listed:
        msg_bits.append(
            "STORE POLICY — do NOT escalate as missing product knowledge. "
            "Quote Delivery / Return-Warranty from PRODUCT CONTEXT: " + policy_listed
        )
    if not pending:
        answers = " | ".join(catalog_answers)
        status = "already_known" if known else (
            "sales_objection" if sales else ("store_policy" if policies else "not_a_gap")
        )
        return {
            "success": True,
            "status": status,
            "answer": answers,
            "parts": parts,
            "message": "\n".join(msg_bits) or (
                "Nothing to escalate. Answer from PRODUCT CONTEXT. "
                "Do NOT say you are checking with the team."
            ),
        }
    gap_listed = " | ".join(gap_questions) if gap_questions else " | ".join(atoms)
    msg_bits.append(
        f"FACTUAL KNOWLEDGE GAPS only — {len(pending)} question(s) went to the merchant: "
        f"{gap_listed}. For THESE only: tell the customer IN THEIR DIALECT that you are "
        "checking with the team. Do NOT invent sensitive-skin or other missing specs."
    )
    status = "escalated" if created else "already_pending"
    return {
        "success": True,
        "status": status,
        "escalation_id": ids[0] if ids else None,
        "escalation_ids": ids,
        "answer": "\n".join(catalog_answers),
        "parts": parts,
        "message": "\n".join(msg_bits),
    }


def _notify_new_escalation(esc, note_question: str = "") -> None:
    channel = getattr(esc, "channel", None)
    phone = getattr(esc, "customer_phone", "")
    question = note_question or _nonempty(getattr(esc, "question", ""))
    try:
        send_escalation_magic_email(esc)
    except Exception as mail_err:
        logger.warning("send_escalation_magic_email: %s", mail_err)
    try:
        from discount.whatssapAPI.process_messages import _add_ai_action_note, send_socket

        _add_ai_action_note(
            channel,
            phone,
            f"Knowledge gap escalated: {question[:180]}",
            author_name="AI Agent",
        )
        team_id = getattr(channel, "owner_id", None) or (
            getattr(channel, "owner", None) and getattr(channel.owner, "id", None)
        )
        if team_id:
            send_socket(
                "knowledge_gap",
                {
                    "channel_id": getattr(channel, "id", None),
                    "customer_phone": phone,
                    "escalation_id": esc.id,
                    "question": question[:300],
                    "product_id": getattr(esc.product, "id", None) if esc.product else None,
                    "product_name": (getattr(esc.product, "name", None) or "")[:120],
                },
                group_name=f"team_updates_{team_id}",
            )
    except Exception as notify_err:
        logger.debug("knowledge gap notify: %s", notify_err)


def _escalate_single_question(
    channel,
    phone: str,
    question: str,
    product=None,
    *,
    notify: bool = True,
) -> dict[str, Any]:
    from discount.models import KnowledgeGapEscalation

    question = _nonempty(question)
    known = find_learned_answer(product, question) if product else ""
    if not known:
        known = find_catalog_answer(product, question)
    if known:
        return {
            "success": True,
            "status": "already_known",
            "question": question,
            "answer": known,
            "message": (
                "This question is already answered from the product catalog or "
                "ProductKnowledgeBase. Reply to the customer using this answer. "
                "Do NOT say you are checking with the team.\n"
                f"Answer: {known}"
            ),
        }

    skipped = _clause_skip_ticket_status(question, product)
    if skipped:
        return skipped
    if not is_factual_product_spec_gap(question, product):
        return {
            "success": True,
            "status": "not_a_gap",
            "question": question,
            "message": (
                "DO NOT ESCALATE. This is not a missing factual product specification. "
                "Answer from PRODUCT CONTEXT or handle it as a sales question. "
                "Do NOT say you are checking with the team."
            ),
        }

    pending = KnowledgeGapEscalation.objects.filter(
        channel=channel,
        status=KnowledgeGapEscalation.STATUS_PENDING,
    ).order_by("-created_at")
    if product is not None:
        pending = pending.filter(product_id=product.id)
    else:
        pending = pending.filter(customer_phone=phone, product__isnull=True)
    for old in list(pending[:40]):
        _materialize_split_pending(old)
        try:
            old.refresh_from_db()
        except Exception:
            continue
        _drop_if_not_factual_pending(old)
    pending = KnowledgeGapEscalation.objects.filter(
        channel=channel,
        status=KnowledgeGapEscalation.STATUS_PENDING,
    ).order_by("-created_at")
    if product is not None:
        pending = pending.filter(product_id=product.id)
    else:
        pending = pending.filter(customer_phone=phone, product__isnull=True)
    for esc in pending[:40]:
        if _questions_match(esc.question, question, product=product):
            try:
                _set_waiting_for_answer(channel, phone, question)
            except Exception:
                pass
            return {
                "success": True,
                "status": "already_pending",
                "question": question,
                "escalation_id": esc.id,
                "message": (
                    "This question is already with the team. Politely tell the customer "
                    "(in their dialect) that you are still checking and will get back to them. "
                    "Do NOT invent an answer."
                ),
            }

    esc = KnowledgeGapEscalation.objects.create(
        channel=channel,
        customer_phone=phone,
        product=product,
        question=question[:4000],
        status=KnowledgeGapEscalation.STATUS_PENDING,
    )
    try:
        _set_waiting_for_answer(channel, phone, question)
    except Exception as wait_err:
        logger.debug("set waiting_for_answer: %s", wait_err)

    if notify:
        _notify_new_escalation(esc, note_question=question)

    logger.info(
        "escalate_missing_info id=%s channel=%s phone=%s product=%s q=%r",
        esc.id,
        getattr(channel, "id", None),
        phone,
        getattr(product, "id", None),
        question[:80],
    )
    return {
        "success": True,
        "status": "escalated",
        "question": question,
        "escalation_id": esc.id,
        "message": (
            "Escalated to the merchant. Politely tell the customer IN THEIR DIALECT "
            "that you are checking with the team and will get back to them shortly. "
            "Do NOT guess or invent product facts."
        ),
    }


def _drop_if_not_factual_pending(esc) -> bool:
    """Delete a pending ticket that is catalog-known, a sales objection, or store policy."""
    q = _nonempty(getattr(esc, "question", None))
    product = getattr(esc, "product", None)
    if q and is_factual_product_spec_gap(q, product):
        if not find_catalog_answer(product, q) and not find_learned_answer(product, q):
            return False
    try:
        esc.delete()
        return True
    except Exception:
        return False


def _materialize_split_pending(esc) -> None:
    """Turn a stored compound ticket into one pending row per unknown question."""
    atoms = split_atomic_questions(getattr(esc, "question", "") or "")
    if len(atoms) < 2:
        return
    product = getattr(esc, "product", None)
    unknown = []
    for atom in atoms:
        if find_learned_answer(product, atom) or find_catalog_answer(product, atom):
            continue
        if not is_factual_product_spec_gap(atom, product):
            continue
        unknown.append(atom)
    if not unknown:
        try:
            esc.delete()
        except Exception:
            pass
        return
    try:
        esc.question = unknown[0][:4000]
        esc.save(update_fields=["question"])
    except Exception:
        return
    for atom in unknown[1:]:
        try:
            _escalate_single_question(
                esc.channel,
                esc.customer_phone,
                atom,
                product,
                notify=False,
            )
        except Exception:
            logger.debug("materialize split pending failed", exc_info=True)


def list_pending_escalations(channel_id: Optional[int] = None, limit: int = 50) -> dict:
    from discount.models import KnowledgeGapEscalation

    qs = (
        KnowledgeGapEscalation.objects.filter(status=KnowledgeGapEscalation.STATUS_PENDING)
        .select_related("product", "channel")
        .order_by("-created_at")
    )
    if channel_id is not None:
        qs = qs.filter(channel_id=channel_id)
    rows = list(qs[: max(1, min(int(limit or 50), 100))])
    for esc in rows:
        _materialize_split_pending(esc)
        try:
            esc.refresh_from_db(fields=["question"])
        except Exception:
            continue
        _drop_if_not_factual_pending(esc)
    if rows:
        qs2 = (
            KnowledgeGapEscalation.objects.filter(status=KnowledgeGapEscalation.STATUS_PENDING)
            .select_related("product", "channel")
            .order_by("-created_at")
        )
        if channel_id is not None:
            qs2 = qs2.filter(channel_id=channel_id)
        rows = list(qs2[: max(1, min(int(limit or 50), 100))])
    collapsed = _collapse_pending_escalations(rows)
    return {
        "success": True,
        "count": len(collapsed),
        "escalations": [serialize_escalation(e) for e in collapsed],
    }


def pending_escalation_status(channel_id: Optional[int] = None) -> dict:
    """Lightweight poll payload for the dashboard Action Required button."""
    data = list_pending_escalations(channel_id, limit=100)
    count = data.get("count") or 0
    return {
        "success": True,
        "has_pending": count > 0,
        "pending_count": count,
    }


def upsert_knowledge_entry(product, question: str, answer: str):
    from discount.models import ProductKnowledgeBase

    if not product or not _nonempty(question) or not _nonempty(answer):
        return None
    existing = list(
        ProductKnowledgeBase.objects.filter(product=product).order_by("-updated_at")[:80]
    )
    for entry in existing:
        if _questions_match(entry.question, question, product=product):
            entry.question = _nonempty(question)[:4000]
            entry.answer = _nonempty(answer)[:8000]
            entry.save(update_fields=["question", "answer", "updated_at"])
            return entry
    return ProductKnowledgeBase.objects.create(
        product=product,
        question=_nonempty(question)[:4000],
        answer=_nonempty(answer)[:8000],
    )


def _invalidate_magic_link(esc) -> None:
    esc.magic_token_nonce = ""


def _deliver_resolved_answer(channel, customer_phone: str, question: str, answer_text: str) -> None:
    """Send now if the customer is waiting; otherwise queue for the next AI reply."""
    from discount.models import WhatsAppCheckoutState
    from discount.services.checkout_state import get_or_create_checkout_state

    state = None
    waiting = False
    try:
        state = get_or_create_checkout_state(channel, customer_phone)
        waiting = bool(state and getattr(state, "is_waiting_for_answer", False))
    except Exception:
        state = None
    if waiting:
        try:
            from discount.whatssapAPI.process_messages import send_automated_response

            send_automated_response(
                customer_phone,
                [{"type": "text", "content": answer_text, "delay": 0}],
                channel=channel,
            )
        except Exception as send_err:
            logger.warning("knowledge gap WhatsApp send failed: %s", send_err)
        if state is not None:
            state.is_waiting_for_answer = False
            state.pending_knowledge_answer = ""
            state.pending_knowledge_question = ""
            state.save(
                update_fields=[
                    "is_waiting_for_answer",
                    "pending_knowledge_answer",
                    "pending_knowledge_question",
                    "updated_at",
                ]
            )
        return
    if state is not None:
        state.is_waiting_for_answer = False
        state.pending_knowledge_question = _nonempty(question)[:4000]
        state.pending_knowledge_answer = answer_text[:8000]
        state.save(
            update_fields=[
                "is_waiting_for_answer",
                "pending_knowledge_question",
                "pending_knowledge_answer",
                "updated_at",
            ]
        )
    elif getattr(channel, "id", None):
        WhatsAppCheckoutState.objects.filter(
            channel_id=channel.id,
            customer_phone=customer_phone,
        ).update(
            is_waiting_for_answer=False,
            pending_knowledge_question=_nonempty(question)[:4000],
            pending_knowledge_answer=answer_text[:8000],
        )


def _close_matching_pending(primary, answer_text: str, kb) -> int:
    """Resolve duplicate pending tickets for the same product fact."""
    from discount.models import KnowledgeGapEscalation

    now = timezone.now()
    qs = KnowledgeGapEscalation.objects.filter(
        channel_id=primary.channel_id,
        status=KnowledgeGapEscalation.STATUS_PENDING,
    ).exclude(pk=primary.pk)
    if primary.product_id:
        qs = qs.filter(product_id=primary.product_id)
    else:
        qs = qs.filter(product__isnull=True)
    closed = 0
    delivered_phones = {primary.customer_phone}
    for sib in qs.select_related("product", "channel")[:40]:
        if not _questions_match(
            sib.question, primary.question, product=primary.product or sib.product
        ):
            continue
        sib.answer = answer_text[:8000]
        sib.status = KnowledgeGapEscalation.STATUS_RESOLVED
        sib.resolved_at = now
        _invalidate_magic_link(sib)
        fields = ["answer", "status", "resolved_at", "magic_token_nonce"]
        if kb is not None:
            sib.knowledge_entry = kb
            fields.append("knowledge_entry")
        sib.save(update_fields=fields)
        closed += 1
        if sib.customer_phone not in delivered_phones:
            try:
                _deliver_resolved_answer(
                    sib.channel, sib.customer_phone, sib.question, answer_text
                )
            except Exception:
                logger.debug("duplicate pending deliver failed", exc_info=True)
            delivered_phones.add(sib.customer_phone)
    return closed


def resolve_knowledge_escalation(
    escalation_id,
    answer: str,
    *,
    channel_id: Optional[int] = None,
) -> dict:
    """
    Merchant answered: always save Q&A to ProductKnowledgeBase.

    If checkout ``is_waiting_for_answer`` is True, WhatsApp the customer now.
    If False, queue the answer for the next LLM reply (natural integration).
    Resolving invalidates the magic-link token (one-time use).
    """
    from discount.models import KnowledgeGapEscalation, WhatsAppCheckoutState
    from discount.services.checkout_state import get_or_create_checkout_state

    answer_text = _nonempty(answer)
    if not answer_text:
        return {"success": False, "error": "answer is required"}
    try:
        esc_id = int(escalation_id)
    except (TypeError, ValueError):
        return {"success": False, "error": "invalid escalation_id"}

    qs = KnowledgeGapEscalation.objects.select_related("product", "channel")
    if channel_id is not None:
        qs = qs.filter(channel_id=channel_id)
    esc = qs.filter(pk=esc_id).first()
    if esc is None:
        return {"success": False, "error": "escalation not found"}
    if esc.status == KnowledgeGapEscalation.STATUS_RESOLVED:
        return {"success": False, "error": "This question was already answered.", "code": "used"}

    kb = None
    if esc.product_id:
        try:
            kb = upsert_knowledge_entry(esc.product, esc.question, answer_text)
        except Exception as kb_err:
            logger.warning("ProductKnowledgeBase save failed: %s", kb_err)

    waiting = False
    state = None
    try:
        state = get_or_create_checkout_state(esc.channel, esc.customer_phone)
        waiting = bool(state and getattr(state, "is_waiting_for_answer", False))
    except Exception as st_err:
        logger.debug("checkout waiting flag: %s", st_err)

    sent = False
    send_error = ""
    deferred = False
    if waiting:
        try:
            from discount.whatssapAPI.process_messages import send_automated_response

            sent = bool(
                send_automated_response(
                    esc.customer_phone,
                    [{"type": "text", "content": answer_text, "delay": 0}],
                    channel=esc.channel,
                )
            )
        except Exception as send_err:
            send_error = str(send_err)
            logger.warning("knowledge gap WhatsApp send failed: %s", send_err)
        if state is not None:
            state.is_waiting_for_answer = False
            state.pending_knowledge_answer = ""
            state.pending_knowledge_question = ""
            state.save(
                update_fields=[
                    "is_waiting_for_answer",
                    "pending_knowledge_answer",
                    "pending_knowledge_question",
                    "updated_at",
                ]
            )
    else:
        deferred = True
        if state is not None:
            state.is_waiting_for_answer = False
            state.pending_knowledge_question = _nonempty(esc.question)[:4000]
            state.pending_knowledge_answer = answer_text[:8000]
            state.save(
                update_fields=[
                    "is_waiting_for_answer",
                    "pending_knowledge_question",
                    "pending_knowledge_answer",
                    "updated_at",
                ]
            )
        elif esc.channel_id:
            WhatsAppCheckoutState.objects.filter(
                channel_id=esc.channel_id,
                customer_phone=esc.customer_phone,
            ).update(
                is_waiting_for_answer=False,
                pending_knowledge_question=_nonempty(esc.question)[:4000],
                pending_knowledge_answer=answer_text[:8000],
            )

    now = timezone.now()
    esc.answer = answer_text[:8000]
    esc.status = KnowledgeGapEscalation.STATUS_RESOLVED
    esc.resolved_at = now
    _invalidate_magic_link(esc)
    if kb is not None:
        esc.knowledge_entry = kb
    update_fields = ["answer", "status", "resolved_at", "magic_token_nonce"]
    if kb is not None:
        update_fields.append("knowledge_entry")
    esc.save(update_fields=update_fields)
    try:
        closed = _close_matching_pending(esc, answer_text, kb)
        if closed:
            logger.info("closed %s duplicate knowledge-gap tickets for #%s", closed, esc.id)
    except Exception:
        logger.debug("close matching pending failed", exc_info=True)

    try:
        from discount.whatssapAPI.process_messages import _add_ai_action_note, send_socket

        route = "WhatsApp sent now" if sent else ("queued for next AI reply" if deferred else "saved")
        _add_ai_action_note(
            esc.channel,
            esc.customer_phone,
            f"Merchant answered knowledge gap #{esc.id}; {route}.",
            author_name="AI Copilot",
        )
        team_id = getattr(esc.channel, "owner_id", None) or (
            getattr(esc.channel, "owner", None) and getattr(esc.channel.owner, "id", None)
        )
        if team_id:
            send_socket(
                "knowledge_gap_resolved",
                {
                    "channel_id": esc.channel_id,
                    "customer_phone": esc.customer_phone,
                    "escalation_id": esc.id,
                },
                group_name=f"team_updates_{team_id}",
            )
    except Exception:
        pass

    if sent:
        msg = "Answer saved to ProductKnowledgeBase and sent to the customer on WhatsApp."
    elif deferred:
        msg = (
            "Answer saved to ProductKnowledgeBase. The customer is chatting, so it will be "
            "woven into the next AI reply instead of an immediate WhatsApp ping."
        )
    elif kb:
        msg = "Answer saved. WhatsApp send failed — retry from the inbox."
    else:
        msg = "Escalation resolved."

    return {
        "success": True,
        "escalation": serialize_escalation(esc),
        "whatsapp_sent": bool(sent),
        "deferred_to_next_reply": bool(deferred),
        "learned": bool(kb is not None),
        "knowledge_entry_id": getattr(kb, "id", None),
        "send_error": send_error or None,
        "message": msg,
    }


def pending_escalations_prompt_hint(channel_id: Optional[int]) -> str:
    if channel_id is None:
        return ""
    data = list_pending_escalations(channel_id, limit=8)
    count = data.get("count") or 0
    if not count:
        return "Pending knowledge-gap escalations: 0."
    lines = [
        f"Pending knowledge-gap escalations: {count}. "
        "Use get_pending_escalations (or list_pending_escalations) to show them. "
        "When the merchant provides an answer, call resolve_escalation with "
        "question_id and merchant_answer."
    ]
    for row in data.get("escalations") or []:
        lines.append(
            f"- #{row.get('id')} [{row.get('product_name') or 'no product'}] "
            f"{row.get('customer_phone')}: {(row.get('question') or '')[:120]}"
        )
    return "\n".join(lines)
