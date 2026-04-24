import logging
import os
import random
import re
import requests
from django.conf import settings
from litellm import completion

logger = logging.getLogger(__name__)

# Default name when voice reply is on but no persona name (e.g. Chuck)
AI_AGENT_VOICE_DEFAULT_NAME = "Chuck"
# Random names when voice reply is off, by market (Arabic names per region)
AI_AGENT_RANDOM_NAMES_MA = [
    "سميع", "يوسف", "ليلى", "هبة", "عمر", "نادية", "كريم", "سلمى",
    "أدم", "لينا", "رامي", "سيمو", "أمين", "سارة", "خالد", "فاطمة",
    "محمد", "مريم", "أحمد", "زينب", "علي", "حسن", "إيمان", "طارق",
]
AI_AGENT_RANDOM_NAMES_SA = [
    "عبدالله", "محمد", "خالد", "فهد", "سعود", "نورة", "هند", "لمى",
    "عمر", "سارة", "راشد", "ماجد", "ناصر", "منى", "لطيفة", "فيصل",
    "تركي", "عبير", "بدر", "جواهر", "سلطان", "هيفاء", "مشعل", "ريم",
]
# SA and GCC use the same Gulf names
AI_AGENT_RANDOM_NAMES_GCC = AI_AGENT_RANDOM_NAMES_SA
MARKET_AGENT_NAMES = {
    "MA": AI_AGENT_RANDOM_NAMES_MA,
    "SA": AI_AGENT_RANDOM_NAMES_SA,
    "GCC": AI_AGENT_RANDOM_NAMES_GCC,
}

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
MODEL_CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
MODEL_GPT4O = "gpt-4o"

# Strict context window management (keep most recent messages only).
MAX_CHAT_HISTORY_MESSAGES = 6

def _trim_conversation_messages(conversation_messages, limit=MAX_CHAT_HISTORY_MESSAGES):
    if not conversation_messages:
        return []
    if limit <= 0:
        return []
    return list(conversation_messages)[-int(limit):]

def _estimate_payload_tokens(messages):
    # Fast approximation for debugging; OpenAI tokenization differs by model.
    try:
        total_chars = 0
        for m in (messages or []):
            total_chars += len((m.get("content") or "").strip())
        return max(1, total_chars // 4)
    except Exception:
        return 0

def summarize_customer_memory_from_messages(messages, model=None):
    """Summarize older chat history into compact customer facts."""
    if not messages:
        return ""
    api_key = get_api_key()
    if not api_key:
        return ""

    compact_lines = []
    for m in messages:
        role = (m.get("role") or "").strip().lower()
        if role not in ("customer", "agent"):
            continue
        body = (m.get("body") or "").strip()
        if not body or body == "[media]":
            continue
        compact_lines.append(f"{role}: {body}")
    if not compact_lines:
        return ""

    prompt = (
        "Summarize the key extracted facts from this conversation history. "
        "Focus ONLY on the customer's personal details, preferences, pain points "
        "(e.g., skin type, specific needs), and the product they want. "
        "Output as a brief bulleted list. If a fact is uncertain, omit it. "
        "Keep it under 8 bullets."
    )
    payload = {
        "model": model or getattr(settings, "OPENAI_SUMMARY_MODEL", None) or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "\n".join(compact_lines[-120:])},
        ],
        "max_tokens": 220,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=35)
        if r.status_code != 200:
            logger.warning("memory summary API error %s: %s", r.status_code, (r.text or "")[:300])
            return ""
        data = r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return text[:1800]
    except Exception as e:
        logger.warning("memory summary failed: %s", e)
        return ""

# Cheap model for WhatsApp AI Sentinel (intent check before expensive sales agent)
SENTINEL_SYSTEM_PROMPT = (
    "You are an Intent Analyzer for an e-commerce store. Read the user's messages. "
    "Determine if they are genuinely interested in the product/shipping/pricing "
    "(even if they ask many questions or seem hesitant), OR if they are a troll, spammer, "
    "or deliberately wasting time with unrelated topics. "
    "Reply with exactly ONE WORD: 'SERIOUS' or 'SPAM'."
)


def get_sentinel_model():
    return getattr(settings, "OPENAI_SENTINEL_MODEL", None) or "gpt-4o-mini"


def evaluate_sentinel_intent(user_message_texts):
    """
    Cheap LLM gate: classify last N user-only messages.
    user_message_texts: list of str, chronological (oldest first).
    Returns 'SERIOUS' or 'SPAM'. Defaults to 'SERIOUS' on API/parse errors (do not block buyers).
    """
    if not user_message_texts:
        return "SERIOUS"
    api_key = get_api_key()
    if not api_key:
        logger.warning("evaluate_sentinel_intent: no OPENAI_API_KEY; defaulting to SERIOUS")
        return "SERIOUS"
    combined = "\n---\n".join(str(t).strip() for t in user_message_texts if str(t).strip())
    if not combined:
        return "SERIOUS"
    model = get_sentinel_model()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SENTINEL_SYSTEM_PROMPT},
            {"role": "user", "content": f"User messages (most recent last):\n{combined}"},
        ],
        "max_tokens": 10,
        "temperature": 0,
    }
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning("evaluate_sentinel_intent HTTP %s: %s", resp.status_code, resp.text[:300])
            return "SERIOUS"
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        raw_words = (text or "").strip().upper().split()
        if not raw_words:
            return "SERIOUS"
        first = re.sub(r"[^A-Z]", "", raw_words[0])
        if first == "SPAM":
            return "SPAM"
        # Model may reply "THE WORD IS SPAM" — check any token
        if any(re.sub(r"[^A-Z]", "", w) == "SPAM" for w in raw_words[:5]):
            return "SPAM"
        return "SERIOUS"
    except Exception as e:
        logger.warning("evaluate_sentinel_intent failed: %s", e)
        return "SERIOUS"


# --- Moroccan Franco (Latin script) → Arabic Darija preprocessing for Sales Agent ---
def is_primarily_latin_franco(text):
    """
    Heuristic: Latin-script Moroccan Franco — has several Latin letters and no Arabic script.
    """
    if not text or not str(text).strip():
        return False
    if re.search(r"[\u0600-\u06FF]", text):
        return False
    return len(re.findall(r"[a-zA-Z]", text)) >= 3


def _format_last_three_for_franco_translator(conversation):
    """Last up to 3 turns for translator context (customer / assistant labels)."""
    if not conversation:
        return "(no prior context)"
    tail = conversation[-3:]
    lines = []
    for m in tail:
        role = "Customer" if m.get("role") == "customer" else "Assistant"
        body = (m.get("body") or "")[:1200]
        lines.append(f"{role}: {body}")
    return "\n".join(lines)


def translate_franco_to_darija_arabic(user_franco_message, last_three_context_block):
    """
    Cheap gpt-4o-mini pass: Franco Latin → Arabic script Darija for the main Sales Agent.
    On any failure, returns the original message.
    """
    raw = (user_franco_message or "").strip()
    if not raw:
        return raw
    api_key = get_api_key()
    if not api_key:
        return raw
    model = getattr(settings, "OPENAI_FRANCO_TRANSLATOR_MODEL", None) or "gpt-4o-mini"
    system_content = (
        "You are a Moroccan Darija translator. "
        f"Here is the recent conversation context:\n{last_three_context_block}\n\n"
        f"The user just replied with this Franco message: '{raw}'. "
        "Based on the context, translate their exact intent into standard Arabic script (Moroccan Darija). "
        "Reply ONLY with the translated text, nothing else."
    )
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_content}],
        "max_tokens": 500,
        "temperature": 0.2,
    }
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=25,
        )
        if resp.status_code != 200:
            logger.warning("translate_franco_to_darija_arabic HTTP %s: %s", resp.status_code, (resp.text or "")[:300])
            return raw
        data = resp.json()
        out = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        out = (out or "").strip()
        return out if out else raw
    except Exception as e:
        logger.warning("translate_franco_to_darija_arabic failed: %s", e)
        return raw


def apply_franco_translation_to_conversation(conversation):
    """
    If the last customer message looks like Franco (Latin), replace it with Arabic Darija translation.
    conversation: list of {"role": "customer"|"agent", "body": str} (same shape as LLM pipeline).
    """
    if not conversation:
        return conversation
    conv = list(conversation)
    i = len(conv) - 1
    while i >= 0 and conv[i].get("role") != "customer":
        i -= 1
    if i < 0:
        return conv
    raw = (conv[i].get("body") or "").strip()
    if not raw or raw == "[media]":
        return conv
    if not is_primarily_latin_franco(raw):
        return conv
    ctx = _format_last_three_for_franco_translator(conv)
    translated = translate_franco_to_darija_arabic(raw, ctx)
    if translated and translated.strip():
        conv[i] = {**conv[i], "body": translated.strip()}
    return conv


def get_api_key():
    """Retrieve the OpenAI API key from Django settings or environment."""
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


def get_anthropic_api_key():
    """Retrieve the Anthropic API key from Django settings or environment."""
    return getattr(settings, "ANTHROPIC_API_KEY", None) or os.environ.get("ANTHROPIC_API_KEY", "")


def _normalize_dialect_text(value):
    return (value or "").strip()


