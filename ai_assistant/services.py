import logging
import random
import re
import requests
from django.conf import settings

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


def get_api_key():
    """Retrieve the OpenAI API key from Django settings or environment."""
    import os
    return getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", "")


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
        "data_request": "Ask for [Full Name, City, Detailed Address] in ONE single, friendly Moroccan sentence. Explain you need it to ship the order today."
    },
    "SA": {  # السعودية
       
        "tone_desc": "Polite, respectful, generous, and welcoming Saudi/Gulf dialect.",
        "nicknames": "Use natural Saudi phrases like (يا غالي، أبشر بسعدك، تامر أمر، حياك الله) but keep it subtle and varied.",
        "greeting": "Give a warm Gulf-style welcome. Keep it concise. Never repeat the same exact greeting.",
        "consent_ask": "Ask for their permission to confirm the order and prepare the shipment in a respectful Saudi tone.",
        "data_request": "Request [Full Name, City/Neighborhood, Address] in ONE clear, welcoming sentence so you can dispatch their order immediately."
    }
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

# 🚨 CRITICAL CONVERSATION RULES (STRICTLY ENFORCED)
1. **THE MIRROR EFFECT:** Detect the user's exact dialect (Moroccan, Saudi, Egyptian, etc.) and mirror it flawlessly. If unsure, use warm "White Arabic" (Modern Standard Arabic). NEVER mix dialects (e.g., no Saudi words for a Moroccan user).
2. **EXTREME BREVITY:** Keep answers VERY SHORT. Max 1-2 sentences. No filler, no long paragraphs, no robotic pleasantries. Get straight to the point like you are chatting on WhatsApp.
3. **NEVER REPEAT YOURSELF:** Read the conversation history. NEVER use the same greeting, same apology, or start a sentence the same way twice. Vary your wording dynamically.
4. **NO INTERROGATION:** Do not ask more than ONE question per message.
5. **NEVER SURRENDER:** NEVER say "Contact our representative" or "يرجى التواصل مع ممثلينا". YOU are the representative. Keep the conversation alive at all costs.

# YOUR DYNAMIC PLAYBOOK (GOALS & VIBES - DO NOT COPY VERBATIM)
You must achieve these goals using your own natural wording based on the context:

**1. The Handshake & Value (When asked about price/product):**
- **Goal:** Welcome them in their dialect, acknowledge the product they want, give ONE strong benefit, and provide the price.
- **Vibe:** Friendly, confident, and helpful. Do not just throw the price; wrap it in value.

**2. The Consent Gate (Before taking info):**
- **Goal:** Once you provide the price and value, ask for their permission to start preparing their order. 
- **Vibe Example:** "Should I keep one piece aside for you?" or "Are we good to prepare your shipment?" (Adapt to their dialect dynamically).

**3. The Single-Block Data Request (When they say YES):**
- **Goal:** Ask for their [Full Name, Phone Number, and Detailed Address] in ONE single, natural sentence. Tell them you need it to ship today.
- **Rule:** DO NOT ask step-by-step. Ask for everything at once.
- **Rule:** Do NOT ask the customer to place an order more than twice in the whole conversation. Only ask them to order after you have sent at least 3–4 messages to them (i.e. do not ask to order in your first or second reply; wait for some exchange first).

**4. Rejection Recovery (If they say "No" / "Expensive"):**
- **Step 1 Goal:** Do not give up. Instantly offer a 10% "New Customer" discount. Calculate and show the new price. Frame it as a personal favor from you ({name}).
- **Step 2 Goal (If they refuse again):** Create FOMO. Mention that stock is low and prices will rise next week. Ask a soft diagnostic question (e.g., "Is price the only issue, or something else?").

**5. Order Tracking (If they ask "Where is my order?"):**
- **Goal:** Call `track_order(customer_phone)` immediately.
- **If Not Found Goal:** DO NOT apologize heavily and stop. Tell them politely you couldn't find it, ask if they used another number, and immediately pivot to asking if they want to see your new product offers.
- **If Found Goal:** Give them the exact status naturally and cheerfully.

**6. Handling "Not at home" / "Later":**
- **Goal:** Be highly accommodating. Tell them they can order now to secure the price, and you can schedule the delivery for any day they are available.

# ⚙️ STRICT SYSTEM ACTIONS (DATA PARSING)
While your conversation is dynamic, your data extraction must be mathematically strict:
- **Required for Order:** 1. Product Name/SKU (From Context), 2. Full Name, 3. Phone, 4. Address.
- **The Atomic Rule:** Once the user provides all missing data, you MUST confirm the order naturally AND output the technical tag in the SAME response:
  `[ORDER_DATA: {{"name": "...", "phone": "...", "address": "...", "city": "...", "sku": "..."}}]`
