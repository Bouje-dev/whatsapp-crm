"""
Dashboard AI Sales Copilot — LLM service layer with OpenAI function calling
and structured UI payloads for the frontend chat blocks.
"""
import json
import logging
import random

import requests
from django.conf import settings
from django.utils import timezone

from ai_assistant.services import get_api_key, UPDATE_OVERRIDE_RULES_TOOL, _openai_direct_model

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
COPILOT_MODEL = _openai_direct_model(getattr(settings, "COPILOT_MODEL", "gpt-4o-mini"))
MAX_COPILOT_HISTORY = 12
MAX_TOOL_ROUNDS = 4

DASHBOARD_COPILOT_SYSTEM_PROMPT = """You are the Dashboard AI Copilot for an e-commerce / SaaS sales platform (WhatsApp commerce, AI sales agents, persuasion rules, and order analytics).

Your role is a command center for store owners and team admins. You help them:
- Monitor sales performance and KPIs
- Adjust the AI sales agent's persuasion persona and selling style
- Interpret trends and recommend concrete next actions
- Answer questions about how the dashboard, rules, and AI agent behave

Behavior guidelines:
- Be concise, confident, and action-oriented — you are an operator's copilot, not a generic chatbot.
- When the user asks for metrics, numbers, or performance, call `get_sales_metrics` with an appropriate period (today, week, or month).
- When the user asks to change persona, tone, or selling style, call `update_persuasion_rule` with a recognized rule_name.
- In your natural-language replies, wrap key figures and names in **double asterisks** (e.g. **126 orders**, **$5,324**, **Starter Bundle**) so the dashboard can highlight them.
- You may call tools and also explain results in natural language in your final reply.
- If a request is ambiguous, ask one clarifying question instead of guessing.
- Never invent live database figures — use `get_sales_metrics` for numeric KPIs.
- Valid persuasion personas: Friendly Consultant, Aggressive Closer, Value Strategist, Empathetic Listener.
- When the admin gives a clear sales rule or instruction for the WhatsApp AI agent, you MUST call `update_override_rules` with custom_rules containing the full actionable rule (use numbered steps when order matters).
- Write custom_rules in imperative form the sales agent can follow literally. Example: "When customer asks about price: (1) state free shipping first, (2) explain product benefits, (3) give the price last."
- NEVER tell the admin that rules were saved/updated unless `update_override_rules` succeeded in this turn.

After tool calls, summarize what changed or what the data means in plain language."""

GET_SALES_METRICS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_sales_metrics",
        "description": (
            "Fetch sales KPIs for the dashboard (orders, revenue, conversion rate, top product). "
            "Use when the user asks about performance, stats, numbers, or analytics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "week", "month"],
                    "description": "Time window for metrics. Defaults to today.",
                },
            },
            "required": [],
        },
    },
}

UPDATE_PERSUASION_RULE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_persuasion_rule",
        "description": (
            "Switch the active AI sales persuasion persona / selling style. "
            "Use when the user wants a different tone or persona for the AI agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "description": (
                        "Persona name, e.g. Friendly Consultant, Aggressive Closer, "
                        "Value Strategist, or Empathetic Listener."
                    ),
                },
            },
            "required": ["rule_name"],
        },
    },
}

COPILOT_TOOLS = [
    GET_SALES_METRICS_TOOL,
    UPDATE_PERSUASION_RULE_TOOL,
    UPDATE_OVERRIDE_RULES_TOOL,
]

VALID_PERSONAS = {
    "friendly consultant": "Friendly Consultant",
    "aggressive closer": "Aggressive Closer",
    "value strategist": "Value Strategist",
    "empathetic listener": "Empathetic Listener",
}

# In-memory mock store for active persona per channel (replace with DB later).
_active_persona_by_channel = {}


def _normalize_period(period):
    p = (period or "today").strip().lower()
    if p in ("today", "week", "month"):
        return p
    if p in ("7d", "7days", "weekly"):
        return "week"
    if p in ("30d", "30days", "monthly"):
        return "month"
    return "today"