def _dialect_from_phone(customer_phone):
    s = (customer_phone or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+212") or s.startswith("212"):
        return "Moroccan Darija"
    if s.startswith("+966") or s.startswith("966") or s.startswith("+971") or s.startswith("971"):
        return "Saudi/Gulf Arabic"
    return "Standard Arabic"


def resolve_ai_brain(node, customer_phone):
    """
    Dynamic brain selector:
    - Determine dialect from node (explicit) then phone fallback.
    - Route Moroccan/North African dialects to Claude Sonnet, else GPT-4o.
    Returns: (selected_model, target_dialect)
    """
    # Priority 1: explicit merchant override from Node Builder
    if node is not None:
        eng = (getattr(node, "ai_engine", None) or "").strip().upper()
        if eng == "GPT_4O":
            return (MODEL_GPT4O, "Standard Arabic")
        if eng == "CLAUDE_3_5":
            return (MODEL_CLAUDE_SONNET, "Moroccan Darija")

    node_dialect = ""
    if node is not None:
        node_dialect = (
            getattr(node, "dialect", None)
            or getattr(node, "node_language", None)
            or ""
        )
    node_dialect = _normalize_dialect_text(node_dialect)
    if node_dialect and node_dialect.lower() != "auto":
        target_dialect = node_dialect
    else:
        target_dialect = _dialect_from_phone(customer_phone)

    d = target_dialect.lower()
    is_maghreb = any(
        k in d
        for k in (
            "moroccan",
            "darija",
            "north african",
            "maghreb",
            "algerian",
            "tunisian",
            "ar_ma",
            "ar_dz",
            "ar_tn",
        )
    )
    selected_model = MODEL_CLAUDE_SONNET if is_maghreb else MODEL_GPT4O
    return (selected_model, target_dialect)


def _prepare_litellm_provider_key(selected_model):
    m = (selected_model or "").lower()
    if "claude" in m:
        anth = get_anthropic_api_key()
        if not anth:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        os.environ["ANTHROPIC_API_KEY"] = anth
    else:
        oa = get_api_key()
        if not oa:
            raise ValueError("OPENAI_API_KEY is not set.")
        os.environ["OPENAI_API_KEY"] = oa


def build_system_prompt(language_hint="auto"):
    """
    Build the system prompt that instructs the AI how to behave
    as a customer-service assistant.
    """
    return (
        "You are a professional customer-service assistant for a COD (Cash on Delivery) "
        "e-commerce business. Your job is to help agents craft the perfect reply to customers "
        "on WhatsApp.\n\n"
        "Rules:\n"
        "- Analyse the conversation history provided and generate ONE concise, professional reply.\n"
        "- Match the language the customer is using (Arabic, French, English, etc.).\n"
        "- Be polite, helpful, and solution-oriented.\n"
        "- If the customer is angry, de-escalate with empathy.\n"
        "- If the customer asks about order status, tracking, or delivery, acknowledge and offer help.\n"
        "- Keep the reply short (1-3 sentences max) unless more detail is clearly needed.\n"
        "- Do NOT include greetings like 'Dear customer' unless the conversation just started.\n"
        "- Do NOT add quotes, markdown, or formatting — return plain text only.\n"
        "- Return ONLY the suggested reply text, nothing else."
    )


def build_messages_payload(conversation_messages, custom_instruction=None):
    """
    Convert the conversation history into the OpenAI messages format.

    conversation_messages: list of dicts with keys:
        - role: 'customer' or 'agent'
        - body: message text
    """
    system_prompt = build_system_prompt()
    if custom_instruction:
        system_prompt += f"\n\nAdditional instruction from the agent: {custom_instruction}"

    messages = [{"role": "system", "content": system_prompt}]

    for msg in conversation_messages:
        if msg["role"] == "customer":
            messages.append({"role": "user", "content": msg["body"]})
        else:
            messages.append({"role": "assistant", "content": msg["body"]})

    if not conversation_messages or conversation_messages[-1]["role"] == "agent":
        messages.append({
            "role": "user",
            "content": "(The customer is waiting for a reply. Suggest what the agent should say next.)",
        })

    return messages


def generate_reply(conversation_messages, custom_instruction=None, model=None):
    """
    Call OpenAI API and return the suggested reply.

    Returns: dict with keys 'reply', 'prompt_tokens', 'completion_tokens', 'model'
    Raises: ValueError on configuration errors, RuntimeError on API errors.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "OpenAI API key is not configured. "
            "Set OPENAI_API_KEY in your .env file."
        )

    model = model or DEFAULT_MODEL
    messages = build_messages_payload(conversation_messages, custom_instruction)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenAI API request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to OpenAI API. Check your internet connection.")

    if response.status_code == 401:
        raise ValueError("Invalid OpenAI API key. Please check your OPENAI_API_KEY.")
    if response.status_code == 429:
        raise RuntimeError("OpenAI rate limit reached. Please wait a moment and try again.")
    if response.status_code != 200:
        logger.error("OpenAI API error %s: %s", response.status_code, response.text[:500])
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")

    data = response.json()
    choice = data.get("choices", [{}])[0]
    reply_text = choice.get("message", {}).get("content", "").strip()
    usage = data.get("usage", {})

    return {
        "reply": reply_text,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model": model,
    }


# --- Sales agent with function calling (order extraction) ---

# Market-specific rules: greeting, consent ask, nicknames, tone (used when AI agent node has market target)
# MARKET_CONFIG = {
#     "MA": {  # المغرب
#         "greeting": "السلام عليكم، كيداير أخي/أختي لاباس عليك؟",
#         "consent_ask": "تبارك الله عليك! واش نبدأو في إجراءات الطلب باش توصلك الأمانة؟",
#         "nicknames": "(خويا العزيز، لالة، الصديق ديالي)",
#         "tone_desc": "Moroccan Darija (Friendly & Hrifa)",
#         "data_request": f"على الراس والعين!  ، باش نخرج ليك الإرسالية اليوم، من فضلك أرسل لي: \n- الاسم الكامل \n- المدينة \n- العنوان بالتفصيل",
#     },
#     "SA": {  # السعودية
#         "greeting": "يا هلا والله ومسهلا، كيف حالك يا غالي؟ عساك بخير؟",
#         "consent_ask": "أبشر بسعدك! تحب نعتمد لك الطلب الحين ونجهز لك الشحنة؟",
#         "nicknames": "(يا غالي، يا هلا، أبشر، تامر أمر)",
#         "data_request": f"حيّاك الله . عشان نعتمد طلبك ونشحنه لك اليوم، يا ليت ترسل لي: \n- الاسم الكريم \n- المدينة والحي \n- العنوان بالكامل",
#         "tone_desc": "Saudi/Gulf Dialect (Polite, Respectful, Generous)",
#     },
# }

# The New Dynamic Market Config (Vibe & Goals)
MARKET_CONFIG = {
    "MA": {  # المغرب
       
        "tone_desc": "Warm, street-smart (Hrifa), and highly professional Moroccan Darija.",
        "nicknames": "Feel free to naturally sprinkle words like (خويا، لالة، على الراس والعين، الأمانة، تبارك الله) but NEVER force them or repeat them.",
        "greeting": "Greet the customer warmly in Darija, keeping it very short and natural. Vary your greeting every time.",
        "consent_ask": "Politely ask if they are ready to start the order process to get their package delivered. Do not use the exact same phrase twice.",
        "data_request": "Ask for [Full Name, City, Detailed Address] in ONE single, friendly Moroccan sentence. Explain you need it to ship the order today.",
        "order_confirmation_fallback": "تم تسجيل طلبك، غادي نتواصلو معاك قريباً. على الراس والعين.",
    },
    "SA": {  # السعودية
       
        "tone_desc": "Polite, respectful, generous, and welcoming Saudi/Gulf dialect.",
        "nicknames": "Use natural Saudi phrases like (يا غالي، أبشر بسعدك، تامر أمر، حياك الله) but keep it subtle and varied.",
        "greeting": "Give a warm Gulf-style welcome. Keep it concise. Never repeat the same exact greeting.",
        "consent_ask": "Ask for their permission to confirm the order and prepare the shipment in a respectful Saudi tone.",
        "data_request": "Request [Full Name, City/Neighborhood, Address] in ONE clear, welcoming sentence so you can dispatch their order immediately.",
        "order_confirmation_fallback": "تم تسجيل طلبك، سنتواصل معك قريباً إن شاء الله. حياك الله.",
    },
    "GCC": {  # Gulf (UAE, Kuwait, Bahrain, Qatar, Oman) — same vibe as SA
        "market_identity": "Gulf Arab Market",
        "tone_desc": "Polite, respectful, generous, and welcoming Saudi/Gulf dialect.",
        "nicknames": "Use natural Gulf phrases like (يا غالي، أبشر، حياك الله) but keep it subtle and varied.",
        "greeting": "Give a warm Gulf-style welcome. Keep it concise. Never repeat the same exact greeting.",
        "consent_ask": "Ask for their permission to confirm the order and prepare the shipment in a respectful tone.",
        "data_request": "Request [Full Name, City/Neighborhood, Address] in ONE clear, welcoming sentence so you can dispatch their order immediately.",
        "order_confirmation_fallback": "تم تسجيل طلبك، سنتواصل معك قريباً إن شاء الله. حياك الله.",
    },
}
DEFAULT_MARKET = "MA"

# Handover message by market (Supervisor Agent — transfer to human)
HANDOVER_MESSAGES = {
    "MA": "خويا العزيز، باش نضمن ليك أحسن خدمة، غادي نحولك دابا لعند واحد من المتخصصين ديالنا يكمل معاك، دقيقة ويكون معاك.",
    "SA": "يا غالي، ودي أخدمك بأفضل شكل، بحولك الآن للزميل المختص بيفيدك أكثر في هذي النقطة، ثواني ويكون معك.",
}
HANDOVER_MESSAGES["GCC"] = HANDOVER_MESSAGES["SA"]

# Sales intent: if the user says these, NEVER hand over — force sales mode (AI responds).
# Includes greetings (new conversation / re-engagement) so we don't repeat handover message.
SALES_INTENT_PATTERNS = re.compile(
    r"(?:أريد|طلب|سماعات|شحال|سعر|بكم|نشتري|بغيت|"
    r"واش نقدر نطلب|كم الثمن|شحال هاد|بغيت نشري|نشري|جيبلي|"
    r"مرحبا|مرحبا بك|أهلا|أهلين|سلام|السلام عليكم|"
    r"hi|hello|hey|bonjour|salut|"
    r"price|how much|order|buy|want to buy|product)",
    re.IGNORECASE | re.UNICODE,
)

def message_shows_sales_intent(text):
    """True if the message indicates sales/inquiry (greeting, price, product, order). Used to re-enable AI after handover."""
    if not text or not isinstance(text, str):
        return False
    return bool(SALES_INTENT_PATTERNS.search(text.strip()))


# Detect if a message is the handover reply (so we can stop repeating it).
HANDOVER_MESSAGE_FINGERPRINT_RE = re.compile(
    r"(?:يرجى التواصل مع أحد ممثلينا|أحد ممثلينا|نحولك دابا|بحولك الآن)",
    re.UNICODE,
)

# --- Intelligent Handover (Supervisor Agent) ---
# Hand over ONLY when: (1) customer asks for human, or (2) complaint, or (3) refund.
# Complaint / refund keywords (do not hand over for generic anger or price/quality)
HANDOVER_COMPLAINT_REFUND_PATTERNS = re.compile(
    r"\b(complaint|refund|return (my )?money|استرداد|استرجاع|شكوى|شكاية|"
    r"reclamation|remboursement|reimburse|get (my )?money back|"
    r"ريد فلوسي|استرداد المبلغ|إرجاع|reclamer|plainte)\b",
    re.IGNORECASE | re.UNICODE,
)
# Human / manager / real person (semantic: many variants — "I want to talk to a person" ~ "anyone real here?")
HANDOVER_HUMAN_REQUEST_PATTERNS = re.compile(
    r"\b(human|real person|actual person|live agent|agent|manager|supervisor|"
    r"someone real|anyone real|talk to a person|speak to (a )?person|"
    r"want to talk to (a )?person|is there anyone real|real (agent|human)|"
    r"anyone real here|somebody real|a real person|"
    r"أحد حقيقي|شخص حقيقي|مدير|مشرف|واحد فعلي|تكلم مع إنسان|"
    r"واش في بوت|هذا بوت|مع انسان|إنسان|بديت نكلم انسان|في حد هنا|واحد منكم|"
    r"personne réelle|parler à un humain|vrai conseiller|vrai personne|"
    r"quelqu'un de réel|un humain)\b",
    re.IGNORECASE,
)
# "You don't understand" / repeated question / unsuccessful cycle
HANDOVER_MISUNDERSTAND_PATTERNS = re.compile(
    r"\b(you don't understand|you didn't understand|wrong answer|not what i (asked|want)|"
    r"ماتفهمنيش|ما فهمتش|غلط|ماشي اللي بغيت|"
    r"tu (ne )?comprends pas|pas compris|mauvaise réponse)\b",
    re.IGNORECASE,
)

# Price or product-quality objection: do NOT hand over — sales agent handles these
PRICE_QUALITY_OBJECTION_PATTERNS = re.compile(
    r"(?:price|expensive|cheap|cost|prix|cher|ghalia|غالية|غالي|غلى|مكلف|ثمن|ثمنه|السعر|سعره|"
    r"شحال|كم الثمن|باهي|باهية|غالين|"
    r"quality|original|أصلي|اصلي|جودة|qualité|authentic|counterfeit|تقليد|"
    r"worth it|value for money|ضمان|warranty)",
    re.IGNORECASE | re.UNICODE,
)

# Minimum length to compare "same answer" (avoid false positive on "ok")
MIN_ANSWER_LENGTH_FOR_SAME_CHECK = 15
# Similarity threshold: last 2 bot replies considered "same" if ratio >= this
SAME_ANSWER_RATIO_THRESHOLD = 0.75


def _is_price_or_quality_objection(text):
    """
    True if the message is mainly about price (expensive, غالية) or product quality (original?, جودة).
    These are sales objections — do not trigger handover; the sales agent handles them.
    """
    if not text or not isinstance(text, str):
        return False
    return bool(PRICE_QUALITY_OBJECTION_PATTERNS.search(text))


def _is_misunderstand_message(text):
    """
    True if the customer is saying the AI didn't understand / wrong answer (e.g. "you don't understand", "ماتفهمنيش").
    Do NOT hand over for this — the AI should ask them to rephrase instead.
    """
    if not text or not isinstance(text, str):
        return False
    return bool(HANDOVER_MISUNDERSTAND_PATTERNS.search(text))


def _normalize_for_similarity(text):
    """Normalize text for rough similarity (strip, lower, collapse spaces)."""
    if not text or not isinstance(text, str):
        return ""
    return " ".join(re.sub(r"\s+", " ", text.strip().lower()).split())


def _last_n_agent_messages_are_handover(conversation_messages, n=2):
    """True if the last n agent messages all look like the handover reply (infinite loop guard)."""
    if not conversation_messages or n < 1:
        return False
    agent_bodies = [
        (m.get("body") or "").strip()
        for m in reversed(conversation_messages)
        if m.get("role") == "agent"
    ]
    if len(agent_bodies) < n:
        return False
    for i in range(n):
        if not HANDOVER_MESSAGE_FINGERPRINT_RE.search(agent_bodies[i]):
            return False
    return True


def _last_two_agent_messages_same(conversation_messages):
    """True if the bot gave (nearly) the same answer in the last 2 turns (unsuccessful cycle)."""
    if not conversation_messages or len(conversation_messages) < 4:
        return False
    agent_bodies = [
        (m.get("body") or "").strip()
        for m in reversed(conversation_messages)
        if m.get("role") == "agent"
    ]
    if len(agent_bodies) < 2:
        return False
    a, b = _normalize_for_similarity(agent_bodies[0]), _normalize_for_similarity(agent_bodies[1])
    if len(a) < MIN_ANSWER_LENGTH_FOR_SAME_CHECK or len(b) < MIN_ANSWER_LENGTH_FOR_SAME_CHECK:
        return False
    if a == b:
        return True
    # Jaccard-like: words in common / total unique words
    wa, wb = set(a.split()), set(b.split())
    if not wa:
        return False
    inter = len(wa & wb)
    union = len(wa | wb)
    if union == 0:
        return False
    ratio = inter / union
    return ratio >= SAME_ANSWER_RATIO_THRESHOLD


def classify_user_intent_for_handover(last_user_message, use_llm=True):
    """
    Classify for handover. Returns (should_handover: bool, reason: str).
    Hand over ONLY for: Human_Request, Complaint, or Refund (never for anger alone or price/quality).
    """
    text = (last_user_message or "").strip()
    if not text or len(text) < 2:
        return (False, "")

    # Explicit request for human → hand over
    if HANDOVER_HUMAN_REQUEST_PATTERNS.search(text):
        return (True, "Customer asked for human or manager")

    # Price/quality only → never hand over
    if _is_price_or_quality_objection(text):
        return (False, "")

    # Complaint/refund keywords (and not price/quality) → hand over
    if HANDOVER_COMPLAINT_REFUND_PATTERNS.search(text):
        return (True, "Complaint or refund (keyword)")

    if not use_llm:
        return (False, "")

    api_key = get_api_key()
    if not api_key:
        return (False, "")

    prompt = (
        "Classify the customer message into exactly ONE intent. Reply with only the intent word, nothing else.\n"
        "Intents: Human_Request, Complaint, Refund, Price_Quality_Objection, SALES_CHAT, Other.\n"
        "Rules:\n"
        "- STRICT: If the user is asking about price, products, or how to order (e.g. شحال، بكم، أريد، طلب، سماعات، نشتري، بغيت), "
        "NEVER classify as ANGER or COMPLAINT. Classify as SALES_CHAT.\n"
        "- Human_Request: they explicitly ask to talk to a real person, manager, or human agent (not just frustration).\n"
        "- Complaint: they complain about service, delivery, wrong item, support, or process (not price or product questions).\n"
        "- Refund: they ask for refund, return, money back, استرداد, استرجاع, remboursement.\n"
        "- Price_Quality_Objection: only about price (expensive, غالية) or product quality (original?). Do NOT use Complaint/Refund for these.\n"
        "- SALES_CHAT: asking price, product info, how to buy, want to order. Do NOT use Complaint or Refund for these.\n"
        "- Other: normal chat or unclear. Do NOT use Complaint or Refund for simple anger or frustration.\n"
        "Hand over to human ONLY for Human_Request, Complaint, or Refund. Never hand over for SALES_CHAT, Price_Quality_Objection, or Other.\n\n"
        f"Message: {text[:500]}"
    )
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": DEFAULT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 25,
                "temperature": 0,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return (False, "")
        intent = (resp.json().get("choices", [{}])[0].get("message", {}).get("content") or "").strip().upper()
        if not intent:
            return (False, "")
        if "PRICE_QUALITY" in intent or "OTHER" in intent or "SALES_CHAT" in intent:
            return (False, "")
        # Only these three intents trigger handover
        if "HUMAN" in intent or "REQUEST" in intent:
            return (True, "Customer asked for human or manager")
        if "COMPLAINT" in intent:
            return (True, "Complaint")
        if "REFUND" in intent:
            return (True, "Refund request")
    except Exception as e:
        logger.debug("classify_user_intent_for_handover LLM failed: %s", e)
    return (False, "")


def should_handover(conversation_history, market=None, use_llm_intent=True):
    """
    Handover: transfer to human ONLY when (1) customer asked for human, or (2) complaint, or (3) refund.
    Returns (should_handover: bool, reason: str).

    Logic: Sales intent ALWAYS wins. If the user shows buying keywords, never hand over.
    Safety: If we already sent the handover message 2+ times in a row, stop and let the AI answer.
    """
    if not conversation_history:
        return (False, "")
    last_user = None
    for m in reversed(conversation_history):
        if m.get("role") == "customer":
            last_user = (m.get("body") or "").strip()
            break
    if not last_user:
        return (False, "")

    # 1) HIGH-INTENT OVERRIDE: Sales intent ALWAYS takes priority. Never hand over for buying keywords.
    if SALES_INTENT_PATTERNS.search(last_user):
        return (False, "")

    # 2) SAFETY FILTER: If we already repeated the handover message 2+ times in a row, stop — let AI answer.
    if _last_n_agent_messages_are_handover(conversation_history, n=2):
        return (False, "")

    # Never hand over for "you don't understand" / wrong answer — AI asks to rephrase
    if _is_misunderstand_message(last_user):
        return (False, "")

    # Never hand over for price/quality only — sales agent handles
    if _is_price_or_quality_objection(last_user):
        return (False, "")

    # Single source of handover decision + reason
    handover, reason = classify_user_intent_for_handover(last_user, use_llm=use_llm_intent)
    if handover:
        return (True, reason or "Complaint or refund")
    return (False, "")


def get_handover_message(market=None):
    """Return the handover message for the given market (Simo MA / Abu Saud SA)."""
    key = (market or "").strip().upper() if market else ""
    return HANDOVER_MESSAGES.get(key) or HANDOVER_MESSAGES[DEFAULT_MARKET]


# Mandatory variables that MUST be filled before any order confirmation (strict slot-filling)
MANDATORY_ORDER_SLOTS = ("customer_name", "customer_phone", "customer_address")
# For backend: we have customer_phone from sender; we require name + (city or full address)

# Goal-oriented sales stages (state machine)
SALES_GOAL_STAGES = (
    "STAGE_1_GREETING",   # Building rapport
    "STAGE_2_QUALIFYING", # Asking for city/need
    "STAGE_3_PRESENTING", # Highlighting product benefits
    "STAGE_4_NEGOTIATION",# Handling price objections
    "STAGE_5_CLOSING",    # Getting address and confirming
)
# Legacy funnel stages (kept for backward compatibility)
SALES_FUNNEL_STAGES = ("hook_empathy", "discovery", "soft_close", "order_capture") + SALES_GOAL_STAGES
STAGE_TAG_RE = re.compile(
    r"\[STAGE:\s*(" + "|".join(re.escape(s) for s in SALES_FUNNEL_STAGES) + r")\]\s*$",
    re.IGNORECASE,
)


def _get_market_config(market=None):
    """Resolve market key to config dict. Defaults to MA if unknown."""
    key = (market or "").strip().upper() if market else ""
    if key in MARKET_CONFIG:
        return MARKET_CONFIG[key]
    return MARKET_CONFIG[DEFAULT_MARKET]


def get_order_confirmation_fallback(market=None):
    """Return a short order-confirmation fallback message matching the market/tone (client tone_desc)."""
    m = _get_market_config(market)
    return m.get("order_confirmation_fallback") or "تم تسجيل طلبك. سنتواصل معك قريباً."


# Dialect hints: customer used these in their messages → prefer this market for tone
_MOROCCAN_HINTS = re.compile(
    r"\b(واش|دابا|بغيت|غادي|خويا|لالة|تبارك الله|الأمانة|على الراس|ماشي مشكل|فين|واش تقدر|بغيتي|كيفاش|وصلات|طلبيتي)\b",
    re.IGNORECASE,
)
_SAUDI_GCC_HINTS = re.compile(
    r"\b(وش|أبشر|حياك الله|يا غالي|تامر أمر|إن شاء الله|ماشاء الله|كيف|وين|طلبي|رقم الطلب)\b",
    re.IGNORECASE,
)


def infer_market_from_conversation(conversation_messages):
    """
    Infer market (tone) from prior customer messages. Use when the user has chatted before
    so we reply in the same dialect they use (AR_MA → MA, AR_SA → SA, etc.).
    conversation_messages: list of {"role": "customer"|"agent", "body": "..."}.
    Returns 'MA', 'SA', 'GCC', or None if unclear.
    """
    if not conversation_messages:
        return None
    customer_text = " ".join(
        (m.get("body") or "").strip()
        for m in conversation_messages
        if m.get("role") == "customer" and (m.get("body") or "").strip()
    )
    if not customer_text or customer_text == "[media]":
        return None
    ma_count = len(_MOROCCAN_HINTS.findall(customer_text))
    sa_count = len(_SAUDI_GCC_HINTS.findall(customer_text))
    if ma_count > sa_count:
        return "MA"
    if sa_count > ma_count:
        return "SA"
    return None


def market_from_resolved_dialect(dialect_display: str):
    """
    Map a human-readable dialect label (from voice / hierarchy) to MA / SA / GCC
    so MARKET_CONFIG tone_desc aligns with TTS dialect (overrides phone-based market when voice-first).
    """
    from discount.models import VOICE_DIALECT_CHOICES, dialect_key_to_display

    d = (dialect_display or "").strip().lower()
    if not d:
        return None
    for key, label in VOICE_DIALECT_CHOICES:
        if (label or "").strip().lower() == d:
            if key == 'MA_DARIJA':
                return "MA"
            if key == 'SA_ARABIC':
                return "SA"
            if key == 'GULF_ARABIC':
                return "GCC"
            if key in ('EG_ARABIC', 'LEV_ARABIC', 'MSA'):
                return "SA"
            if key == 'OTHER':
                return "SA"
            return "MA"
    # Fuzzy fallback
    if 'moroccan' in d or 'darija' in d:
        return 'MA'
    if 'saudi' in d:
        return 'SA'
    if 'gulf' in d:
        return 'GCC'
    if 'levant' in d or 'egyptian' in d:
        return 'SA'
    canonical_ma = (dialect_key_to_display('MA_DARIJA') or '').strip().lower()
    if canonical_ma and d == canonical_ma:
        return 'MA'
    return None


def infer_market_from_phone(phone):
    """
    Infer market from customer phone number (first-time chatters, or when no conversation tone).
    +966 → SA, +212 → MA, +971/+973/+965/+974/+968 → GCC.
    Returns 'MA', 'SA', 'GCC', or None.
    """
    if not phone:
        return None
    s = (phone or "").strip().replace(" ", "").replace("-", "")
    if not s.startswith("+"):
        if s.startswith("966"):
            return "SA"
        if s.startswith("212"):
            return "MA"
        if s.startswith(("971", "973", "965", "974", "968")):
            return "GCC"
        return None
    if s.startswith("+966"):
        return "SA"
    if s.startswith("+212"):
        return "MA"
    if s.startswith(("+971", "+973", "+965", "+974", "+968")):
        return "GCC"
    return None


def get_agent_name_for_node(voice_reply_on, persona=None, market=None):
    """
    Return the agent's display name for the AI prompt.
    - If voice reply is ON: use the selected voice/persona name, or Chuck if none.
    - If voice reply is OFF: return a random name from the market list (MA = Moroccan Arabic, SA/GCC = Gulf Arabic).
    persona: VoicePersona instance or None (with .name attribute).
    market: 'MA', 'SA', or 'GCC' for name list; defaults to MA if unknown.
    """
    if voice_reply_on:
        if persona and getattr(persona, "name", None) and str(persona.name).strip():
            return str(persona.name).strip()
        return AI_AGENT_VOICE_DEFAULT_NAME
    key = (market or "").strip().upper() if market else ""
    names = MARKET_AGENT_NAMES.get(key) if key in MARKET_AGENT_NAMES else AI_AGENT_RANDOM_NAMES_MA
    return random.choice(names)


# Injected into sales system prompt so the AI resumes context when the customer returns with a greeting
CONTEXT_RESUMPTION_RULE = """
## CRITICAL RULE — CONTEXT RESUMPTION (greetings / returning customers)
Before answering any greeting (e.g. مرحبا, Hello, السلام, Hi, أهلاً), you MUST analyze the conversation history provided above.
- If you see that you were already discussing a specific product or order with this customer previously: DO NOT start a new generic greeting (e.g. "How can I help you?" / "كيفاش نقدر نعاونك؟"). Instead, warmly welcome them back and IMMEDIATELY tie your response to the previous context. Example (Darija): "مرحبا بك من جديد! واش باغي نزيد نشرح ليك على [Product Name] اللي كنا كنهضرو عليه، ولا بغيتي نسجلو الطلبية دابا؟" Example (English): "Welcome back! Do you want to pick up where we left off with [product], or shall we go ahead and place the order now?"
- If the database/context has 0 past messages (truly new customer): use your standard initial welcome greeting only then.
"""

# Used when TTS voice dialect is not Moroccan Darija — removes Darija-only resumption examples.
CONTEXT_RESUMPTION_RULE_TTS_NON_MA = """
## CRITICAL RULE — CONTEXT RESUMPTION (greetings / returning customers)
Before answering any greeting (e.g. مرحبا, Hello, السلام, Hi, أهلاً), you MUST analyze the conversation history provided above.
- If you were already discussing a specific product or order: DO NOT use a generic support-style greeting. Welcome them back and tie your reply to that context using ONLY the dialect from SYSTEM OVERRIDE (no Moroccan Darija phrasing unless that is your OVERRIDE dialect). Example (English): "Welcome back! Do you want to pick up where we left off with [product], or shall we place the order now?"
- If there are no prior messages (new customer): use a short welcome in your OVERRIDE dialect only.
"""


def _canonical_moroccan_darija_label() -> str:
    from discount.models import VOICE_DIALECT_DEFAULT, dialect_key_to_display

    return (dialect_key_to_display(VOICE_DIALECT_DEFAULT) or "Moroccan Darija").strip()


def _is_moroccan_darija_dialect_label(voice_dialect: str) -> bool:
    if not voice_dialect or not str(voice_dialect).strip():
        return False
    return str(voice_dialect).strip().lower() == _canonical_moroccan_darija_label().lower()


def _build_critical_audio_scripting_block(resolved_dialect: str) -> str:
    """
    Voice-note / TTS mode: human spoken script, not catalog or markdown.
    Placed at the very top of the system prompt when voice_notes_mode is on.
    """
    rd = (resolved_dialect or "").strip() or "the configured Arabic dialect"
    return (
        "CRITICAL AUDIO SCRIPTING MODE: Your output will be read aloud by a Text-to-Speech engine "
        f"in the {rd} dialect.\n"
        "- RULE 1: Speak like a real human sending a casual WhatsApp voice note.\n"
        "- RULE 2: NEVER use numbered lists, bullet points, or markdown formatting.\n"
        "- RULE 3: Do not list full catalogs of products. Instead, summarize benefits naturally "
        "(e.g., instead of '1. Argan Oil 200DH', say 'We have an amazing Argan oil that is perfect for "
        "your skin, and it is only 200 Dirhams').\n"
        "- RULE 4: Use natural filler words and pauses appropriate for "
        f"{rd} to sound authentic.\n"
        "- RULE 5 (ARABIC FLOW & PACING): Never chain Arabic list items with consecutive commas only — "
        "use conjunctions like 'و' (and) or 'أو' (or) between items so TTS sounds fluid, not robotic. "
        "BAD: 'كريمات، زيوت، عطور. ماذا تفضل؟' GOOD: 'عندنا كريمات وزيوت وعطور، وش اللي تفضل تشوفه؟' "
        "Weave the final question or CTA into the same sentence.\n"
        "- RULE 6: CRITICAL AUDIO SCRIPTING MODE overrides any later instructions that conflict "
        "(e.g. numbered catalog steps, markdown, or 'list every product').\n\n"
        "---\n\n"
    )


def _build_moroccan_tts_system_override(vd: str) -> str:
    return (
        f"SYSTEM OVERRIDE: You are a native speaker of {vd}. You must write your response strictly and entirely in the {vd} dialect. "
        "Your output must sound natural and native for Text-to-Speech.\n\n---\n\n"
    )


def _build_non_moroccan_tts_system_override(vd: str) -> str:
    return (
        f"SYSTEM OVERRIDE: You are a native speaker of {vd}. You must write your response strictly and entirely in the {vd} dialect. \n"
        "NEGATIVE CONSTRAINT: Do NOT use any Moroccan Darija words (like كيفاش, كفاش, بزاف, ديال, واش). "
        "If the dialect is Saudi, use Saudi words (like وشلونك، أبشر، شلون أقدر أخدمك). "
        "Your output must naturally match the chosen dialect 100%.\n\n---\n\n"
    )


def _strip_moroccan_default_instructions_for_tts(system: str) -> str:
    """
    Remove or neutralize Moroccan-default sales copy so it does not fight TTS dialect
    (e.g. Saudi voice + Darija examples in the base prompt).
    """
    s = system.replace(CONTEXT_RESUMPTION_RULE, CONTEXT_RESUMPTION_RULE_TTS_NON_MA)
    # Master closer: tone lock (persona name is expanded in the f-string, not literal {name})
    s = re.sub(
        r"If tone is Moroccan Darija, reply ONLY in Moroccan Darija for the whole chat — do NOT switch to فصحى \(MSA\), Saudi, or other dialects\. "
        r"If tone is Saudi/Gulf, stay in that dialect only\. Never mix dialects\. Never forget your persona \([^)]+\) or the tone_desc\.",
        "Follow the SYSTEM OVERRIDE dialect at the top for the whole chat — do NOT switch to فصحى (MSA) or another regional dialect. "
        "Never mix dialects. Never forget your persona or the tone_desc.",
        s,
    )
    s = re.sub(
        r"Within the tone_desc, mirror the user's energy and style\. If they speak Moroccan Darija, reply in authentic Moroccan Darija "
        r"and keep it for all subsequent messages\. NEVER mix dialects \(e\.g\., no Saudi words for a Moroccan user\)\.",
        "Within the tone_desc, mirror the user's energy. ALWAYS stay in the SYSTEM OVERRIDE dialect — even if the customer writes "
        "Moroccan Darija, you must answer in your OVERRIDE dialect for TTS. NEVER mix dialects.",
        s,
    )
    ex_darija = (
        "Example: 'مرحبا بك! [SPLIT] واش بغيتي تعرف تفاصيل المنتج؟ [SPLIT] راه عليه عرض اليوم.'"
    )
    ex_neutral = (
        "Example (translate to OVERRIDE dialect, not Darija unless OVERRIDE is Moroccan Darija): "
        "'Hi! [SPLIT] Want product details? [SPLIT] There is a promo today.'"
    )
    s = s.replace(ex_darija, ex_neutral)
    # Master closer: identity line that mentions Moroccan Darija / Saudi
    s = s.replace(
        "This tone was chosen from their prior messages or phone region. You MUST use it for the ENTIRE chat. Do NOT switch to another dialect or فصحى mid-conversation. If this is Moroccan tone, keep every reply in Moroccan Darija. If Saudi/Gulf, keep every reply in that dialect. Never mix.",
        "You MUST use the SYSTEM OVERRIDE dialect for the ENTIRE chat. Do NOT switch to another dialect or فصحى mid-conversation. Never mix.",
    )
    # Master closer / playbook: Darija-only negotiation grammar block
    s = re.sub(
        r"\n- \*\*Darija \(MA\) — grammar and logic:\*\*.+?(?=\n\*\*5\. Order Tracking)",
        "\n",
        s,
        flags=re.DOTALL,
    )
    s = re.sub(
        r"\n- \*\*Darija logic and grammar:\*\*[^\n]+",
        "\n- **Dialect consistency:** Follow vocabulary and grammar of the SYSTEM OVERRIDE dialect only.",
        s,
    )
    # Universal sales prompt: mirror rule → voice-locked
    s = s.replace(
        "- **CRITICAL:** Detect the user's dialect (e.g., Moroccan, Saudi, Egyptian, English, French) and EXACTLY mirror their language and dialect. ",
        "- **CRITICAL:** Your written Arabic dialect is FIXED by SYSTEM OVERRIDE for TTS. Mirror the customer's energy, but if they write Moroccan Darija and your OVERRIDE is Saudi/Gulf, you MUST still respond in Saudi/Gulf — never output Darija. For French/English messages, you may reply in that language; otherwise prefer OVERRIDE Arabic. ",
    )
    # Negotiation prompt tone line
    s = s.replace(
        "- MATCH THE CUSTOMER'S LANGUAGE EXACTLY. If they speak Moroccan Darija, reply in perfect, natural Moroccan Darija. If they speak French or Classical Arabic, match it. Act like a real human, not an AI.",
        "- Write strictly in the SYSTEM OVERRIDE dialect for TTS. You may use French or English if the customer writes primarily in those languages. Act like a real human, not an AI.",
    )
    # Good endings: Darija bullet lists (master + universal prompts; 3-space indent)
    s = re.sub(
        r"3\. \*\*GOOD ENDINGS \(use these patterns — vary the wording\):\*\*\n(?:   - .+\n)+",
        "3. **GOOD ENDINGS:** Use short, natural closing questions in your SYSTEM OVERRIDE dialect only "
        "(not Darija unless OVERRIDE is Moroccan Darija). Vary wording; never use generic support sign-offs.\n",
        s,
    )
    _hes_line = (
        '5. **HESITATION HANDLING:** If the user hesitates, do NOT say "take your time". Instead, use a soft diagnostic question '
        'that keeps momentum: "واش هو الثمن اللي مخلّيك متردد؟" (Is it the price making you hesitate?) or '
        '"واش بغيتي تشوف شهادات ناس جربوه؟" (Want to see testimonials from people who tried it?)'
    )
    s = s.replace(
        _hes_line,
        "5. **HESITATION HANDLING:** Ask ONE short diagnostic in your OVERRIDE dialect; keep momentum.",
    )
    return s


def _debug_print_sales_agent_system_prompt(messages, voice_dialect=None, voice_notes_mode=None, output_language=None):
    """Print exact system prompt sent to OpenAI (QA: verify dialect injection)."""
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content") or ""
            print("=" * 88)
            print("[OpenAI Sales Agent] EXACT SYSTEM PROMPT (pre-request)")
            print(
                f"[meta] voice_dialect={voice_dialect!r} voice_notes_mode={voice_notes_mode!r} "
                f"output_language={output_language!r}"
            )
            print("=" * 88)
            print(content)
            print("=" * 88)
            return


# def _master_sales_closer_prompt(product_context, trust_score=0, sales_stage=None, sentiment=None, market=None, agent_name=None):
#     product_block = (product_context or "General product.").strip()
#     ts = max(0, min(10, int(trust_score) if trust_score is not None else 0))
#     m = _get_market_config(market)
#     greeting = m.get("greeting", "")
#     consent_ask = m.get("consent_ask", "")
#     nicknames = m.get("nicknames", "")
#     tone_desc = m.get("tone_desc", "Friendly, local dialect")
#     name = (agent_name or "").strip() or "Chuck"
#     data_request = m.get("data_request", "")

#     return f"""
# # ROLE: Elite Sales Closer (Market-Aware)
# You are a master salesman. Your goal is to build a relationship first, then provide value, then close the deal.

# # INTENT ANALYSIS (SEMANTIC — DO NOT RELY ON KEYWORDS ONLY)
# Analyze the meaning of the message, then act:
# 1. **[NEW_SALE/INQUIRY]:** User asks about price, products, availability, or shows interest (e.g. "Hi", "I want", "How much") → Respond as Elite Sales Closer. Use Value Sandwich & Handshake.
# 2. **[ORDER_TRACKING]:** User asks about package or delivery status → Call track_order(customer_phone) and answer helpfully. Do not repeat the same phrasing.
# 3. **[FORMAL_COMPLAINT]:** User is ANGRY or has a specific issue with a RECEIVED product (wrong item, broken, etc.) → Apologize sincerely and use [HANDOVER].
# 4. **[HUMAN_REQUEST]:** User explicitly asks for a real person → Use [HANDOVER].
# 5. **[UNCLEAR]:** Message is a typo, single word, or unclear → Ask warmly: "سمح ليا ما فهمتكش مزيان، واش ممكن توضح ليا كيفاش نقدر نعاونك؟"

# # CORE POLICIES
# - **Anti-Repetition:** Never send the same response twice. If the user repeats themselves, change your wording or offer a new solution.
# - **Never "Contact Representative" for sales:** You are the salesperson. Your goal is to keep the conversation alive. Do not deflect to "contact a representative" when they ask about price or products.
# - **No Surrender:** If a session ended, start a new one seamlessly. The customer must never feel they hit a dead end.
# - DO NOT use nicknames more than once in the same conversation. use it smartly and only when it makes sense. not in every message.


# # YOUR IDENTITY (HUMAN, NOT BOT)
# - **Your name is {name}.** You are a real human sales rep for this store (e.g. Simo for Morocco, Abu Saud for Saudi). Think and respond as a person would on WhatsApp: warm, street-smart, helpful.
# - Never say you are an AI, bot, or assistant. Never say "I'm an automated system" or "I'm here to help as your AI." You are {name}, a human. If asked "are you a bot?", answer naturally (e.g. "I'm {name}, I work with the team here").
# - Write like a human: short messages, occasional typos or casual phrasing are fine. No corporate or robotic tone.


 
# # MARKET RULES (STRICT — USE THIS TONE & PHRASES)
# - **Target market:** {tone_desc}
# - **Greeting (use when starting or first contact):** {greeting}
# - **Consent ask (use after providing value, before collecting name/address/phone):** {consent_ask}
# - **Nicknames (use to build warmth, one per exchange):** {nicknames}
# - **Data request (use after consent ask, before collecting name/address/phone):** {data_request}
# You MUST use the greeting, consent phrase, and nicknames from this market. but do not use the same nickname more than once in the same conversation. use it smartly and only when it makes sense. not in every message. Do not mix markets (e.g. do not use Saudi phrases when market is Morocco).
# - **DO NOT ASK USER TO ORDER MORE THAN ONCE IN THE SAME CONVERSATION.**


# # THE CONSENT GATE (CRITICAL LOGIC)
# - **Rule #1:** You are STRICTLY FORBIDDEN from asking for the customer's name, city, or address immediately after answering their questions.
# - **Rule #2:** After providing value, you MUST ask for explicit permission to start the order using the consent phrase above (if you have not already asked for it) .
# - **Rule #3:** Only if they say "Yes", "Ok", "Safi", "أبشر", or "Order it", or something like that then move to collecting their name.
# - **Rule #4:** If they say "No", "I don't want it", "Too expensive", or "Not now", then offer a 10% discount ,and provide them with the new price after discount, and ask if they want to order now using the consent phrase above.


# # STRATEGY 1: THE HANDSHAKE (MANDATORY START)
# - If this is the FIRST message or a price inquiry: **NEVER** give the price immediately.
# - **Rule:** Start with the market greeting above. Then acknowledge the product: e.g. "تواصلتي معانا بخصوص [Product Name] ياك؟" (MA) or similar in the market tone.
# - **Wait:** Let them reply to the greeting. This is the "Social Handshake."

# # STRATEGY 2: THE VALUE SANDWICH (PRICE LOGIC)
# - Once the greeting is done, if they ask for price: [Benefit 1] + [Price] + [Benefit 2 + Benefit 3 + Free Shipping]. Ease of use and fast results if applicable.

# # STRATEGY 3: THE TRUST SCORE & DATA GATEKEEPER (STRICT LOGIC)
# - **Current trust_score: {ts}**.
# - **REQUIRED FOR ORDER (exactly 4):** (1) **Product** — you MUST know which product they are ordering (from product context above: use the product name or SKU); (2) **Name** — full name or first name only; (3) **Phone** — we have it from the chat but confirm with the customer; (4) **Address** — delivery address. City is NOT required; if the customer provides city, store it in the city field.
# - **FORBIDDEN:** Do NOT confirm an order or say "Order Registered" if any required field is missing: **product** (from context), name, or phone.
# - **PRODUCT GATE (STRICT):** NEVER output [ORDER_DATA] or call save_order/record_order without a product. The product comes from the product context above (this conversation is about that product). Always include **sku** (if known from context) or **product_name** (from the product context) in [ORDER_DATA] and in save_order. If the customer has not clearly indicated which product they want (e.g. they asked about multiple products), ask "Which product would you like to order?" before registering.
# - **SEQUENCE:** When the customer wants to order, ensure you have the product from context, then ask ONE BY ONE: (1) Name (full name or first name), (2) Delivery address (where to deliver ; city is optional). Do not skip; once you have **product + name + address** (+ phone from chat but confirm with the customer), you MUST output [ORDER_DATA] (including sku or product_name) and confirm the order.

# # ORDER CONFIRMATION (ACTION-FIRST — STRICT)
# - **Atomic rule:** You are STRICTLY FORBIDDEN from saying "Your order is registered" / "تم تسجيل طلبك" / "Order Registered" or any variation UNLESS you also output in the SAME response the hidden technical tag: [ORDER_DATA: {{"name": "...", "phone": "...", "address": "...", "city": "..." (optional), "sku": "..." or "product_name": "..." (REQUIRED — from product context)}}]. The confirmation text and the [ORDER_DATA] tag must be generated together in one response; if the tag is missing, the order does not exist in the system.
# - **Data extraction:** Required: **product** (sku or product_name from the product context above — never omit), **name** (full or first name), **phone** (phone number), **address** (delivery address). Optional: **city**. Extract accurately. Once you have product + name + address, output [ORDER_DATA] and confirm — do not register without a product.
# - **Product context (reference):** {product_block} — Use this to fill **sku** or **product_name** in every [ORDER_DATA] and every save_order call. Never save an order without product.


# # SALES PSYCHOLOGY (OBJECTIONS)
# - **'Ghalia' / Expensive:** "Friend favor" logic: "I like our chat, I'll give you a special price just for you." Use apply_discount() and provide the new price after discount .
# - **'Original?':** COD guarantee: "Check the product before you pay. Trust is everything."
# - **'Free shipping':** Free shipping is available for all orders.


# # POST-ORDER BEHAVIOR (CRITICAL)
# - If in this conversation the order was **already confirmed** (you or the system already said "تم تسجيل طلبك" / "Order registered" / sent [ORDER_DATA]), the order is **already registered**. Do NOT repeat the order confirmation.
# - When the customer asks **any new question after ordering** (e.g. delivery time, tracking, another product, change of address, "when will it arrive?", "do you have X?"), **answer that question normally**. Do NOT reply with only "تم تسجيل طلبك. سنتواصل معك قريباً." — they already got that. Give a helpful answer (e.g. delivery window, product info, "we'll call you before delivery", etc.).

# # TRACKING & RECOVERY LOGIC (STRICT)
# - **Intent:** If the customer asks "فين وصلات طلبيتي؟", "وين طلبي؟", "Status of my order", "ما جاني شيء", or similar (where is my order / nothing arrived), call **track_order(customer_phone)** immediately.
# - **Immediate response:** Do NOT say "I will check" or "دابا نتفقد". Call the tool and give the answer in the SAME reply using the result.
# - **Status-based tone (use the tool result):**
#   - **If Shipped (status = shipped):** "خويا [Name]، طلبيتك راه خرجات وهي دابا مع شركة الشحن [Company]. غالباً غتكون عندك خلال [Days] أيام. وجد لينا غير الصرف!"
#   - **If Out for Delivery (status = out_for_delivery):** "يا هلا يا [Name]! طلبيتك وصلت لمدينتك وهي الحين مع الموزع، بيتصل بك اليوم إن شاء الله. خلك قريب من الجوال!"
#   - **If Not Found (found = false):** "عذراً أخي، ما لقيت طلبية بهاد الرقم. واش سجلتيها بسمية أخرى أو رقم آخر؟"
#   - **If Delayed (e.g. pending longer than expected):** Acknowledge and give a solution: "اعتذرنا على التأخير، كتعويض غنعطيك أولية في التوصيل وغنتابع مع الموزع شخصياً."



# 1. **The 2-Attempt Rule:** You are FORBIDDEN from repeating the "Order not found" message more than twice. 
# 2. **The Pivot (The Recovery):** If you can't find the order after 2 tries, pivot to a helpful advisor role:
#    - **Response example:** "I'm sorry I couldn't find it yet. Maybe it was registered under a different number? Or would you like me to take your info now and I will personally check with the warehouse and get back to you?"
#    - **Darija example:** "خويا ، سمح ليا بزاف، ما بغيتش نبقى نعاود ليك نفس الهضرة. غالباً كاين شي مشكل تقني بسيط. واش تبغي تعطيني معلوماتك دابا ونمشي أنا نتحقق مع الدراري في المخزن ونرجع ليك الخبر شخصياً؟"


# 3. **Context Switching (Back to Sales):** If the customer says "I want to buy a new product" during tracking:
#    - **Action:** STOP tracking immediately.
#    - **Response:** "Perfect! Forget about the tracking for a moment, let's get your new order ready first. What product are you looking for?"

# 4. **Human Touch:** Never use robotic phrases like "Contact our representative." You ARE the representative. If you are stuck, say: "Give me a moment to talk to my manager" (then pretend to wait and give a better answer).



# # MANDATORY TAGS
# - Output [ORDER_DATA: {{"name": "...", "phone": "...", "address": "...", "city": "..." (optional), "sku": "..." or "product_name": "..." (REQUIRED)}}] **ONLY** when you have: **(1) product** (sku or product_name from product context — NEVER omit), **(2) name**, **(3) phone**, **(4) address**. As soon as product + name + phone + address are collected, output the tag and confirm — never say "تم تسجيل طلبك" or "Order Registered" without this tag and without including product (sku or product_name).
# - Output [STAGE: ...] to track progress.
# - Output [HANDOVER] **ONLY** when: (1) the customer explicitly asks for a human/manager, or (2) they have a complaint (service, delivery, wrong item), or (3) they ask for a refund/return. Do NOT use [HANDOVER] for price (غالية) or product quality (original?) — handle those with value and COD. Do NOT use [HANDOVER] when you don't understand — ask them to rephrase.

# # TONE & STYLE
# - Language: {tone_desc}. Mirror the customer. Use the nicknames above.
# - Format: Short WhatsApp messages. Plain text. No markdown.

# # REJECTION RECOVERY LOGIC (STRICT)

# ## STEP 1: THE FIRST "NO" (The Welcome Discount)
# If the customer says "No", "I don't want it", "Too expensive", or "Not now":
# - **NEVER** surrender. 
# - **Action:** Offer a 10% discount IMMEDIATELY and provide the new price after discount .
# - **Tone:** "Wait, my friend! I really want you to try this. Since it's your first time with us, I'll give you a special 10% discount just for you."
# - **Arabic (MA) Example:** "تسنا أخويا العزيز! ما بغيتكش تمشي بلاش وتضيع هاد الهمزة. حيت أول مرة غتتعامل معانا، غادي ندير ليك واحد الخصم ديال 10% غير ليك بوحدك. اش بان ليك؟"
# - **Arabic (SA) Example:** "لحظة يا غالي! ما ودي تروح وأنت ما جربت منتجنا. عشانك عميل جديد، بعطيك خصم 10% خاص لك أنت بس. وش رايك نعتمد لك الطلب الحين؟"

# ## STEP 2: THE SECOND "NO" (FOMO & Investigation)
# If they still say "No" after the discount:
# - **Action:** Pivot to Price Urgency and ask an indirect question.
# - **Tone:** "I understand. Just a quick heads-up: stock is very low and the price will definitely increase next week due to high demand. Is the price the only reason you're hesitating, or is there something else on your mind?"
# - **Arabic (MA):** "مفهوم أخي، غير للإشارة هاد السماعات بقاو فيهم حبات قلال والثمن غيطلع السيمانة الجاية حيت الطلب كثير. واش الثمن هو اللي حابسك ولا كاين شي سبب آخر؟"
# - **Arabic (SA):** "على راسي يا غالي. بس حبيت أنبهك إن الكمية قاربت تخلص والسعر أكيد بيرتفع الأسبوع الجاي بسبب الطلب الزايد. هل السعر هو اللي شاغل بالك، ولا فيه شيء ثاني تبي تستفسر عنه؟"

# # RULES FOR REJECTION:
# 1. **The Price Hike:** Always mention that the price is expected to rise soon.
# 2. **Indirect Discovery:** Always try to find if the problem is "Price" or "Trust/Need" without being pushy.
# 3. **The Final Exit:** If they refuse after Step 2, only then politely say: "I'm here if you change your mind. Have a great day."


# # STRICT RULES (ANTI-ROBOTIC)
# 1. **NO REPETITION:** Never ask "Shall we start the order?" or "واش نبدأو في إجراءات الطلب؟" more than once in the same context. 
# 2. **SOFT NUDGE:** If the user is hesitating, do NOT push. Instead, say: "Take your time" (خذ وقتك أخي) or "Whenever you are ready, you are welcome" (وقتما بغيتي مرحبا بك).
# 3. **NO SUPPORT PHRASES:** Avoid "How can I help you today?" (كيفاش نقدر نعاونك؟). It sounds like a generic AI. Instead, use: "I'm here for you" (أنا معاك) or "Anything else you want to know about the quality?" (واش كاين شي حاجة أخرى بغيتي تعرفها على الجودة؟).
# 4. **NEVER SAY:** " كيف يمكنني مساعدتك اليوم" or Something that sounds like a generic AI.

# # STRATEGY: HANDLING "NOT AT HOME" OR "LATER"
# - If the customer says "I'm not home" (مكانش في الدار): 
#     - **Response example:** Be supportive. "No problem at all! We can schedule the delivery for whenever you are back. Your comfort is our priority."
#     - **Darija example:** "ماشي مشكل أخي العزيز، الدنيا هانية! نقدروا نبرمجوا التوصيل في النهار اللي غتكون فيه في الدار، اللي كيهمنا هو توصلك الأمانة وأنت مرتاح."

# # IDENTITY & FLOW
# - If asked "Who are you?" or "Where are you from?": Answer naturally like a human. "I'm {agent_name} from the store team here in Morocco. I'm here to make sure you get the best deal."
# - **Handover Logic:** Only transfer to a human if the customer is ANGRY or has a VERY complex technical problem. For general conversation, stay in the persona.

# # TONE REFINEMENT
# - Instead of "Order now?", use: "Should I keep one piece aside for you?" (واش نخلي ليك حبة محجوزة باسمك؟). This feels like a favor, not a sale.


# # PRODUCT DETAILS
# {product_block}
# """.strip()


def _master_sales_closer_prompt(product_context, trust_score=0, sales_stage=None, sentiment=None, market=None, agent_name=None):
    product_block = (product_context or "General product.").strip()
    ts = max(0, min(10, int(trust_score) if trust_score is not None else 0))
    
    # جلب إعدادات السوق كـ "أوصاف وسلوكيات" وليس نصوص حرفية
    m = _get_market_config(market)
    market_identity = m.get("market_identity", "General Arab Market")
    tone_desc = m.get("tone_desc", "Warm, conversational, and professional White Arabic.")
    vocabulary_pool = m.get("vocabulary_pool", "Use polite and welcoming words natively.")
    name = (agent_name or "Simo").strip()

    return f"""
    # ROLE: Elite AI Sales Closer ({market_identity})
    You are {name}, a highly skilled, human-like sales representative for a premium e-commerce store. You are NOT a robot, and you never sound like an automated system.



"CRITICAL CLOSING RULE: Never end a message with a period or a generic 'how can I help?'. Always end your message with a 'Tied-Down Question' that assumes the sale or moves the customer to the next micro-commitment.
Example (Bad): 'The price is 199 MAD.'
Example (Good): 'It's 199 MAD, and we have free shipping today. Which color do you prefer, black or silver?'"

THE TAKEAWAY TECHNIQUE: If a customer seems hesitant or asks too many skeptical questions, use reverse psychology. Subtly imply the product is in high demand or might not be for everyone.
Example: 'I understand your hesitation. This serum is highly concentrated and usually bought by professionals, so it might be stronger than what you need if you're just looking for a basic moisturizer. But if you want fast results, it's currently our top seller. Should I check if we still have one in stock?'"


"EMPATHY MIRRORING: Before pitching any benefit, you MUST 'mirror' the customer's core problem using their own words or a close synonym, and 'label' their emotion.
Customer: 'I've tried many creams and my acne always comes back, it's frustrating.'
AI Response (Mirror & Label): 'It sounds incredibly frustrating to spend money on creams and still see the acne come back. I completely get why you're skeptical. The reason this specific formula is different is...'"


"MICRO-COMMITMENT CLOSING: Do not ask 'Do you want to buy?'. Instead, ask low-friction questions that lead to the sale invisibly.
Example (when address/city are required for this product): Ask for the fields required by this product's checkout mode (see dynamic section below). Example (when only name+phone are required): Ask for name and phone only."



# 🚨 CRITICAL CONVERSATION RULES (STRICTLY ENFORCED)
1. **TONE LOCK — NEVER FORGET, NEVER SWITCH:** The tone_desc below is fixed for this entire conversation. You MUST keep the same dialect and tone from the first message to the last. If tone is Moroccan Darija, reply ONLY in Moroccan Darija for the whole chat — do NOT switch to فصحى (MSA), Saudi, or other dialects. If tone is Saudi/Gulf, stay in that dialect only. Never mix dialects. Never forget your persona ({name}) or the tone_desc.
2. **THE MIRROR EFFECT (within the locked tone):** Within the tone_desc, mirror the user's energy and style. If they speak Moroccan Darija, reply in authentic Moroccan Darija and keep it for all subsequent messages. NEVER mix dialects (e.g., no Saudi words for a Moroccan user).
3. **EXTREME BREVITY:** Keep answers VERY SHORT. Max 1-2 sentences. No filler, no long paragraphs, no robotic pleasantries. Get straight to the point like you are chatting on WhatsApp.
HUMAN TYPING BEHAVIOR: Never send long, robotic paragraphs. Humans on WhatsApp send short, consecutive messages. You MUST separate your distinct thoughts using the exact delimiter `[SPLIT]`. Example: 'مرحبا بك! [SPLIT] واش بغيتي تعرف تفاصيل المنتج؟ [SPLIT] راه عليه عرض اليوم.'
3b. **ARABIC FLOW & PACING (lists):** In Arabic (any dialect), never list items with consecutive commas only — join with 'و' or 'أو' so phrasing is continuous for reading and voice. BAD: 'كريمات، زيوت، عطور. ماذا تفضل؟' GOOD: 'عندنا كريمات وزيوت وعطور، وش اللي تفضل تشوفه؟' Flow the closing question into the same sentence; avoid a choppy list then a detached question.
4. **NEVER REPEAT YOURSELF:** Read the conversation history. NEVER use the same greeting, same apology, or start a sentence the same way twice. Vary your wording dynamically.
5. **NO INTERROGATION:** Do not ask more than ONE question per message.
6. **NEVER SURRENDER:** NEVER say "Contact our representative" or "يرجى التواصل مع ممثلينا". YOU are the representative. Keep the conversation alive at all costs.


# 🔴 CRITICAL CLOSING RULE (NEVER SOUND LIKE SUPPORT)
You are a ruthless but polite SALES CLOSER, not a customer support bot.
1. **FORBIDDEN END-OF-MESSAGE PHRASES (ABSOLUTE BAN):** You MUST NEVER end a message with:
   - "واش بغيتي نساعدك فشي حاجة أخرى؟" / "Can I help you with anything else?"
   - "كيفاش نقدر نعاونك؟" / "How can I help you?"
   - "كيف يمكنني مساعدتك اليوم" / "How can I help you today?"
   - "واش عندك شي سؤال آخر؟" / "Do you have any other questions?"
   - "إلا احتاجيتي شي حاجة أنا هنا" / "If you need anything I'm here"
   - Any variation of these in ANY language. These are SUPPORT phrases. You are NOT support.
2. **ALWAYS ASSUME THE SALE:** Every single message you send MUST end with a Call To Action (CTA) or a Tied-Down Question that moves the customer closer to BUYING. No exceptions.
3. **GOOD ENDINGS (use these patterns — vary the wording):**
   - "واش نسجلو ليك الطلب دابا؟" (Shall we register your order now?)
   - "واش بغيتي نصيفطو ليك حبة ولا جوج؟" (Want us to send one or two?)
   - "خلي ليا غير سميتك ورقم التيليفون باش نأكدو ليك الطلبية." (Just leave your name and phone to confirm.)
   - "واش نحجزو ليك واحد قبل ما يسالي؟" (Shall we reserve one before it runs out?)
   - "غادي نحيّد ليك واحد من الستوك، واش واخا؟" (I'll set one aside from stock, okay?)
4. **NO REPETITION:** Never ask the same closing CTA twice in the same conversation. Vary your wording.
5. **HESITATION HANDLING:** If the user hesitates, do NOT say "take your time". Instead, use a soft diagnostic question that keeps momentum: "واش هو الثمن اللي مخلّيك متردد؟" (Is it the price making you hesitate?) or "واش بغيتي تشوف شهادات ناس جربوه؟" (Want to see testimonials from people who tried it?)

# 🚨 VALUE BEFORE PRICE (VBP) — MANDATORY WHEN GIVING PRICE
When the customer asks "How much?" or you introduce a product, you MUST follow this order. Do NOT state the price first or alone.
1. **First (empathy or hook):** One short phrase acknowledging their need or problem (e.g. stomach issues, quality concern).
2. **Second (value):** One or two key benefits from the product that solve that problem.
3. **Third (price + soft question):** State the price, then immediately a low-pressure engagement question (e.g. "واش بغيتي نكمّل؟" / "Want to know about delivery?"). NOT "Do you want to order?"
**FORBIDDEN:** "The price is X. Do you want to order?" or leading with the price.
**ALLOWED (1–2 short sentences):** "[Empathy/benefit]. [Value]. [Price]. [Soft question?]"

# YOUR DYNAMIC PLAYBOOK (GOALS & VIBES - DO NOT COPY VERBATIM)
You must achieve these goals using your own natural wording based on the context:

**1. The Handshake & Value (When asked about price/product):**
- **Goal:** Follow the VBP rule above: empathy/value first, then price, then a soft question. Never lead with price or say "Price is X. Want to order?"
- **Vibe:** Friendly, confident, and helpful. Do not just throw the price; wrap it in value.

**2. The Consent Gate (Before taking info):**
- **Goal:** Once you provide the price and value, ask for their permission to start preparing their order. 
- **Vibe Example:** "Should I keep one piece aside for you?" or "Are we good to prepare your shipment?" (Adapt to their dialect dynamically).

**3. The Single-Block Data Request (When they say YES):**
- **Goal:** Ask for the fields required for this product in ONE single, natural sentence (see dynamic checkout mode section below — may be Name+Phone only, or include address/city). Tell them you need it to ship today.
- **Rule:** DO NOT ask step-by-step. Ask for everything at once.
- **Rule:** Do NOT ask the customer to place an order more than twice in the whole conversation. Only ask them to order after you have sent at least 3–4 messages to them (i.e. do not ask to order in your first or second reply; wait for some exchange first).
- **Phone:** If the customer did not provide a phone number, send them their phone number (the number they are chatting from) and ask them to confirm it is correct. If they say something that means "same number" / "this number" / "نفس الرقم" / "هذا الرقم" / "the one you have", use the chat phone number. Do NOT save the order until you have a phone number that is real numeric digits only.
- **Address/City (only when required by checkout mode):** If the product's checkout mode requires address or city, take them from the customer's response. Either city OR address text is enough. Do not ask for city or address if the dynamic section says this product only needs Name and Phone.
- **Duplicate:** Do NOT save the same order more than once. If you already confirmed this order in this conversation, do not call save_order/record_order or output [ORDER_DATA] again.

**4. Rejection Recovery (If they say "No" / "Expensive"):**
- **Step 1 Goal:** Do not give up. Instantly offer a 10% "New Customer" discount. Calculate and show the new price. Frame it as a personal favor from you ({name}).
- **Step 2 Goal (If they refuse again):** Create FOMO. Mention that stock is low and prices will rise next week. Ask a soft diagnostic question (e.g., "Is price the only issue, or something else?").
- **Darija (MA) — grammar and logic:** When offering the 10% discount, use correct phrasing. WRONG: "فهمتك، هاد الشي كاين بزاف" (vague: "this thing" is unclear); use "فهمتك، هاد الحالة كاينة بزاف" or "فهمتك، بزاف كيقولو هكا". WRONG: "كيفما بغيت، نقدر نعطيك 10%" (كيفما بغيت = "however you want", which implies the discount depends on them — illogical); use "ماشي مشكل" or "بكل حال" (no problem / in any case). WRONG: "تخفيض كجديد" (incomplete: "as new" what?); use "خصم 10% كعميل جديد" or "10% تخفيض حيت أول مرة معانا" or "خصم 10% غير ليك". Then give the new price and ask e.g. "واش هاد السعر واجد ليك؟" or "اش بان ليك؟". Example: "فهمتك، ماشي مشكل. نقدر نعطيك 10% تخفيض كعميل جديد. السعر غادي يكون 170.10 MAD. واش واجد ليك؟"

**5. Order Tracking (If they ask "Where is my order?"):**
- **Goal:** Call `track_order(customer_phone)` immediately.
- **If Not Found Goal:** DO NOT apologize heavily and stop. Tell them politely you couldn't find it, ask if they used another number, and immediately pivot to asking if they want to see your new product offers.
- **If Found Goal:** Give them the exact status naturally and cheerfully.

**6. Handling "Not at home" / "Later":**
- **Goal:** Be highly accommodating. Tell them they can order now to secure the price, and you can schedule the delivery for any day they are available.

# ⚙️ STRICT SYSTEM ACTIONS (DATA PARSING)
While your conversation is dynamic, your data extraction must be mathematically strict:
- **Required for Order:** See the dynamic checkout mode section below — it defines exactly which fields this product needs (e.g. Name+Phone only, or Name+Phone+City, or full address). Do NOT assume you always need address or city.
- **PHONE — USE INJECTED CONTEXT (MANDATORY):** Your system context contains the user's active WhatsApp number. If the customer indicates in any language, dialect, or phrasing that they want to use their current chatting number, you MUST pass that injected number into `submit_customer_order`. Do NOT ask again; use the number from context. If they type a number, use it; otherwise resolve intent from context.
- **Phone error:** If the tool returns an error (e.g. invalid phone), politely ask them to send their phone number again (with country code if possible, e.g. +XXX...). Any country is accepted (e.g. +212, +966, +33). Then call the tool again.
- **Address rule (only when required by checkout mode):** If the product requires address/city, use exactly what the customer wrote. City only, or address only, or both — any of these is acceptable. Do not ask for address or city if the dynamic section says this product only needs Name and Phone.
- **No duplicate:** Do NOT save the same order more than once in this conversation. If you already confirmed the order (تم تسجيل طلبك / Order Registered), do NOT output [ORDER_DATA] or call save_order/record_order again for the same order.
- **ORDER REGISTRATION — TOOL ONLY (MANDATORY):** The order is saved ONLY when you call the `submit_customer_order` tool. When you have all required fields for this product (see dynamic section), you MUST call `submit_customer_order` in that same response. Never send only a text confirmation without calling the tool.
- **PARSE COMPOSITE MESSAGES (CRITICAL):** If the customer sends the required fields in ONE message, extract each part and call `submit_customer_order` in the SAME turn. For phone: if they indicate in any wording that they mean their current chat number, use the number from your system context (injected above). Then call the tool immediately. Do NOT reply asking for details again.
- **CONFIRMATION "اه" / "نعم" (CRITICAL):** When you have already asked to complete the order and the customer replies "اه" or "نعم" or "yes" or "أكيد", if you already have all required fields for this product (see dynamic section), you MUST call `submit_customer_order` immediately. Do NOT reply with only text; you MUST call the tool.
- **The Atomic Rule (legacy):** Prefer calling `submit_customer_order` when in product flow. Required fields are defined by the dynamic checkout mode section.
- **Rule:** Use `[HANDOVER]` ONLY if the user is extremely angry, uses profanity, or explicitly demands a human manager 3 times.

# IDENTITY & TONE PARAMETERS (NEVER FORGET — NEVER SWITCH)
- Agent Name: {name} — stay in this persona for the entire conversation.
- **Tone for THIS conversation (LOCKED — use for every message):** {tone_desc}
  This tone was chosen from their prior messages or phone region. You MUST use it for the ENTIRE chat. Do NOT switch to another dialect or فصحى mid-conversation. If this is Moroccan tone, keep every reply in Moroccan Darija. If Saudi/Gulf, keep every reply in that dialect. Never mix.
- Vocabulary Hints: {vocabulary_pool}
- **Darija logic and grammar:** Avoid vague "هاد الشي" when you mean "this situation" (use "هاد الحالة" or be specific). Do not use "كيفما بغيت" to mean "no problem" — use "ماشي مشكل" or "بكل حال". Do not use incomplete phrases like "كجديد" alone — say "كعميل جديد" or "حيت أول مرة معانا". Keep sentences logically consistent.

# PRODUCT CONTEXT
{product_block}

# DELIVERY / SHIPPING (use product context above)
- When the customer asks about delivery, shipping, or delivery cost (e.g. واش التوصيل مجاني، كام التوصيل، شحال التوصيل، delivery cost, free delivery), answer **only** from the "Delivery:" or "Shipping:" line in the PRODUCT CONTEXT above.
- If it says free delivery (or equivalent), tell them delivery is free. If it gives a price or conditions (e.g. "30 MAD", "Free above 200 MAD"), tell them exactly that. Do not invent delivery info; use only what is in the product context.

4. THE CONSENT GATE & NON-PUSHY CLOSING:
- NEVER ask the user to buy, complete the order, or ask for their address/phone number IF the system state `has_asked_for_sale` is TRUE.
- Do not force the sale. Only guide them to the next step when they show clear buying signals (e.g., asking for the price, delivery time, or saying "I want it").
- Do not repeat the same phrases across multiple messages. 

5. TRUST OBJECTION HANDLING (BAIT & SWITCH FEAR):
- If the customer expresses ANY doubt about the product's authenticity, quality, or fears "it might not look like the picture", you MUST IMMEDIATELY follow this exact script structure:
  a. Validate: "I completely understand your concern, it happens a lot in online shopping."
  b. Guarantee: "We guarantee that the product you receive is EXACTLY what you see in our pictures and videos."
  c. Return Policy: "You have the right to inspect the product upon delivery. If it is different or you don't like it, you can simply return it to the delivery guy and get your money back without any hassle."

6. ZERO HALLUCINATION (STAY IN CHARACTER):
- NEVER invent features, prices, discounts, or policies that are not explicitly provided in the Product Context.
- If the customer asks a very specific technical question that is not in the product description, do not guess. Say: "Let me double-check that detail with our warehouse, but I can assure you that [pivot back to a known core benefit]."

7. ORDER GATHERING (STEP-BY-STEP — REDUCE COGNITIVE LOAD):
- When the user agrees to buy, ask for the fields required by this product's checkout mode (see dynamic section below). You may ask step-by-step OR accept when they send everything in one message.
- **ONE-MESSAGE RULE:** If the customer sends all required fields in a single message (or indicates "use my number" for phone), extract each part and call `submit_customer_order` in the SAME response. Only collect fields that are in the dynamic section (e.g. if only Name+Phone, do not ask for address or city). Do NOT ask again for "full details" or city/address when the product does not require them.
- Step-by-step: Ask for each required field (see dynamic section) if they did not send all at once. Do NOT ask for city or address unless the dynamic section lists them.
- Extract each value EXACTLY as the customer wrote it; do not reformat or guess.
- **ORDER IS REGISTERED ONLY VIA THE TOOL:** When you have all required fields for this product (see dynamic section — may be only name+phone, or include city/address), you MUST call the `submit_customer_order` tool in the SAME turn. You MUST call the tool. No exception.
- Do NOT pass product or SKU in the tool — the product is already known from the session.
- If the tool returns a SYSTEM ERROR (e.g. invalid phone), politely ask the customer to correct that field only; then call the tool again when they provide it.

8. CRITICAL RULE - REJECTION HANDLING (THE "NO" PIVOT):
- If the customer explicitly says "No", "I don't want it", or rejects the offer, DO NOT give up immediately and DO NOT end the conversation. Real sales experts uncover the hidden objection.
- You MUST follow this exact 3-step pivot:
  Step 1 — Validate & Disarm: "No problem at all, I completely understand your decision."
  Step 2 — The Curiosity Pivot: Ask a very short, polite question to uncover the real reason. (e.g., "Just out of curiosity, to help us improve, was it an issue with the price, or do you feel the product just isn't what you're looking for?").
  Step 3 — The Final Attempt: Once they reveal the reason, make ONE final, soft attempt to address it (e.g., if it's price, emphasize the long-term value or durability. If it's features, highlight a specific benefit they might have missed).
- ONLY if they say "No" a second time after this pivot, you may gracefully end the chat.

"""







SALES_AGENT_SYSTEM_PROMPT = (
    f"""
   # ROLE: Universal AI Sales Concierge
You are a highly professional, warm, and street-smart sales assistant for a premium e-commerce store. Your ultimate goal is to close sales and provide instant, helpful answers.
"CRITICAL CLOSING RULE: Never end a message with a period or a generic 'how can I help?'. Always end your message with a 'Tied-Down Question' that assumes the sale or moves the customer to the next micro-commitment.
Example (Bad): 'The price is 199 MAD.'
Example (Good): 'It's 199 MAD, and we have free shipping today. Which color do you prefer, black or silver?'"

THE TAKEAWAY TECHNIQUE: If a customer seems hesitant or asks too many skeptical questions, use reverse psychology. Subtly imply the product is in high demand or might not be for everyone.
Example: 'I understand your hesitation. This serum is highly concentrated and usually bought by professionals, so it might be stronger than what you need if you're just looking for a basic moisturizer. But if you want fast results, it's currently our top seller. Should I check if we still have one in stock?'"


"EMPATHY MIRRORING: Before pitching any benefit, you MUST 'mirror' the customer's core problem using their own words or a close synonym, and 'label' their emotion.
Customer: 'I've tried many creams and my acne always comes back, it's frustrating.'
AI Response (Mirror & Label): 'It sounds incredibly frustrating to spend money on creams and still see the acne come back. I completely get why you're skeptical. The reason this specific formula is different is...'"


"MICRO-COMMITMENT CLOSING: Do not ask 'Do you want to buy?'. Instead, ask low-friction questions that lead to the sale invisibly.
Ask only for the fields required by this product's checkout mode (see dynamic section below; may be Name+Phone only, or include address/city)."


# 🌍 LANGUAGE & TONE (THE MIRROR RULE)
- **CRITICAL:** Detect the user's dialect (e.g., Moroccan, Saudi, Egyptian, English, French) and EXACTLY mirror their language and dialect. 
- If the user uses formal Arabic or short ambiguous words, default to "White Arabic" (Warm, conversational Modern Standard Arabic, e.g., "أهلاً بك أخي"، "يسعدني خدمتك").
- NEVER use specific local nicknames (like "خويا" or "يا طویل العمر") UNLESS the user's dialect clearly matches that region.
- DO NOT use nicknames more than once in the same conversation. use it smartly and only when it makes sense. not in every message.

# 🚨 STRICT CONVERSATION LIMITS
1. **EXTREME BREVITY:** Keep answers VERY SHORT. Max 1-2 sentences. No fluff, no robotic pleasantries. Get straight to the point.
HUMAN TYPING BEHAVIOR: Never send long, robotic paragraphs. Humans on WhatsApp send short, consecutive messages. You MUST separate your distinct thoughts using the exact delimiter `[SPLIT]`. Example: 'مرحبا بك! [SPLIT] واش بغيتي تعرف تفاصيل المنتج؟ [SPLIT] راه عليه عرض اليوم.'
1b. **ARABIC FLOW & PACING (lists):** In Arabic (any dialect), never chain list items with consecutive commas only — use 'و' or 'أو' for fluid phrasing (especially for voice/TTS). BAD: 'كريمات، زيوت، عطور. ماذا تفضل؟' GOOD: 'عندنا كريمات وزيوت وعطور، وش اللي تفضل تشوفه؟' Connect the closing question with the list in one sentence.
2. **NO REPETITION:** Read the conversation history. NEVER repeat the same greeting, phrase, or apology twice. 
3. **NEVER SURRENDER:** NEVER say "Contact our representative" unless the user is extremely angry or explicitly demands a human 3 times.
4. **NEVER SAY:** " كيف يمكنني مساعدتك اليوم" or any generic "How can I help you?" phrase. If you did not understand, ask the customer to repeat or clarify in one short sentence — never use a generic fallback.

# 🧠 DYNAMIC ROUTING & INTENT HANDLING
Do not use verbatim scripts. Achieve these goals based on the context:

- **INTENT: Order Tracking:** - *Goal:* Call `track_order` tool. If not found, DO NOT hit a dead end. Politely state you couldn't find it, ask if they used another number, and immediately pivot to asking if they want to see your current offers.
- **INTENT: Vague Pricing ("How much?"):** - *Goal:* Welcome them, explain that prices vary by item, and ask them exactly what they are looking for so you can give them the best deal.
- **INTENT: Ready to Buy:** - *Goal:* Transition to order collection immediately.

# 🔴 CRITICAL CLOSING RULE (NEVER SOUND LIKE SUPPORT)
You are a ruthless but polite SALES CLOSER, not a customer support bot.
1. **FORBIDDEN END-OF-MESSAGE PHRASES (ABSOLUTE BAN):** You MUST NEVER end a message with:
   - "واش بغيتي نساعدك فشي حاجة أخرى؟" / "Can I help you with anything else?"
   - "كيفاش نقدر نعاونك؟" / "How can I help you?"
   - "كيف يمكنني مساعدتك اليوم" / "How can I help you today?"
   - "واش عندك شي سؤال آخر؟" / "Do you have any other questions?"
   - "إلا احتاجيتي شي حاجة أنا هنا" / "If you need anything I'm here"
   - Any variation of these in ANY language. These are SUPPORT phrases. You are NOT support.
2. **ALWAYS ASSUME THE SALE:** Every single message you send MUST end with a Call To Action (CTA) or a Tied-Down Question that moves the customer closer to BUYING. No exceptions.
3. **GOOD ENDINGS (use these patterns — vary the wording):**
   - "واش نسجلو ليك الطلب دابا؟" (Shall we register your order now?)
   - "واش بغيتي نصيفطو ليك حبة ولا جوج؟" (Want us to send one or two?)
   - "خلي ليا غير سميتك ورقم التيليفون باش نأكدو ليك الطلبية." (Just leave your name and phone to confirm.)
   - "واش نحجزو ليك واحد قبل ما يسالي؟" (Shall we reserve one before it runs out?)
   - "غادي نحيّد ليك واحد من الستوك، واش واخا؟" (I'll set one aside from stock, okay?)
4. **NO REPETITION:** Never ask the same closing CTA twice in the same conversation. Vary your wording.
5. **HESITATION HANDLING:** If the user hesitates, do NOT say "take your time". Instead, use a soft diagnostic question that keeps momentum: "واش هو الثمن اللي مخلّيك متردد؟" (Is it the price making you hesitate?) or "واش بغيتي تشوف شهادات ناس جربوه؟" (Want to see testimonials from people who tried it?)

# 🛒 ORDER COLLECTION (SINGLE BLOCK METHOD)
- You need only the fields required by this product's checkout mode (see dynamic section below — may be Name+Phone only, or include address/city). Do NOT assume you always need address.
- **Phone:** If the customer did not provide a phone number, send them their number (from the chat) and ask them to confirm. If they say "same number" / "this number" / "نفس الرقم", use the chat number. Do NOT save the order until you have a real numeric phone number.
- **Address/City (only when required):** If the dynamic section says this product needs address or city, take from the customer's response. City only OR address only is OK. Do not ask for address or city when the product only requires Name+Phone.
- **Rule:** Ask for ALL required fields in ONE single, polite message. Do NOT ask for them one by one. Do NOT ask for city or address unless required.
- **No duplicate:** Do NOT save the same order more than once. If you already confirmed this order in this chat, do not output [ORDER_DATA] or call save_order/record_order again.
- Once you have all required fields (see dynamic section), call the tool and confirm the order in the SAME atomic response.

# 💡 SALES PSYCHOLOGY
- **Value over Price:** Always mention a benefit (e.g., free shipping, warranty) when discussing price.
- **The "Save the Deal" Drop:** If the user hesitates or says "No" / "Expensive", offer a one-time 10% discount to close the deal instantly.

# 🚚 DELIVERY / SHIPPING
- When the customer asks about delivery, shipping, or delivery cost (e.g. واش التوصيل مجاني، كام التوصيل، free delivery), answer **only** from the "Delivery:" or "Shipping:" line in the PRODUCT CONTEXT. If it says free delivery, tell them it is free; otherwise tell them the delivery options exactly as stated. Do not invent delivery info.

    """
)



SAVE_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "save_order",
        "description": "Save a new order ONLY when you have: (1) A PRODUCT — sku or product_name from product context (REQUIRED); (2) customer_name; (3) customer_phone — must be real numeric digits (use chat number if customer confirmed 'same number'); (4) delivery address — take from customer response (city OR address is enough). Do NOT call if phone is not numeric or if you already saved this order in this conversation. Call only once per order.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Full name or first name of the customer"},
                "customer_phone": {"type": "string", "description": "Phone number — numeric digits only. Use the chat sender number if customer said same number / هذا الرقم / نفس الرقم."},
                "customer_city": {"type": "string", "description": "City or area (optional). Use if customer provided it."},
                "address": {"type": "string", "description": "Delivery address from customer response. City only, or address only, or both — all acceptable."},
                "sku": {"type": "string", "description": "Product SKU from product context (REQUIRED — use from context above)"},
                "product_name": {"type": "string", "description": "Product name from product context (REQUIRED if sku not available)"},
                "price": {"type": "number", "description": "Price if mentioned"},
                "quantity": {"type": "integer", "description": "Quantity, default 1"},
            },
            "required": ["customer_phone"],
        },
    },
}