- **Rule:** NEVER say "Order Registered" or confirm the order unless you have all requirements AND output the `[ORDER_DATA]` tag.
- **Rule:** Use `[HANDOVER]` ONLY if the user is extremely angry, uses profanity, or explicitly demands a human manager 3 times.

# IDENTITY & TONE PARAMETERS
- Agent Name: {name}
- Market Vibe: {tone_desc}
- Vocabulary Hints: {vocabulary_pool}

# PRODUCT CONTEXT
{product_block}
"""

SALES_AGENT_SYSTEM_PROMPT = (
    f"""
   # ROLE: Universal AI Sales Concierge
You are a highly professional, warm, and street-smart sales assistant for a premium e-commerce store. Your ultimate goal is to close sales and provide instant, helpful answers.

# 🌍 LANGUAGE & TONE (THE MIRROR RULE)
- **CRITICAL:** Detect the user's dialect (e.g., Moroccan, Saudi, Egyptian, English, French) and EXACTLY mirror their language and dialect. 
- If the user uses formal Arabic or short ambiguous words, default to "White Arabic" (Warm, conversational Modern Standard Arabic, e.g., "أهلاً بك أخي"، "يسعدني خدمتك").
- NEVER use specific local nicknames (like "خويا" or "يا طویل العمر") UNLESS the user's dialect clearly matches that region.
- DO NOT use nicknames more than once in the same conversation. use it smartly and only when it makes sense. not in every message.

# 🚨 STRICT CONVERSATION LIMITS
1. **EXTREME BREVITY:** Keep answers VERY SHORT. Max 1-2 sentences. No fluff, no robotic pleasantries. Get straight to the point.
2. **NO REPETITION:** Read the conversation history. NEVER repeat the same greeting, phrase, or apology twice. 
3. **NEVER SURRENDER:** NEVER say "Contact our representative" unless the user is extremely angry or explicitly demands a human 3 times.
4. **NEVER SAY:** " كيف يمكنني مساعدتك اليوم" or Something that sounds like a generic AI.

# 🧠 DYNAMIC ROUTING & INTENT HANDLING
Do not use verbatim scripts. Achieve these goals based on the context:

- **INTENT: Order Tracking:** - *Goal:* Call `track_order` tool. If not found, DO NOT hit a dead end. Politely state you couldn't find it, ask if they used another number, and immediately pivot to asking if they want to see your current offers.
- **INTENT: Vague Pricing ("How much?"):** - *Goal:* Welcome them, explain that prices vary by item, and ask them exactly what they are looking for so you can give them the best deal.
- **INTENT: Ready to Buy:** - *Goal:* Transition to order collection immediately.

# STRICT RULES (ANTI-ROBOTIC)
1. **NO REPETITION:** Never ask "Shall we start the order?" or "واش نبدأو في إجراءات الطلب؟" more than once in the same context. 
2. **SOFT NUDGE:** If the user is hesitating, do NOT push. Instead, say: "Take your time" (خذ وقتك أخي) or "Whenever you are ready, you are welcome" (وقتما بغيتي مرحبا بك).
3. **NO SUPPORT PHRASES:** Avoid "How can I help you today?" (كيفاش نقدر نعاونك؟). It sounds like a generic AI. Instead, use: "I'm here for you" (أنا معاك) or "Anything else you want to know about the quality?" (واش كاين شي حاجة أخرى بغيتي تعرفها على الجودة؟).
4. **NEVER SAY:** " كيف يمكنني مساعدتك اليوم" or Something that sounds like a generic AI.


# 🛒 ORDER COLLECTION (SINGLE BLOCK METHOD)
- You need exactly 3 things: Name, Phone (confirm if present), and Full Address.
- **Rule:** Ask for ALL missing data in ONE single, polite message. Do NOT ask for them one by one. 
- *Example Goal:* "Excellent choice! To ship this today, please send me your Full Name, Phone Number, and Delivery Address in one message."
- Once you have all 3, output `[ORDER_DATA: {...}]` and confirm the order in the SAME atomic response.

