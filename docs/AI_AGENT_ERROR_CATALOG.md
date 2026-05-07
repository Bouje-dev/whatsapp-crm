# AI Agent Error Catalog

This document lists **all errors related to the AI agent**, where they are logged, and explains **why the agent sometimes does not reply** and **why it sometimes crashes** (handoff or failure).

---

## 1. Why the agent sometimes does NOT reply to the customer

| Cause | Where | What the customer sees |
|-------|--------|-------------------------|
| **HITL: AI disabled for this session** | `process_messages.py` (HITL gatekeeper) | No automated reply. Merchant gets `handover_new_message` socket; they must reply manually. |
| **Channel autopilot off** | `process_messages.py`: `if not getattr(channel, "ai_auto_reply", False): continue` | No reply. Only manual or trigger-based flows run. |
| **Empty AI reply (no fallback sent)** | `run_ai_agent_node`: when `reply_text` is empty after LLM/tools (e.g. API glitch, timeout) | No message sent. Log: `"AI agent returned empty reply (channel=..., sender=...); no fallback message sent."` |
| **Voice/fallback path: empty reply** | `process_messages.py` (voice reply path): `if not reply_text: return` | No reply. Log: `"AI voice/fallback returned empty reply ...; no fallback message sent."` |
| **Voice path: generate_reply_with_tools exception** | `process_messages.py`: `generate_reply_with_tools` in try/except; on exception we `return` | No reply. Log: `"generate_reply_with_tools failed: ..."` |
| **Voice path: plan / imports** | `process_messages.py`: `verify_plan_access` (PermissionDenied) or AI voice imports fail | No reply. Log: `"AI auto-reply skipped: plan does not allow auto_reply"` or `"AI voice reply imports failed"`. |
| **continue_after_tool_calls failed** | `process_messages.py`: after tool execution, `continue_after_tool_calls` can throw; we only log and keep going with possibly stale `result` | Reply may be missing or wrong. Log: `"continue_after_tool_calls failed: ..."` or `"continue_after_tool_calls (voice) failed: ..."`. |
| **submit_customer_order failed (non-success)** | Tool returns `success: false`; AI is expected to relay the error to the customer. If the AI doesn’t generate a follow-up message (e.g. empty reply), customer gets no reply. | Depends on LLM. Log: `"submit_customer_order failed (channel=..., sender=...): ..."`. |
| **Product/seller not linked** | `_execute_submit_customer_order` returns error JSON; AI gets tool result. If next turn is empty or fails, customer may see nothing. | Depends on LLM. Log: `"_execute_submit_customer_order: no product_id in node ai_model_config"` or `"channel has no owner"`. |

---

## 2. Why the agent sometimes “crashes” (handoff or error message)

| What happens | Where | Log / user-visible |
|--------------|--------|---------------------|
| **Uncaught exception in run_ai_agent_node** | `process_messages.py`: `except Exception as e` in `run_ai_agent_node` | **Customer sees:** `"عندي مشكل تقني بسيط، فريقنا غادي يتواصل معاك قريباً."` (handoff). **Log:** `logger.exception("run_ai_agent_node failed: %s", e)`. Session: `ai_enabled=False`, `handover_reason="Backend error (tool or LLM)"`, `HandoverLog` created. |
| **Handoff on AI error (session update fails)** | Same except block: updating session/handover can throw. | **Customer:** already got the handoff message above. **Log:** `"Handoff on AI error failed: ..."`. |
| **submit_customer_order tool: DB/validation failure** | `orders_ai.py`: `handle_submit_order_tool` returns `success: False` with SYSTEM ERROR message; `_execute_submit_customer_order` returns error JSON. | **Customer:** sees whatever the AI says (we instruct it to apologize and not retry). **Log:** `"FATAL TOOL ERROR -> ..."` / `"FATAL TOOL ERROR (stack) -> ..."` only on unexpected exception in the tool; otherwise `"submit_customer_order failed ..."` in process_messages. |
| **submit_customer_order: channel/product/seller missing** | `process_messages.py`: `_execute_submit_customer_order` | Returns error JSON to AI. **Log:** `"Channel or product context missing"` / `"no product_id in node ai_model_config"` / `"channel has no owner"`. |
| **submit_customer_order: exception in backend** | `_execute_submit_customer_order`: `except Exception` | **Log:** `logger.exception("_execute_submit_customer_order: %s", e)`. AI gets SYSTEM ERROR instructing to apologize and not retry. |
| **save_order_from_ai exception** | `orders_ai.py`: `save_order_from_ai` | **Log:** `logger.exception("save_order_from_ai failed: %s", e)`. Returns `None`; no order created; AI may still reply with text. |
| **OpenAI API errors (timeout, rate limit, status code)** | `ai_assistant/services.py`: `generate_reply_with_tools` / `continue_after_tool_calls` | Exceptions propagate to `run_ai_agent_node` → caught → handoff message + `ai_enabled=False`. **Log:** in services: `"OpenAI API request timed out"`, `"OpenAI API error ..."`, etc. |