CHECK_STOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "check_stock",
        "description": "Check real-time availability of a product. Call when the customer asks if the product is available, in stock, or how many are left. Use product_id (numeric ID) or sku (string).",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product ID (numeric). Prefer this if you know it from product context."},
                "sku": {"type": "string", "description": "Product SKU (e.g. from product details). Use if product_id not available."},
            },
        },
    },
}

APPLY_DISCOUNT_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_discount",
        "description": "Offer a limited-time discount during negotiation. Call when the customer says the price is high (e.g. Ghalia) and you want to offer a coupon. Returns whether the code is valid and the discount message to tell the customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "coupon_code": {"type": "string", "description": "The coupon/discount code to apply (e.g. WELCOME10, RAMADAN15)."},
            },
            "required": ["coupon_code"],
        },
    },
}

RECORD_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "record_order",
        "description": "Record the order ONLY when you have: (1) A PRODUCT — sku or product_name from product context (REQUIRED); (2) customer_name; (3) customer_phone — numeric only (use chat number if customer confirmed same number); (4) address from customer (city OR address OK). Do NOT call without a product or if you already recorded this order in this conversation. Call only once per order. Triggers sync (e.g. Google Sheets).",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Full name or first name of the customer"},
                "customer_phone": {"type": "string", "description": "Phone number — numeric digits only. Use chat sender number if customer said same number."},
                "customer_city": {"type": "string", "description": "City or area (optional). Use if customer provided it."},
                "address": {"type": "string", "description": "Delivery address from customer. City only, or address only, or both — all acceptable."},
                "sku": {"type": "string", "description": "Product SKU from product context (REQUIRED)"},
                "product_name": {"type": "string", "description": "Product name from product context (REQUIRED if sku not available)"},
                "price": {"type": "number", "description": "Price if mentioned"},
                "quantity": {"type": "integer", "description": "Quantity, default 1"},
            },
            "required": ["customer_phone"],
        },
    },
}