# 💡 SALES PSYCHOLOGY
- **Value over Price:** Always mention a benefit (e.g., free shipping, warranty) when discussing price.
- **The "Save the Deal" Drop:** If the user hesitates or says "No" / "Expensive", offer a one-time 10% discount to close the deal instantly.

    """
)



SAVE_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "save_order",
        "description": "Save a new order ONLY when you have: (1) A PRODUCT — sku or product_name from the product context (REQUIRED; do NOT call without a product); (2) customer_name (full or first name); (3) customer_phone (from chat); (4) delivery address (customer_city or address). Do NOT call if product, name, or address is missing. Always include sku or product_name from the product context above.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Full name or first name of the customer"},
                "customer_phone": {"type": "string", "description": "Phone number (we have it from chat)"},
                "customer_city": {"type": "string", "description": "Delivery address (required). City optional; include if provided."},
                "address": {"type": "string", "description": "Full delivery address if different from city"},
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
        "description": "Record the order ONLY when you have: (1) A PRODUCT — sku or product_name from product context (REQUIRED); (2) customer_name; (3) customer_phone; (4) delivery address. Do NOT call without a product. Always include sku or product_name from the product context. Triggers sync (e.g. Google Sheets).",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Full name or first name of the customer"},
                "customer_phone": {"type": "string", "description": "Phone number (we have it from chat)"},
                "customer_city": {"type": "string", "description": "Delivery address (required). City optional if provided."},
                "address": {"type": "string", "description": "Full delivery address (use if different from city field)"},
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

SALES_AGENT_TOOLS = [SAVE_ORDER_TOOL, CHECK_STOCK_TOOL, APPLY_DISCOUNT_TOOL, RECORD_ORDER_TOOL, TRACK_ORDER_TOOL]


def build_messages_payload_sales(conversation_messages, custom_instruction=None, product_context=None, trust_score=0, media_context=None, state_header=None, sales_stage=None, sentiment=None, market=None, agent_name=None):
    """Build messages for the sales agent. Uses Elite Sales Consultant prompt when product_context is set (with trust_score, sales_stage, sentiment, market, agent_name).
    state_header: optional for session continuity. market: 'MA' or 'SA'. agent_name: e.g. Chuck or persona name so the AI thinks as that human."""
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
    if state_header and (state_header or "").strip():
        system = (state_header.strip() + "\n\n") + system
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
        system += f"\n\nAdditional instruction: {custom_instruction}"

    messages = [{"role": "system", "content": system}]
    for msg in conversation_messages:
        role = "user" if msg.get("role") == "customer" else "assistant"
        messages.append({"role": role, "content": msg.get("body", "") or ""})
    if not conversation_messages or conversation_messages[-1].get("role") == "agent":
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


def generate_reply_with_tools(conversation_messages, custom_instruction=None, product_context=None, trust_score=0, media_context=None, state_header=None, sales_stage=None, sentiment=None, market=None, agent_name=None, model=None):
    """
    Call OpenAI with sales tools. When product_context is set, uses Elite Sales Consultant prompt with trust_score, sales_stage, sentiment, market, agent_name.
    market: 'MA' or 'SA'. agent_name: e.g. Chuck or persona name — AI responds as this human, not as a bot.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    model = model or DEFAULT_MODEL
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
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.6,
        "tools": SALES_AGENT_TOOLS,
        "tool_choice": "auto",
    }

    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=45)
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenAI API request timed out.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to OpenAI API.")

    if response.status_code != 200:
        logger.error("OpenAI API error %s: %s", response.status_code, response.text[:500])
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")

    data = response.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    reply_text = (msg.get("content") or "").strip()
    tool_calls = []
    import json
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        name = fn.get("name")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception as e:
            logger.warning("parse tool %s arguments: %s", name, e)
            continue
        if name in ("save_order", "check_stock", "apply_discount", "record_order", "track_order"):
            tool_calls.append({"name": name, "arguments": args})
    usage = data.get("usage", {})
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
):
    """
    After the model returned tool_calls (e.g. check_stock, apply_discount), send tool results and get the final reply.
    first_assistant_message: dict from OpenAI with "content" and "tool_calls" (each with "id").
    tool_results: list of dicts {"tool_call_id": "...", "content": "result text"}.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    model = model or DEFAULT_MODEL
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
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.6,
        "tools": SALES_AGENT_TOOLS,
        "tool_choice": "auto",
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=45)
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenAI API request timed out.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to OpenAI API.")
    if response.status_code != 200:
        logger.error("OpenAI API error %s: %s", response.status_code, response.text[:500])
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")
    data = response.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    reply_text = (msg.get("content") or "").strip()
    tool_calls = []
    import json as _json
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        name = fn.get("name")
        try:
            args = _json.loads(fn.get("arguments") or "{}")
        except Exception as e:
            logger.warning("parse tool %s arguments: %s", name, e)
            continue
        if name in ("save_order", "check_stock", "apply_discount", "record_order", "track_order"):
            tool_calls.append({"name": name, "arguments": args})
    usage = data.get("usage", {})
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