---

## 3. All AI-agent-related log messages (by file)

### discount/whatssapAPI/process_messages.py

| Log / message | Level | Meaning |
|---------------|--------|--------|
| `_execute_submit_customer_order: no product_id in node ai_model_config (...). Link a product to this AI Agent node in the Flow Builder.` | warning | Product not linked to AI node → tool returns error JSON. |
| `_execute_submit_customer_order: channel has no owner (channel_id=...)` | warning | Channel has no owner → tool returns error JSON. |
| `logger.exception("_execute_submit_customer_order: %s", e)` | exception | Unexpected error in submit_customer_order execution. |
| `submit_customer_order failed (channel=..., sender=...): ...` | info | Tool returned success=false; AI should explain to customer. |
| `continue_after_tool_calls failed: ...` | warning | Second LLM call after tools failed; reply may be missing/wrong. |
| `continue_after_tool_calls (voice) failed: ...` | warning | Same, in voice/fallback path. |
| `Order not saved (tool_calls save_order/record_order rejected): ... should_accept_order_data returned False` | warning | Order rejected by guardrails (trust_score/stage). |
| `Order not saved (ORDER_DATA rejected): ...` | warning | Order data from [ORDER_DATA] tag rejected. |
| `Incomplete Capture: AI replied with order confirmation but no valid [ORDER_DATA] (...)` | warning | AI said “order registered” but no valid order data; we force retry message. |
| `AI agent returned empty reply (channel=..., sender=...); no fallback message sent.` | warning | LLM/tools returned no text; we don’t send a generic fallback. |
| `SEND_MEDIA %s failed: ...` | warning | Sending a media asset from AI failed. |
| `SEND_PRODUCT_IMAGE failed: ...` | warning | Sending product image failed. |
| `logger.exception("run_ai_agent_node failed: %s", e)` | exception | Top-level crash in AI agent; we send handoff message and disable AI. |
| `Handoff on AI error failed: ...` | warning | Could not update session/handover after run_ai_agent_node exception. |
| `AI takeover note failed: ...` | warning | Could not add internal “AI took over” note. |
| `HITL handover update: ...` | warning | Could not set ai_enabled=False / HandoverLog when AI requested handover. |
| `AI action note failed: ...` | warning | Adding an AI action note failed. |
| `check_stock failed: ...` | warning | check_stock tool failed. |
| `track_order failed: ...` | warning | track_order tool failed. |
| `AI voice reply imports failed: ...` | warning | Import error in voice reply path; no reply sent. |
| `generate_reply_with_tools failed: ...` | exception | Voice path: LLM call failed; we return without replying. |
| `process_and_send_voice failed, falling back to text: ...` | warning | Voice TTS failed; we send text instead. |
| `AI voice/fallback returned empty reply (...); no fallback message sent.` | warning | Voice path empty reply; we return without sending. |
| `cancel_pending_follow_up_tasks_for_customer: ...` | warning | Cancel follow-ups failed (non-fatal). |
| `HITL/sales-intent reset: ...` | warning | Error in HITL/sales-intent check; we continue (skip AI reply for that message). |

### discount/orders_ai.py