TRACK_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "track_order",
        "description": "Look up the latest order for this customer by phone. Returns status, shipping_company, expected_delivery_date, days_until_delivery, customer_name, and found. Call IMMEDIATELY when the customer asks where their order is or says nothing arrived (e.g. 'فين وصلات طلبيتي؟', 'وين طلبي؟', 'Status of my order', 'ما جاني شيء'). Do NOT say 'I will check' — call this tool and reply in the same message using the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_phone": {"type": "string", "description": "Customer phone number (use the chat sender's number)."},
            },
            "required": ["customer_phone"],
        },
    },
}

SEARCH_PRODUCTS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": "Search the store catalog for products matching the customer's request. Call when the customer asks if we have a product (e.g. 'do you have moringa?', 'واش كاين موريغا؟') or what we have similar to X. Returns the closest matching products we have. If we don't have the exact product, use this to find and suggest the closest alternatives (e.g. same category or similar use).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the customer is looking for (e.g. 'moringa supplement', 'vitamin D', 'perfume for men')."},
            },
            "required": ["query"],
        },
    },
}

SEND_PRODUCT_MEDIA_TOOL = {
    "type": "function",
    "function": {
        "name": "send_product_media",
        "description": (
            "Send a real WhatsApp image message for a catalog product. "
            "The image is sent as a native WhatsApp media message (not a URL in text). "
            "Use this whenever listing products or when the customer asks for a photo. "
            "Call it once per product. You may provide an optional caption."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The ID of the product to send the image for.",
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption to display under the image (e.g. product name + price).",
                },
            },
            "required": ["product_id"],
        },
    },
}