def _mock_metrics_seed(period):
    """Deterministic-ish mock data keyed by period."""
    base = {"today": 1, "week": 7, "month": 30}[period]
    rng = random.Random(base * 9973)
    orders = rng.randint(12, 48) * (1 if period == "today" else base // 2)
    revenue = round(orders * rng.uniform(28.0, 95.0), 2)
    conversion = round(rng.uniform(1.8, 6.4), 2)
    products = ["Gold Pack", "Starter Bundle", "Premium Kit", "Wellness Box", "Pro Subscription"]
    return {
        "period": period,
        "orders": orders,
        "revenue": revenue,
        "currency": "USD",
        "conversion_rate_pct": conversion,
        "avg_order_value": round(revenue / max(orders, 1), 2),
        "top_product": rng.choice(products),
        "generated_at": timezone.now().isoformat(),
    }


def mock_get_sales_metrics(period="today"):
    period = _normalize_period(period)
    data = _mock_metrics_seed(period)
    period_label = {"today": "Today", "week": "Last 7 days", "month": "Last 30 days"}[period]
    return {
        "success": True,
        "period": period,
        "period_label": period_label,
        "metrics": data,
    }


def mock_update_persuasion_rule(rule_name, channel_id=None):
    raw = (rule_name or "").strip()
    if not raw:
        return {"success": False, "error": "rule_name is required"}

    normalized = VALID_PERSONAS.get(raw.lower())
    if not normalized:
        for key, label in VALID_PERSONAS.items():
            if key in raw.lower() or label.lower() in raw.lower():
                normalized = label
                break
    if not normalized:
        normalized = raw.title()

    key = str(channel_id) if channel_id is not None else "global"
    _active_persona_by_channel[key] = normalized
    return {
        "success": True,
        "rule_name": normalized,
        "channel_id": channel_id,
        "updated_at": timezone.now().isoformat(),
    }


def get_active_persuasion_rule(channel_id=None):
    key = str(channel_id) if channel_id is not None else "global"
    return _active_persona_by_channel.get(key, "Friendly Consultant")


def execute_copilot_tool(tool_name, arguments, channel_id=None):
    """Run a single tool call and return a JSON-serializable result dict."""
    args = arguments if isinstance(arguments, dict) else {}
    if tool_name == "get_sales_metrics":
        return mock_get_sales_metrics(args.get("period") or "today")
    if tool_name == "update_persuasion_rule":
        return mock_update_persuasion_rule(args.get("rule_name"), channel_id=channel_id)
    if tool_name == "update_override_rules":
        if channel_id is None:
            return {"success": False, "error": "channel_id required for rule updates"}
        from discount.whatssapAPI.whaDash import handle_update_override_rules

        return handle_update_override_rules(channel_id, args.get("custom_rules"))
    return {"success": False, "error": f"Unknown tool: {tool_name}"}


def _metrics_to_component_data(tool_result):
    metrics = (tool_result or {}).get("metrics") or {}
    period_label = tool_result.get("period_label") or "Today"
    rows = [
        {"label": "Period", "value": period_label},
        {"label": "Orders", "value": str(metrics.get("orders", "—"))},
        {"label": "Revenue", "value": f"{metrics.get('currency', 'USD')} {metrics.get('revenue', '—')}"},
        {"label": "Conversion rate", "value": f"{metrics.get('conversion_rate_pct', '—')}%"},
        {"label": "Avg. order value", "value": f"{metrics.get('currency', 'USD')} {metrics.get('avg_order_value', '—')}"},
        {"label": "Top product", "value": str(metrics.get("top_product", "—"))},
    ]
    return {"rows": rows, "title": f"Sales metrics — {period_label}"}


def _persuasion_to_component_data(tool_result):
    if not tool_result.get("success"):
        return {
            "text": tool_result.get("error") or "Could not update persona.",
            "type": "error",
        }
    name = tool_result.get("rule_name") or "Unknown"
    return {"text": f"Rule updated: {name}", "type": "success"}


def build_structured_response(message, tool_results):
    """
    Map the assistant message + executed tool outputs to the frontend contract:
    { message, ui_component, component_data }
    """
    text = (message or "").strip()
    ui_component = "none"
    component_data = {}

    if not tool_results:
        return {
            "message": text or "How can I help with your dashboard today?",
            "ui_component": ui_component,
            "component_data": component_data,
        }

    # Prefer the most recent tool for UI rendering; metrics table wins over badge if both ran.
    last_metrics = None
    last_persuasion = None
    last_rules = None
    for tr in tool_results:
        name = tr.get("tool_name")
        result = tr.get("result") or {}
        if name == "get_sales_metrics" and result.get("success"):
            last_metrics = result
        elif name == "update_persuasion_rule":
            last_persuasion = result
        elif name == "update_override_rules":
            last_rules = result

    if last_metrics:
        ui_component = "data_table"
        component_data = _metrics_to_component_data(last_metrics)
    elif last_persuasion:
        ui_component = "status_badge"
        component_data = _persuasion_to_component_data(last_persuasion)
    elif last_rules:
        ui_component = "status_badge"
        if last_rules.get("success"):
            component_data = {"text": "Sales rules saved to AI agent", "type": "success"}
        else:
            component_data = {
                "text": last_rules.get("error") or "Could not update rules.",
                "type": "error",
            }

    if not text:
        if last_persuasion and last_persuasion.get("success"):
            text = f"Done — the AI agent is now using the **{last_persuasion.get('rule_name')}** persona."
        elif last_metrics:
            text = "Here are the latest sales metrics for your selected period."
        else:
            text = "I completed that action. What would you like to do next?"

    return {
        "message": text,
        "ui_component": ui_component,
        "component_data": component_data,
    }


def _call_openai(messages, tools=None, tool_choice="auto"):
    api_key = get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    payload = {
        "model": COPILOT_MODEL,
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.35,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    response = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    if response.status_code != 200:
        logger.error(
            "Copilot OpenAI error %s model=%r: %s",
            response.status_code,
            payload.get("model"),
            response.text[:500],
        )
        raise RuntimeError(f"OpenAI API returned status {response.status_code}.")

    data = response.json()
    choice = data.get("choices", [{}])[0]
    return choice.get("message", {}), data


def _normalize_chat_messages(messages):
    """Accept OpenAI-style user/assistant history from the client."""
    cleaned = []
    for m in messages or []:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content")
        if role in ("user", "assistant") and content is not None:
            cleaned.append({"role": role, "content": str(content)[:8000]})
    return cleaned[-MAX_COPILOT_HISTORY:]


def run_copilot_chat(messages, channel_id=None, extra_context=None):
    """
    Run the copilot conversation loop with function calling.

    Args:
        messages: list of {"role": "user"|"assistant", "content": "..."}
        channel_id: optional channel scope for persona updates
        extra_context: optional string appended to the system prompt

    Returns:
        dict with keys message, ui_component, component_data
    """
    history = _normalize_chat_messages(messages)
    if not history or history[-1].get("role") != "user":
        raise ValueError("The last message must be a user message.")

    system_content = DASHBOARD_COPILOT_SYSTEM_PROMPT
    if channel_id is not None:
        active = get_active_persuasion_rule(channel_id)
        system_content += f"\n\nCurrent channel_id: {channel_id}. Active persuasion persona: {active}."
    if extra_context:
        system_content += f"\n\nAdditional context:\n{extra_context[:4000]}"

    full_messages = [{"role": "system", "content": system_content}]
    full_messages.extend(history)

    tool_results = []
    final_content = ""

    for _ in range(MAX_TOOL_ROUNDS):
        assistant_msg, _raw = _call_openai(full_messages, tools=COPILOT_TOOLS, tool_choice="auto")
        tool_calls = assistant_msg.get("tool_calls") or []
        content = (assistant_msg.get("content") or "").strip()

        if not tool_calls:
            final_content = content
            break

        full_messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get("content"),
                "tool_calls": tool_calls,
            }
        )

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            result = execute_copilot_tool(name, args, channel_id=channel_id)
            tool_results.append({"tool_name": name, "arguments": args, "result": result})

            full_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": json.dumps(result),
                }
            )

        if content:
            final_content = content

    if not final_content and tool_results:
        # One more pass without tools so the model summarizes tool output.
        summary_msg, _raw = _call_openai(full_messages, tools=None)
        final_content = (summary_msg.get("content") or "").strip()

    result = build_structured_response(final_content, tool_results)
    result["rules_updated"] = any(
        tr.get("tool_name") == "update_override_rules"
        and (tr.get("result") or {}).get("success")
        for tr in tool_results
    )
    return result
