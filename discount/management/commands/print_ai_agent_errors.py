"""
Print all AI-agent-related errors and why the agent sometimes doesn't reply or crashes.
Usage: python manage.py print_ai_agent_errors
"""
from django.core.management.base import BaseCommand


def get_catalog_text():
    return r"""
================================================================================
AI AGENT ERROR CATALOG
================================================================================
Lists all errors related to the AI agent and explains:
  - Why the agent sometimes does NOT reply to the customer
  - Why it sometimes "crashes" (handoff or error message)
================================================================================

1. WHY THE AGENT SOMETIMES DOES NOT REPLY
--------------------------------------------------------------------------------
- HITL: Session has ai_enabled=False
  → No automated reply. Merchant gets handover_new_message; they reply manually.
  → File: process_messages.py (HITL gatekeeper), continue

- Channel autopilot off (ai_auto_reply=False)
  → No reply. File: process_messages.py, continue

- Empty AI reply (LLM/tools returned no text; we don't send fallback)
  → Log: "AI agent returned empty reply (channel=..., sender=...); no fallback message sent."
  → File: process_messages.py inside run_ai_agent_node

- Voice/fallback path: empty reply
  → if not reply_text: return → No reply.
  → Log: "AI voice/fallback returned empty reply ...; no fallback message sent."

- Voice path: generate_reply_with_tools exception
  → Log: "generate_reply_with_tools failed: ..." then return → No reply.

- Voice path: plan or imports (PermissionDenied / ImportError)
  → Log: "AI auto-reply skipped: plan does not allow auto_reply" or "AI voice reply imports failed"

- continue_after_tool_calls failed (after tools ran)
  → Reply may be missing or wrong. Log: "continue_after_tool_calls failed: ..."

- submit_customer_order returned success=false
  → AI is expected to relay error; if AI returns empty, customer gets no reply.
  → Log: "submit_customer_order failed (channel=..., sender=...): ..."

- Product/seller not linked in node
  → Tool returns error JSON; if next turn empty or fails, no reply.
  → Log: "_execute_submit_customer_order: no product_id in node ai_model_config" or "channel has no owner"


2. WHY THE AGENT SOMETIMES "CRASHES" (HANDOFF OR ERROR MESSAGE)
--------------------------------------------------------------------------------
- Uncaught exception in run_ai_agent_node
  → Customer sees: "عندي مشكل تقني بسيط، فريقنا غادي يتواصل معاك قريباً."
  → Session: ai_enabled=False, handover_reason="Backend error (tool or LLM)", HandoverLog created.
  → Log: logger.exception("run_ai_agent_node failed: %s", e)
  → File: process_messages.py

- Handoff on AI error (session update fails)
  → Log: "Handoff on AI error failed: ..."

- submit_customer_order: DB/validation failure
  → Tool returns success=False with SYSTEM ERROR; AI instructed to apologize and not retry.
  → On unexpected exception: Log "FATAL TOOL ERROR -> ..." / "FATAL TOOL ERROR (stack) -> ..."
  → File: orders_ai.py (handle_submit_order_tool), process_messages.py (_execute_submit_customer_order)

- submit_customer_order: channel/product/seller missing
  → Log: "Channel or product context missing" / "no product_id in node ai_model_config" / "channel has no owner"

- save_order_from_ai exception
  → Log: logger.exception("save_order_from_ai failed: %s", e). Returns None.

- OpenAI API errors (timeout, rate limit, status code)
  → Exceptions propagate to run_ai_agent_node → handoff message + ai_enabled=False.
  → File: ai_assistant/services.py (generate_reply_with_tools, continue_after_tool_calls)


3. LOG MESSAGES BY FILE (KEY PHRASES TO GREP)
--------------------------------------------------------------------------------
process_messages.py:
  _execute_submit_customer_order: no product_id in node
  _execute_submit_customer_order: channel has no owner
  _execute_submit_customer_order: (exception)
  submit_customer_order failed
  continue_after_tool_calls failed
  AI agent returned empty reply
  run_ai_agent_node failed
  Handoff on AI error failed
  HITL handover update
  generate_reply_with_tools failed
  AI voice/fallback returned empty reply

orders_ai.py:
  get_or_create_ai_agent_user failed
  handle_submit_order_tool: product_id=... not found
  FATAL TOOL ERROR
  save_order_from_ai: channel and customer_phone required
  save_order_from_ai: rejected
  save_order_from_ai failed
  _notify_owner_order_created failed

ai_assistant/services.py:
  OpenAI API error
  OPENAI_API_KEY is not set
  (Raises: Timeout, ConnectionError, RuntimeError for status code)


4. SYSTEM ERROR MESSAGES RETURNED TO THE AI (TOOL RESULT)
--------------------------------------------------------------------------------
- Channel or product context missing.
- No product is selected in this conversation. The merchant must link a product...
- Channel not configured.
- Order could not be processed. Please try again. / Tool execution failed in the backend.
- Invalid arguments. Politely ask the customer again...
- Product no longer available. Ask the customer to choose another product.
- Customer name is missing. / Delivery city or address is missing. / The phone number is missing...
- Store mismatch. Please try again.
- A duplicate order was detected...
- Failed to save to DB. Reason: ... Do not retry the tool.
- The product price could not be determined (price is 0 or missing)...

================================================================================
Full doc: docs/AI_AGENT_ERROR_CATALOG.md
================================================================================
"""


class Command(BaseCommand):
    help = "Print all AI-agent-related errors and why the agent sometimes doesn't reply or crashes."

    def handle(self, *args, **options):
        self.stdout.write(get_catalog_text())