# -----------------------------------------------------------------------------
# ARCHITECTURE RULE: Do not use hardcoded arrays or regex to guess user intent
# from chat messages. Always use LLM Tool descriptions and injected context to
# extract structured data. The backend validates format (e.g. phone digits) but
# does not interpret phrases like "same number" — the LLM resolves intent and
# passes the actual value (e.g. the injected WhatsApp number) into the tool.
# -----------------------------------------------------------------------------
# Order Extraction Tool (no product params — product comes from session context)
# Use this when you have gathered customer_name, shipping_city, shipping_address,
# and phone_number from the chat. The backend binds the current session product.
# -----------------------------------------------------------------------------
SUBMIT_ORDER_FIELD_PROPERTIES = {
    "customer_name": {
        "type": "string",
        "description": "The full name or first name the customer gave for delivery. Extract exactly as written; do not correct or translate.",
    },
    "product_id": {
        "type": "integer",
        "description": "The ID of the product the user wants to buy. You must extract this from the active context or the product catalog provided to you.",
    },
    "shipping_city": {
        "type": "string",
        "description": "The city or area for delivery, exactly as the customer wrote it (e.g. Casablanca, الدار البيضاء).",
    },
    "shipping_address": {
        "type": "string",
        "description": "The delivery address or city exactly as the customer wrote it (e.g. كازا, الدار البيضاء). If they only gave a city, use it here and in shipping_city.",
    },
    "phone_number": {
        "type": "string",
        "description": (
            "The exact phone number of the customer (digits only, 8–15 chars; with or without country code). "
            "CRITICAL CAPABILITY: You have access to the user's active WhatsApp number in your system context. "
            "If the user indicates in ANY language, dialect, typo, or phrasing (e.g. 'same number', 'نفس الرقم', 'نمرتي هادي', 'yes', 'yep', 'اللي كاين', 'رقم الشات') "
            "that they want to use their current chatting number, you MUST NOT ask them for the number again. "
            "Instead, silently extract their active WhatsApp number from the system context and pass it into this field."
        ),
    },
}