| Log / message | Level | Meaning |
|---------------|--------|--------|
| `get_or_create_ai_agent_user failed: ...; falling back to owner` | warning | Bot user creation failed; we use store owner for order agent. |
| `TOOL CALLED: Raw arguments received -> ...` | info | submit_customer_order tool invoked (debug). |
| `VALIDATION PASSED: Payload (stripped to allowed keys) -> ...` | info | Payload valid for DB (debug). |
| `handle_submit_order_tool: product_id=... not found for seller ...` | warning | Product missing → return SYSTEM ERROR. |
| `DB INSERT ATTEMPT...` | info | About to create order. |
| `DB SUCCESS: Order ID -> ...` | info | Order created. |
| `handle_submit_order_tool: set contact to closed failed: ...` | warning | Updating contact pipeline_stage failed (non-fatal). |
| `FATAL TOOL ERROR -> ...` | error | Unexpected exception in handle_submit_order_tool. |
| `FATAL TOOL ERROR (stack) -> ...` | error | Full traceback for above. |
| `save_order_from_ai: channel and customer_phone required` | warning | save_order_from_ai called without channel/phone → return None. |
| `save_order_from_ai: rejected — no product (sku or product_name). ...` | warning | No product identifier → return None. |
| `save_order_from_ai product lookup for sku=...: ...` | warning | Product lookup by SKU failed. |
| `save_order_from_ai: rejected — sku=... does not match any product in the store.` | warning | SKU not found → return None. |
| `save_order_from_ai product lookup by name=...: ...` | warning | Product lookup by name failed. |
| `save_order_from_ai: rejected — product_name=... does not match any product in the store.` | warning | Product name not found → return None. |
| `save_order_from_ai: rejected — price must be positive (...). Ask AI to re-extract ...` | warning | Price 0/missing and no product price → return dict with SYSTEM ERROR for AI. |
| `save_order_from_ai: max_monthly_orders (...) reached for channel ...` | info | Plan limit reached; order not created. |
| `save_order_from_ai created order_id=... for ...` | info | Order created. |
| `logger.exception("save_order_from_ai failed: %s", e)` | exception | DB or other error in save_order_from_ai → return None. |
| `logger.exception("_notify_owner_order_created failed: %s", e)` | exception | Order notification (email/WhatsApp) failed. |

### ai_assistant/services.py

| Log / message | Level | Meaning |
|---------------|--------|--------|
| `OpenAI API error ...: ...` | error | Non-2xx from OpenAI; raises RuntimeError. |
| `OpenAI coaching API error ...` | error | Coaching API error. |
| `parse tool ... arguments: ...` | warning | Tool arguments JSON parse failed. |
| (Raises: `ValueError("OPENAI_API_KEY is not set.")`) | - | No API key. |
| (Raises: `RuntimeError` for timeout, connection, rate limit, status code) | - | OpenAI call failed; propagates to run_ai_agent_node → handoff. |

---

## 4. SYSTEM ERROR messages returned to the AI (tool result text)

These strings are returned to the LLM so it can explain to the customer (or apologize and not retry):

- **Channel or product context missing.** (from `_execute_submit_customer_order`)
- **No product is selected in this conversation. The merchant must link a product to this AI Agent node in the Flow Builder.**
- **Channel not configured.** (channel has no owner)
- **Order could not be processed. Please try again.** / **Tool execution failed in the backend. Log: ...**
- **Invalid arguments. Politely ask the customer again for the required information.**
- **Channel not available. Please try again.**
- **No product is selected... Ask the customer to choose a product first...**
- **Product no longer available. Ask the customer to choose another product.**
- **Customer name is missing. ...**
- **Delivery city or address is missing. ...**
- **The phone number is missing. ...** / **The phone number is too short. ...** / **The phone number is not a valid Moroccan mobile. ...**
- **Store mismatch. Please try again.**
- **A contact number is required to register the order. ...**
- **SYSTEM INSTRUCTION: A duplicate order was detected...**
- **Failed to save to DB. Reason: ... Apologize to the customer... Do not retry the tool.**
- **The product price could not be determined (price is 0 or missing). Review the conversation history...** (save_order_from_ai)

---

## 5. Quick reference: no reply vs crash

- **No reply:** HITL (ai_enabled=False), autopilot off, empty AI reply (no fallback), voice path early return (import/plan/generate_reply failure), or continue_after_tool_calls failure leaving no reply.
- **Crash (user-visible):** Uncaught exception in `run_ai_agent_node` → customer sees handoff message and AI is disabled; or tool returns SYSTEM ERROR and AI replies with an apology (no “crash” in code, but error flow).

To see these errors at runtime, search logs for the phrases in the tables above or run:  
`python manage.py print_ai_agent_errors`