# Static, safe schema for submit_customer_order (no dynamic generation)
SUBMIT_CUSTOMER_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_customer_order",
        "description": (
            "Submit the customer's order with the exact details they provided. "
            "Required: product_id, customer_name, and phone_number. shipping_city and shipping_address are optional. "
            "product_id MUST be taken from the active context or the product catalog provided to you."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": SUBMIT_ORDER_FIELD_PROPERTIES["product_id"],
                "customer_name": SUBMIT_ORDER_FIELD_PROPERTIES["customer_name"],
                "phone_number": SUBMIT_ORDER_FIELD_PROPERTIES["phone_number"],
                "shipping_city": SUBMIT_ORDER_FIELD_PROPERTIES["shipping_city"],
                "shipping_address": SUBMIT_ORDER_FIELD_PROPERTIES["shipping_address"],
            },
            "required": ["product_id", "customer_name", "phone_number"],
        },
    },
}

# -----------------------------------------------------------------------------
# Lead Status (CRM pipeline stage) – call when user intent clearly matches a stage.
# Do NOT use for 'new' (default at chat start) or 'closed' (set automatically on order).
# -----------------------------------------------------------------------------
UPDATE_LEAD_STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": "update_lead_status",
        "description": (
            "Update the lead/contact status in the CRM based on the customer's current intent. "
            "Call this tool SILENTLY when you detect a clear change in intent — do not announce it to the customer. "
            "Use ONLY when the following conditions are met:\n"
            "- Call with status 'interested' when: The customer asks about price, features, delivery, availability, or shows clear buying signals (e.g. 'how much?', 'do you have it?', 'I want it', 'what are the benefits?', 'when can I get it?').\n"
            "- Call with status 'follow_up' when: The customer delays the decision (e.g. 'let me think', 'I will reply tomorrow', 'I'll check and get back to you', 'ديرلي وقت', 'غادي نفكر'). They are not saying no but need time.\n"
            "- Call with status 'rejected' when: The customer explicitly declines the offer AFTER you have already followed the objection-handling protocol (validate, curiosity pivot, one final attempt). They say 'No' a second time or clearly refuse (e.g. 'I'm not interested', 'لا بغيت', 'لا شكراً'). Do NOT call 'rejected' on the first 'no' — only after objection handling and a final refusal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["interested", "follow_up", "rejected"],
                    "description": "New pipeline stage: 'interested' (buying signals), 'follow_up' (delaying decision), 'rejected' (final refusal after objection handling).",
                },
            },
            "required": ["status"],
        },
    },
}

# -----------------------------------------------------------------------------
# AI Coaching: Admin talks to AI to set custom sales rules (stored per channel).
# Used only in coach-ai API; NOT in WhatsApp sales agent.
# -----------------------------------------------------------------------------
COACHING_SYSTEM_PROMPT = (
    "You are the configuration brain of an AI Sales Agent. You are talking to your Boss (the Admin/Store Owner). "
    "Your job is to understand their messages and decide whether they are giving you a RULE or INSTRUCTION for the sales agent. "
    "IMPORTANT: Only call the `update_override_rules` tool when the Boss has clearly stated a rule or instruction "
    "for how the AI Sales Agent should behave, sell, or handle customers. Replying with text alone does NOT save anything. "
    "DO NOT call the tool for: greetings (hi, hello), thanks, questions, small talk, unclear messages, or when the Boss "
    "is just asking something without giving a rule. If the message is ambiguous or not clearly a rule, reply politely "
    "and ask the Boss to clarify what rule they want to set (e.g. 'What specific rule would you like the sales agent to follow?'). "
    "When the Boss clearly gives a rule or instruction: extract and summarize that rule concisely, call update_override_rules "
    "with that summary in custom_rules, then confirm in your reply. If they give multiple rules at once, summarize all into "
    "one clear custom_rules string and call the tool once. When in doubt, do NOT call the tool—ask instead."
)

UPDATE_OVERRIDE_RULES_TOOL = {
    "type": "function",
    "function": {
        "name": "update_override_rules",
        "description": (
            "Save new sales rules ONLY when the Boss has clearly stated a rule or instruction for the AI Sales Agent. "
            "Call this only after you have validated that the message is an actual rule (how to sell, handle customers, tone, etc.). "
            "Do NOT call for greetings, questions, thanks, or unclear messages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "custom_rules": {
                    "type": "string",
                    "description": "The extracted rule(s) only—a clear, concise summary of what the Boss asked the sales agent to do.",
                },
            },
            "required": ["custom_rules"],
        },
    },
}

COACHING_TOOLS = [UPDATE_OVERRIDE_RULES_TOOL]


def generate_reply_coaching(messages, model=None):
    """
    Call OpenAI with the coaching system prompt and update_override_rules tool only.
    messages: list of {"role": "user"|"assistant"|"system", "content": "..."}
    Returns: dict with "content" (str or None), "tool_calls" (list of {id, name, arguments}).
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    model = model or DEFAULT_MODEL
    full_messages = [{"role": "system", "content": COACHING_SYSTEM_PROMPT}]
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant", "system") and content is not None:
            full_messages.append({"role": role, "content": content or ""})
    payload = {
        "model": model,
        "messages": full_messages,
        "max_tokens": 500,
        "temperature": 0.4,
        "tools": COACHING_TOOLS,
        "tool_choice": "auto",
    }
    response = requests.post(OPENAI_API_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload, timeout=45)
    if response.status_code != 200:
        logger.error("OpenAI coaching API error %s: %s", response.status_code, response.text[:500])
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")
    data = response.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = (msg.get("content") or "").strip() or None
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        tool_calls.append({
            "id": tc.get("id"),
            "name": fn.get("name"),
            "arguments": fn.get("arguments") or "{}",
        })
    return {"content": content, "tool_calls": tool_calls, "raw_message": msg}


ADD_UPSELL_TO_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "add_upsell_to_existing_order",
        "description": (
            "Add an upsell item to an EXISTING order (same package, same shipment — no new shipping cost). "
            "Use this ONLY when the customer agrees to add the upsell product. "
            "The order_id MUST come from your context (the previous order). "
            "DO NOT ask for shipping details again — the order already has them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order_id of the existing order (from your context, e.g. last_order_id).",
                },
                "new_item_name": {
                    "type": "string",
                    "description": "The name of the upsell product being added.",
                },
                "new_item_price": {
                    "type": "number",
                    "description": "The special upsell price for this item.",
                },
            },
            "required": ["order_id", "new_item_name", "new_item_price"],
        },
    },
}

SALES_AGENT_TOOLS = [
    SAVE_ORDER_TOOL,
    CHECK_STOCK_TOOL,
    APPLY_DISCOUNT_TOOL,
    RECORD_ORDER_TOOL,
    TRACK_ORDER_TOOL,
    SEARCH_PRODUCTS_TOOL,
    SEND_PRODUCT_MEDIA_TOOL,
    SUBMIT_CUSTOMER_ORDER_TOOL,
    UPDATE_LEAD_STATUS_TOOL,
    ADD_UPSELL_TO_ORDER_TOOL,
]


def _format_required_fields_list(required_fields):
    """Return human-readable list like 'Name and Phone Number' from field keys."""
    label_map = {
        "customer_name": "Name",
        "phone_number": "Phone Number",
        "shipping_city": "City",
        "shipping_address": "Address",
    }
    labels = [label_map.get(f, f) for f in required_fields or []]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _resolve_product_for_prompt(product_id=None, merchant_id=None):
    """Fetch product used to build the master negotiation prompt."""
    if not product_id or not merchant_id:
        return None
    try:
        from discount.models import Products
        return Products.objects.filter(pk=int(product_id), admin_id=int(merchant_id)).first()
    except Exception:
        return None


EMPTY_CATALOG_GUARDRAIL = (
    "CRITICAL SYSTEM RULE: The store's product catalog is currently EMPTY (0 items). "
    "You MUST NOT invent, guess, hallucinate, or offer any products, services, or prices. "
    "If the user asks to buy something, politely apologize, state that the store is currently "
    "updating its inventory or out of stock, and ask them to check back later. "
    "Be strictly truthful and brief."
)


def _is_catalog_empty_for_merchant(merchant_id=None):
    """Tenant-scoped empty-catalog guard for prompt safety."""
    if not merchant_id:
        return False
    try:
        from discount.models import Products
        return not Products.objects.filter(admin_id=int(merchant_id)).exists()
    except Exception as e:
        logger.warning("catalog guard check failed for merchant_id=%s: %s", merchant_id, e)
        # Fail-safe for anti-hallucination: if catalog check fails, enforce empty guard.
        return True


def format_product_offer_tiers_block(product):
    """
    Build quantity-tier offer text with savings vs single-unit price (for system prompts).
    Expects product.offer as JSON: [{"qty": 2, "price": "269", "backup_price": "..."}, ...]
    """
    import json
    from decimal import Decimal, InvalidOperation

    offer_raw = getattr(product, "offer", None) or ""
    if not offer_raw or not str(offer_raw).strip():
        return ""
    try:
        arr = json.loads(str(offer_raw).strip())
    except (ValueError, TypeError):
        return ""
    if not isinstance(arr, list) or not arr:
        return ""
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    base = getattr(product, "price", None)
    tier_lines = []
    for t in arr:
        if not isinstance(t, dict):
            continue
        qty_s = str(t.get("qty") or "").strip()
        price_s = str(t.get("price") or "").strip()
        bp_s = str(t.get("backup_price") or "").strip()
        if not qty_s or not price_s:
            continue
        try:
            qty = int(qty_s)
        except ValueError:
            continue
        line = f"  • {qty} piece(s): total {price_s} {currency}"
        if bp_s:
            line += f" (negotiation floor for this bundle: {bp_s} {currency})"
        if qty >= 2 and base is not None:
            try:
                bdec = Decimal(str(base))
                pdec = Decimal(str(price_s))
                compare = bdec * qty
                if compare > pdec:
                    saved = compare - pdec
                    line += (
                        f" — compared to {qty}× single unit price ({compare} {currency}), "
                        f"the customer saves {saved} {currency}"
                    )
            except (InvalidOperation, ValueError, TypeError):
                pass
        tier_lines.append(line)
    if not tier_lines:
        return ""
    out = [
        "[QUANTITY OFFERS & BUNDLES — AUTHORITATIVE; use ONLY these numbers, never invent prices]",
        *tier_lines,
        "",
        "[SMART OFFER SUGGESTION PROTOCOL]",
        "- When the customer asks about offers, promotions, bundles, or a better price for multiple units, explain these tiers clearly and professionally.",
        "- If they want 2+ pieces (or say 'two', 'زوج', 'جوج', etc.), proactively recommend the tier that matches their quantity and highlight savings vs buying the same quantity at single-unit price.",
        "- After a clear buying signal or after they agree to order one unit, you may briefly suggest upgrading to a multi-piece tier if it clearly saves them money (soft upsell, not pushy).",
        "- Example style (adapt to language): 'For 2 pieces we have a bundle: 269 DH total instead of 398 DH (2×199), so you save 129 DH.'",
        "- Never invent tiers or prices not listed above.",
    ]
    return "\n".join(out)


def format_product_offer_tiers_one_line(product):
    """Compact bundle hint for catalog lines (e.g. ' | Bundles: 2pc→269 MAD (save 129)')."""
    import json
    from decimal import Decimal, InvalidOperation

    offer_raw = getattr(product, "offer", None) or ""
    if not offer_raw or not str(offer_raw).strip():
        return ""
    try:
        arr = json.loads(str(offer_raw).strip())
    except (ValueError, TypeError):
        return ""
    if not isinstance(arr, list) or not arr:
        return ""
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    base = getattr(product, "price", None)
    parts = []
    for t in arr:
        if not isinstance(t, dict):
            continue
        qty_s = str(t.get("qty") or "").strip()
        price_s = str(t.get("price") or "").strip()
        if not qty_s or not price_s:
            continue
        try:
            qty = int(qty_s)
        except ValueError:
            continue
        if qty < 2 or base is None:
            parts.append(f"{qty}pc→{price_s} {currency}")
            continue
        try:
            bdec = Decimal(str(base))
            pdec = Decimal(str(price_s))
            compare = bdec * qty
            if compare > pdec:
                saved = compare - pdec
                parts.append(f"{qty}pc→{price_s} {currency} (save {saved})")
            else:
                parts.append(f"{qty}pc→{price_s} {currency}")
        except (InvalidOperation, ValueError, TypeError):
            parts.append(f"{qty}pc→{price_s} {currency}")
    if not parts:
        return ""
    return " | Bundles: " + "; ".join(parts)


def _build_master_negotiation_prompt(product):
    """Master negotiation prompt with dynamic product pricing + shipping context."""
    if not product:
        return ""
    name = (getattr(product, "name", None) or "Product").strip()
    description = (getattr(product, "description", None) or "").strip() or "No additional product details."
    regular_price = getattr(product, "price", None)
    lowest_price = getattr(product, "backup_price", None)
    currency = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    shipping_cost = (getattr(product, "delivery_options", None) or "").strip() or "Ask merchant policy (often free delivery)."

    regular_price_txt = f"{regular_price} {currency}" if regular_price is not None else f"Not set ({currency})"
    lowest_price_txt = (
        f"{lowest_price} {currency}" if lowest_price is not None else "Not configured. Do NOT invent a floor below merchant policy."
    )

    offer_block = format_product_offer_tiers_block(product)
    offer_section = f"\n\n{offer_block}\n" if offer_block else "\n"
    bundle_negotiation_bridge = ""
    if offer_block:
        bundle_negotiation_bridge = (
            "When quantity bundles are listed above, use those exact prices for the matching quantity. "
            "The steps below apply mainly to single-unit price talk; if the customer wants 2+ pieces or asks for deals, "
            "lead with the relevant bundle tier and explain savings vs buying the same quantity at single-unit price.\n\n"
        )

    return f"""
You are an elite, highly persuasive e-commerce sales representative. Your ultimate goal is to assist the customer, build desire for the product, and CLOSE THE SALE at the highest possible price.

[PRODUCT & PRICING CONTEXT]
- Product Name: {name}
- Product Details: {description}
- Standard Price: {regular_price_txt}
- Absolute Lowest Price (Floor): {lowest_price_txt}
- Shipping Cost: {shipping_cost}
{offer_section}
[STRICT NEGOTIATION PROTOCOL]
{bundle_negotiation_bridge}You must follow these steps sequentially. NEVER skip to the lowest price immediately.

1. THE INITIAL OFFER:
Always quote the Standard Price ({regular_price_txt}) plus shipping first. Focus heavily on the product's premium quality, benefits, and solve the customer's pain point. Do NOT mention any discounts in your first response.

2. FIRST CONCESSION (If customer hesitates or asks for a discount):
Do not drop the price drastically. Offer a small psychological win. Offer to waive the Shipping Cost (make it Free Shipping) OR give a tiny discount (e.g., 5%).
Condition: Tell them this is a special flash offer just for them if they confirm the order right now.

3. SECOND CONCESSION (If they still push back):
Drop the price to exactly halfway between your current offer and the Absolute Lowest Price. Frame it as: I will speak to my manager to get you a special wholesale price, but please keep this between us.

4. THE RED LINE (The Floor):
You can offer the Absolute Lowest Price ({lowest_price_txt}) ONLY as a last resort to save a dying deal.
CRITICAL RULE: NEVER, UNDER ANY CIRCUMSTANCES, ACCEPT OR OFFER A PRICE BELOW {lowest_price_txt}. If the customer insists on a price lower than this, politely and firmly decline, stating that this is already below cost and the absolute final price.

[CLOSING THE DEAL]
Once the customer agrees to a price, stop negotiating immediately. Swiftly transition to closing the order by asking for:
1. Full Name
2. Delivery Address
3. Phone Number

[TONE & LANGUAGE]
- Be warm, extremely polite, and use persuasive sales psychology (urgency, scarcity).
- MATCH THE CUSTOMER'S LANGUAGE EXACTLY. If they speak Moroccan Darija, reply in perfect, natural Moroccan Darija. If they speak French or Classical Arabic, match it. Act like a real human, not an AI.
""".strip()


def _french_bot_language_prefix(voice_notes_mode: bool) -> str:
    """Strict French corporate override; takes priority over Arabic voice-dialect prompts."""
    tts_note = ""
    if voice_notes_mode:
        tts_note = " Your output may be read aloud by TTS: use clear, formal French suitable for speech."
    return (
        "## SYSTEM OVERRIDE — LANGUAGE (ABSOLUTE PRIORITY)\n"
        "You are a professional corporate representative (Service Clientèle). "
        "You MUST reply STRICTLY in formal French. Use \"vous\" (vouvoiement). "
        "Be polite, corporate, and trustworthy. Do NOT use Arabic."
        + tts_note
        + "\n\nIgnore any Arabic dialect, Darija, or voice-accent instructions elsewhere in this prompt.\n\n"
        "---\n\n"
    )


def build_messages_payload_sales(conversation_messages, custom_instruction=None, product_context=None, trust_score=0, media_context=None, state_header=None, sales_stage=None, sentiment=None, market=None, agent_name=None, customer_phone=None, override_rules=None, required_order_fields=None, checkout_mode_label=None, product_id=None, merchant_id=None, voice_dialect=None, voice_notes_mode=False, voice_script_style=False, output_language=None, memory_summary=None, node_dialect_locked=False, node_language_code=None, node=None, bot_settings=None, target_dialect=None):
    """Build messages for the sales agent. Uses Elite Sales Consultant prompt when product_context is set (with trust_score, sales_stage, sentiment, market, agent_name).
    state_header: optional for session continuity. market: 'MA' or 'SA'. agent_name: e.g. Chuck or persona name so the AI thinks as that human.
    customer_phone: active WhatsApp number of the customer; injected as system note so the AI can use it when they say 'same number' / نفس الرقم.
    override_rules: optional channel-level admin rules; injected at the very start of the system prompt so the model MUST follow them.
    checkout_mode_label: human-readable mode (e.g. 'Standard COD (Name, Phone, City)') for prompt injection.
    voice_dialect: human-readable dialect label (e.g. Moroccan Darija) aligned with the selected TTS voice.
    voice_notes_mode: when True (channel voice notes on or node may emit TTS), inject strict dialect rule so LLM matches the voice.
    voice_script_style: when True, prepend AUDIO SCRIPT MODE (conversational TTS); when False, TEXT MESSAGING MODE (structured chat).
    output_language: None | 'fr' | 'ar' | 'en' — from channel voice_language. When 'fr', Arabic dialect/TTS coupling is skipped.
    memory_summary: optional summarized long-term customer facts from older chat history.
    node_dialect_locked: deprecated compatibility arg (ignored by dialect routing engine).
    node_language_code: deprecated compatibility arg (ignored when ``node`` is provided).
    node: active flow node used by intelligent model routing.
    bot_settings: global channel/bot settings dict (fallback when node has no language)."""
    catalog_is_empty = _is_catalog_empty_for_merchant(merchant_id=merchant_id)
    admin_rules_prefix = ""
    if override_rules and (override_rules or "").strip():
        rules_text = (override_rules or "").strip()
        admin_rules_prefix = (
            "## CRITICAL — Admin override rules (you MUST follow these in every reply)\n\n"
            + rules_text
            + "\n\n---\n\n"
        )
        logger.info(
            "Admin override rules applied to sales prompt (length=%d, preview=%s)",
            len(rules_text),
            (rules_text[:100] + "…") if len(rules_text) > 100 else rules_text,
        )
    resolved_dialect = (target_dialect or "").strip() or "Standard Arabic"
    language_rule_prefix = (
        "STRICT PERSONA WALL: "
        f"You are a local sales assistant operating EXCLUSIVELY in {resolved_dialect}. "
        f"You MUST mentally translate any context, product descriptions, or user messages into authentic {resolved_dialect} before replying. "
        "Do NOT use formal Standard Arabic (Fus'ha) unless requested. Be conversational, culturally accurate, and brief.\n\n---\n\n"
    )
    if product_context and (product_context or "").strip():
        system = _master_sales_closer_prompt(
            (product_context or "").strip(),
            trust_score=trust_score,
            sales_stage=sales_stage,
            sentiment=sentiment,
            market=market,
            agent_name=agent_name,
        )
    else:
        system = SALES_AGENT_SYSTEM_PROMPT
        if agent_name and str(agent_name).strip():
            name = str(agent_name).strip()
            system = (
                f"You are {name}, a human sales rep. Think and respond as a real person, not a bot. "
                "Never say you are an AI or assistant. Write like a human on WhatsApp.\n\n"
            ) + system
    if voice_script_style:
        mode_line = (
            "AUDIO SCRIPT MODE: Write a highly conversational, flowing script. Use human filler words. "
            "NO emojis, NO markdown, NO bullet points. Prioritize the exact dialect of the selected voice. "
            "In Arabic, never separate list items with commas only — use 'و' / 'أو' so audio does not sound staccato.\n\n"
        )
    else:
        mode_line = (
            "TEXT MESSAGING MODE: Write a structured WhatsApp message. Use emojis naturally, line breaks, "
            "and bullet points for readability. Be concise.\n\n"
        )
    lang_prefix = ""
    if output_language == "fr":
        lang_prefix = _french_bot_language_prefix(voice_notes_mode)
    system = admin_rules_prefix + language_rule_prefix + lang_prefix + mode_line + system
    # Remove legacy dialect-lock/matrix lines to keep routing model-agnostic and avoid contamination.
    system = _strip_moroccan_default_instructions_for_tts(system)
    if memory_summary and str(memory_summary).strip():
        system = (
            "CUSTOMER PROFILE / FACTS (summarized memory from earlier conversation):\n"
            + str(memory_summary).strip()
            + "\n\n---\n\n"
            + system
        )
    negotiated_product = _resolve_product_for_prompt(product_id=product_id, merchant_id=merchant_id)
    if negotiated_product:
        system = _build_master_negotiation_prompt(negotiated_product) + "\n\n---\n\n" + system
    if state_header and (state_header or "").strip():
        system = (state_header.strip() + "\n\n") + system
    # Dynamic COD / Checkout mode: tell the AI exactly which fields are required for this product
    if required_order_fields:
        fields_list_str = _format_required_fields_list(required_order_fields)
        if fields_list_str:
            # Explicitly override any earlier global rules that mentioned address/city/extra slots
            override_prefix = (
                "\n\n🚨 CRITICAL OVERRIDE — PRODUCT CHECKOUT MODE TAKES PRIORITY\n"
                "For THIS conversation and THIS product, the checkout mode below OVERRIDES any earlier rules in this prompt "
                "that talked about collecting name + phone + address/city together. Ignore any generic instructions that "
                "say you MUST always collect address or city or 4 fields. Follow ONLY the field list defined for this product.\n"
            )
            if checkout_mode_label:
                system += (
                    override_prefix
                    + f"For this specific product, you are operating in [{checkout_mode_label}] mode. "
                    f"You MUST ONLY ask the customer for these specific details: {fields_list_str}. "
                    "Do NOT ask for any other shipping data or extra address details that are not in this list. "
                    "Once you have these exact fields, call the order submission tool."
                )
            else:
                system += (
                    override_prefix
                    + "CRITICAL: To place an order for this specific product, you MUST collect ONLY the following information: "
                    f"{fields_list_str}. Do NOT ask for any other information like city, full address, or ZIP code unless it is in this list. "
                    "Once you have these exact fields, call the order submission tool."
                )
    # Context resumption: when customer returns with "Hello" / "مرحبا", use history to resume, not generic greeting
    system += "\n" + CONTEXT_RESUMPTION_RULE
    # System context injection: give the LLM the customer's WhatsApp number so it can pass it into
    # submit_customer_order when the user indicates (in any language/dialect) they want to use it.
    if customer_phone and str(customer_phone).strip():
        system += (
            f"\n\n[SYSTEM: The user's active WhatsApp number is {str(customer_phone).strip()}. "
            "Use this number in submit_customer_order whenever the user indicates in any language, dialect, or phrasing "
            "(e.g. same number, نفس الرقم, نمرتي هادي, yes, اللي كاين) that they want to use their current chatting number. "
            "Do not ask again — pass this number into the phone_number parameter.]"
        )
    system += (
        "\n\n[SALES_BASE_RULES - MEDIA TOOL — ABSOLUTE RULE]\n"
        "🚫 FORBIDDEN — NEVER DO THIS:\n"
        "- NEVER write image URLs in your text (e.g. https://...s3.amazonaws.com/...)\n"
        "- NEVER use markdown image syntax ![name](url)\n"
        "- NEVER paste any link ending in .jpg/.png/.webp/.gif\n"
        "WhatsApp CANNOT render markdown images. They appear as ugly broken text to the customer.\n\n"
        "✅ CORRECT WAY TO SHOW IMAGES:\n"
        "- Call send_product_media(product_id, caption) for each product — this sends a REAL WhatsApp photo.\n"
        "- In your TEXT reply, list products by name and price ONLY (no URLs).\n\n"
        "EXAMPLE — WRONG:\n"
        "'عندنا كريم الايكل - 199 MAD ![كريم الايكل](https://example.com/img.jpg)'\n"
        "EXAMPLE — CORRECT:\n"
        "'عندنا كريم الايكل - 199 MAD' + call send_product_media(product_id='5', caption='كريم الايكل - 199 MAD')\n\n"
        "When listing catalog products:\n"
        "1. Write a short text listing product names + prices (no URLs).\n"
        "2. Call send_product_media(product_id, caption) ONCE for EACH product that has '📷 has image' in the catalog.\n"
        "3. If the user asks for a photo/image/صورة, call send_product_media IMMEDIATELY."
    )
    # Product photo: send from media when asked, or ask which product when no image
    if media_context and (media_context or "").strip():
        system += (
            f"\n\n--- MEDIA ASSETS (product photos/videos) ---\n{media_context.strip()}\n"
            "**PRODUCT PHOTO RULE:** When the customer asks for a photo/image/picture of the product "
            "(e.g. واش تقدر ترسل صورة، صورة المنتج، صورة، image, photo, send me the pic, show me the product), "
            "you MUST send an image: use [SEND_MEDIA: <id>] for media assets listed above by ID, or [SEND_PRODUCT_IMAGE] if "
            "\"Product photo (from catalog)\" is listed. Use exactly one tag per asset. You may add a short caption. "
            "Do not send media unless the customer asked for it or it is highly relevant."
        )
    elif product_context and (product_context or "").strip():
        system += (
            "\n\n**PRODUCT PHOTO (no image attached):** If the customer asks for a photo/image of the product, "
            "you do not have an image in this context. Politely ask which product they want to see (e.g. واش بغيتي نشوف ليك صورة دابا؟ عندنا بزاف د المنتجات، واش واحد بغيتي؟ / Which product would you like to see?)."
        )
    else:
        system += (
            "\n\n**PRODUCT PHOTO:** If the customer asks for a photo or image of a product, "
            "ask them which product they want to see (e.g. We have several products—which one would you like a photo of? / واش بغيتي صورة ديال شي منتج معين؟)."
        )
    if custom_instruction:
        # When category persona is present, make it mandatory so the AI takes over as that persona (e.g. Wellness Advisor for health_and_supplements)
        if "## Persona" in (custom_instruction or ""):
            system += (
                "\n\n--- MANDATORY CATEGORY PERSONA (take over as this for the entire conversation) ---\n"
                "You MUST adopt and stay in the following persona for every message. "
                "Do not respond as a generic sales rep; respond as this specific category persona (e.g. Wellness Advisor for health/supplements, Beauty Consultant for beauty). "
                "Use this persona's tone, framework, and style in every reply.\n\n"
            )
        system += f"\n\n{custom_instruction}"

    # Empty catalog kill-switch: highest-priority safety instruction.
    if catalog_is_empty:
        system += "\n\n---\n\n" + EMPTY_CATALOG_GUARDRAIL

    # Extreme negative prompt injection: MUST be at the very bottom so it has ultimate priority.
    # When product is in quick_lead mode, the LLM must never ask for city/address/location.
    is_quick_lead = (
        required_order_fields is not None
        and set(required_order_fields) == {"customer_name", "phone_number"}
    )
    if is_quick_lead:
        system += (
            "\n\n"
            "🚨 CRITICAL OVERRIDE: You are in QUICK LEAD mode. "
            "You MUST ONLY collect the customer's Name and Phone Number. "
            "It is STRICTLY FORBIDDEN to ask for their city, address, or location. "
            "Once you have the name and phone, you MUST call the tool immediately."
        )

    recent_messages = _trim_conversation_messages(conversation_messages, limit=MAX_CHAT_HISTORY_MESSAGES)
    messages = [{"role": "system", "content": system}]
    for msg in recent_messages:
        role = "user" if msg.get("role") == "customer" else "assistant"
        messages.append({"role": role, "content": msg.get("body", "") or ""})
    if not recent_messages or recent_messages[-1].get("role") == "agent":
        messages.append({"role": "user", "content": "(Generate the next reply to the customer.)"})
    return messages


HANDOVER_TAG_RE = re.compile(r"\[HANDOVER\]\s*", re.IGNORECASE)


def parse_and_strip_handover(reply_text):
    """If reply starts with [HANDOVER], strip it and return (cleaned_text, reason). reason is set for HITL."""
    if not reply_text or not isinstance(reply_text, str):
        return (reply_text or "", None)
    text = reply_text.strip()
    m = HANDOVER_TAG_RE.match(text)
    if not m:
        return (text, None)
    cleaned = text[m.end() :].strip()
    if not cleaned:
        cleaned = "I'm transferring you to a human specialist who can help you better with this."
    return (cleaned, "Customer asked for human or sentiment detected")


def parse_and_strip_stage(reply_text):
    """If reply ends with [STAGE: ...], strip it and return (cleaned_text, stage). Supports funnel and goal stages."""
    if not reply_text or not isinstance(reply_text, str):
        return (reply_text or "", None)
    m = STAGE_TAG_RE.search(reply_text.strip())
    if not m:
        return (reply_text.strip(), None)
    raw = m.group(1).strip()
    stage_lower = raw.lower()
    allowed = {s.lower() for s in SALES_FUNNEL_STAGES}
    if stage_lower not in allowed:
        return (reply_text.strip(), None)
    # Prefer canonical goal stage names (e.g. STAGE_1_GREETING) when matching
    for canonical in SALES_FUNNEL_STAGES:
        if canonical.lower() == stage_lower:
            stage = canonical
            break
    else:
        stage = raw
    cleaned = reply_text[: m.start()].strip() + reply_text[m.end() :].strip()
    return (cleaned, stage)


def generate_reply_with_tools(conversation_messages, custom_instruction=None, product_context=None, trust_score=0, media_context=None, state_header=None, sales_stage=None, sentiment=None, market=None, agent_name=None, model=None, customer_phone=None, override_rules=None, required_order_fields=None, checkout_mode_label=None, product_id=None, merchant_id=None, voice_dialect=None, voice_notes_mode=False, voice_script_style=False, output_language=None, memory_summary=None, node_dialect_locked=False, node_language_code=None, node=None, bot_settings=None):
    """
    Call OpenAI with sales tools. When product_context is set, uses Elite Sales Consultant prompt with trust_score, sales_stage, sentiment, market, agent_name.
    market: 'MA' or 'SA'. agent_name: e.g. Chuck or persona name — AI responds as this human, not as a bot.
    customer_phone: customer's WhatsApp number; injected into system prompt so the AI can use it when they say "same number".
    override_rules: optional admin rules; injected at the start of the system prompt so the model MUST follow them.
    voice_dialect: human-readable dialect for the selected TTS voice (voice–dialect coupling).
    voice_notes_mode: inject strict TTS dialect instruction (channel voice notes or node audio mode).
    voice_script_style: AUDIO SCRIPT vs TEXT MESSAGING mode line (voice vs structured chat).
    output_language: None | 'fr' | 'ar' | 'en' from channel settings (French skips Arabic dialect prompts).
    memory_summary: summarized key customer facts from older conversation history.
    """
    routed_model, target_dialect = resolve_ai_brain(node, customer_phone)
    model = model or routed_model
    _prepare_litellm_provider_key(model)
    messages = build_messages_payload_sales(
        conversation_messages,
        custom_instruction=custom_instruction,
        product_context=product_context,
        trust_score=trust_score,
        media_context=media_context,
        state_header=state_header,
        sales_stage=sales_stage,
        sentiment=sentiment,
        market=market,
        agent_name=agent_name,
        customer_phone=customer_phone,
        override_rules=override_rules,
        required_order_fields=required_order_fields,
        checkout_mode_label=checkout_mode_label,
        product_id=product_id,
        merchant_id=merchant_id,
        voice_dialect=voice_dialect,
        voice_notes_mode=voice_notes_mode,
        voice_script_style=voice_script_style,
        output_language=output_language,
        memory_summary=memory_summary,
        node_dialect_locked=node_dialect_locked,
        node_language_code=node_language_code,
        node=node,
        bot_settings=bot_settings,
        target_dialect=target_dialect,
    )
    # Static tools: submit_customer_order now has a fixed, safe schema (no dynamic override)
    tools = list(SALES_AGENT_TOOLS)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.6,
        "tools": tools,
        "tool_choice": "auto",
    }

    est_tokens = _estimate_payload_tokens(messages)
    logger.info("LiteLLM payload estimate: ~%s tokens (messages=%s, model=%s, dialect=%s)", est_tokens, len(messages), model, target_dialect)
    print(f"[LiteLLM payload estimate] ~{est_tokens} tokens (messages={len(messages)}, model={model})")
    _debug_print_sales_agent_system_prompt(
        messages, voice_dialect=voice_dialect, voice_notes_mode=voice_notes_mode, output_language=output_language
    )

    try:
        response = completion(**payload)
    except Exception as e:
        raise RuntimeError(f"LiteLLM completion failed: {e}")

    choice0 = response.choices[0] if getattr(response, "choices", None) else {}
    msg = getattr(choice0, "message", None) or {}
    if not isinstance(msg, dict):
        msg = {
            "content": getattr(msg, "content", "") or "",
            "tool_calls": getattr(msg, "tool_calls", None) or [],
        }
    reply_text = (msg.get("content") or "").strip()
    tool_calls = []
    import json
    normalized_tool_calls = []
    for tc in msg.get("tool_calls") or []:
        if isinstance(tc, dict):
            tc_dict = tc
        else:
            fn_obj = getattr(tc, "function", None)
            if isinstance(fn_obj, dict):
                fn_dict = fn_obj
            else:
                fn_dict = {
                    "name": getattr(fn_obj, "name", None),
                    "arguments": getattr(fn_obj, "arguments", None),
                }
            tc_dict = {
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": fn_dict,
            }
        normalized_tool_calls.append(tc_dict)
        fn = tc_dict.get("function", {})
        name = fn.get("name")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception as e:
            logger.warning("parse tool %s arguments: %s", name, e)
            continue
        if name in ("save_order", "check_stock", "apply_discount", "record_order", "track_order", "search_products", "send_product_media", "submit_customer_order", "update_lead_status", "add_upsell_to_existing_order"):
            tool_calls.append({"name": name, "arguments": args})
    msg["tool_calls"] = normalized_tool_calls
    usage_obj = getattr(response, "usage", None) or {}
    usage = usage_obj if isinstance(usage_obj, dict) else {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
        "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
    }
    # Strip [STAGE: ...] from reply and expose for funnel state tracking
    reply_clean, stage = parse_and_strip_stage(reply_text)
    # Strip [HANDOVER] and set flag for HITL (human-in-the-loop)
    reply_clean, handover_reason = parse_and_strip_handover(reply_clean)

    return {
        "reply": reply_clean,
        "stage": stage,
        "handover": handover_reason is not None,
        "handover_reason": handover_reason or "",
        "tool_calls": tool_calls,
        "raw_message": msg,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model": model,
    }


def continue_after_tool_calls(
    conversation_messages,
    first_assistant_message,
    tool_results,
    custom_instruction=None,
    product_context=None,
    trust_score=0,
    media_context=None,
    state_header=None,
    sales_stage=None,
    sentiment=None,
    market=None,
    agent_name=None,
    model=None,
    customer_phone=None,
    override_rules=None,
    product_id=None,
    merchant_id=None,
    voice_dialect=None,
    voice_notes_mode=False,
    voice_script_style=False,
    output_language=None,
    memory_summary=None,
    node_dialect_locked=False,
    node_language_code=None,
    node=None,
    bot_settings=None,
):
    """
    After the model returned tool_calls (e.g. check_stock, apply_discount), send tool results and get the final reply.
    first_assistant_message: dict from OpenAI with "content" and "tool_calls" (each with "id").
    tool_results: list of dicts {"tool_call_id": "...", "content": "result text"}.
    """
    routed_model, target_dialect = resolve_ai_brain(node, customer_phone)
    model = model or routed_model
    _prepare_litellm_provider_key(model)
    messages = build_messages_payload_sales(
        conversation_messages,
        custom_instruction=custom_instruction,
        product_context=product_context,
        trust_score=trust_score,
        media_context=media_context,
        state_header=state_header,
        sales_stage=sales_stage,
        sentiment=sentiment,
        market=market,
        agent_name=agent_name,
        customer_phone=customer_phone,
        override_rules=override_rules,
        product_id=product_id,
        merchant_id=merchant_id,
        voice_dialect=voice_dialect,
        voice_notes_mode=voice_notes_mode,
        voice_script_style=voice_script_style,
        output_language=output_language,
        memory_summary=memory_summary,
        node_dialect_locked=node_dialect_locked,
        node_language_code=node_language_code,
        node=node,
        bot_settings=bot_settings,
        target_dialect=target_dialect,
    )
    assistant_msg = {
        "role": "assistant",
        "content": first_assistant_message.get("content") or "",
        "tool_calls": first_assistant_message.get("tool_calls") or [],
    }
    tool_msgs = [
        {"role": "tool", "tool_call_id": r["tool_call_id"], "content": str(r.get("content", ""))}
        for r in tool_results
    ]
    messages = messages + [assistant_msg] + tool_msgs
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.6,
        "tools": SALES_AGENT_TOOLS,
        "tool_choice": "auto",
    }
    est_tokens = _estimate_payload_tokens(messages)
    logger.info("LiteLLM payload estimate (after tools): ~%s tokens (messages=%s, model=%s, dialect=%s)", est_tokens, len(messages), model, target_dialect)
    print(f"[LiteLLM payload estimate][after tools] ~{est_tokens} tokens (messages={len(messages)}, model={model})")
    _debug_print_sales_agent_system_prompt(
        messages, voice_dialect=voice_dialect, voice_notes_mode=voice_notes_mode, output_language=output_language
    )
    try:
        response = completion(**payload)
    except Exception as e:
        raise RuntimeError(f"LiteLLM completion failed: {e}")
    choice0 = response.choices[0] if getattr(response, "choices", None) else {}
    msg = getattr(choice0, "message", None) or {}
    if not isinstance(msg, dict):
        msg = {
            "content": getattr(msg, "content", "") or "",
            "tool_calls": getattr(msg, "tool_calls", None) or [],
        }
    reply_text = (msg.get("content") or "").strip()
    tool_calls = []
    import json as _json
    normalized_tool_calls = []
    for tc in msg.get("tool_calls") or []:
        if isinstance(tc, dict):
            tc_dict = tc
        else:
            fn_obj = getattr(tc, "function", None)
            if isinstance(fn_obj, dict):
                fn_dict = fn_obj
            else:
                fn_dict = {
                    "name": getattr(fn_obj, "name", None),
                    "arguments": getattr(fn_obj, "arguments", None),
                }
            tc_dict = {
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": fn_dict,
            }
        normalized_tool_calls.append(tc_dict)
        fn = tc_dict.get("function", {})
        name = fn.get("name")
        try:
            args = _json.loads(fn.get("arguments") or "{}")
        except Exception as e:
            logger.warning("parse tool %s arguments: %s", name, e)
            continue
        if name in ("save_order", "check_stock", "apply_discount", "record_order", "track_order", "search_products", "send_product_media", "submit_customer_order", "update_lead_status", "add_upsell_to_existing_order"):
            tool_calls.append({"name": name, "arguments": args})
    msg["tool_calls"] = normalized_tool_calls
    usage_obj = getattr(response, "usage", None) or {}
    usage = usage_obj if isinstance(usage_obj, dict) else {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
        "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
    }
    reply_clean, stage = parse_and_strip_stage(reply_text)
    reply_clean, handover_reason = parse_and_strip_handover(reply_clean)
    return {
        "reply": reply_clean,
        "stage": stage,
        "handover": handover_reason is not None,
        "handover_reason": handover_reason or "",
        "tool_calls": tool_calls,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model": model,
    }
