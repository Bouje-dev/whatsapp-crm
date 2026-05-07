"""
Weighted Chat Routing with Strict Sticky Sessions.

- Strict Sticky: Existing customers (contact.assigned_agent_id set) always stay
  with that agent. No re-distribution.
- Weighted Distribution: New customers (no assigned_agent_id) are assigned to
  one of the channel's agents based on routing_percentage (weighted random).
- Agents with is_accepting_chats=False are excluded from new assignments only;
  existing assignments are kept (UI can show "Assigned Agent Offline").
"""

import random
from django.db import transaction

from discount.models import Contact, WhatsAppChannel, ChannelAgentRouting, CustomUser


# -----------------------------------------------------------------------------
# Strict Sticky Routing: existing customers
# -----------------------------------------------------------------------------

def get_assigned_agent_for_contact(contact):
    """
    Returns the assigned agent ID for this contact if any (sticky routing).
    Does NOT run distribution; use this to decide whether to route or assign new.
    """
    if not contact:
        return None
    return getattr(contact, "assigned_agent_id", None)


def is_agent_accepting_chats(channel, agent_id):
    """
    Check if the assigned agent is currently accepting chats (is_accepting_chats).
    Used to flag "Assigned Agent Offline" in UI; we keep the sticky assignment.
    """
    if not channel or not agent_id:
        return True
    config = ChannelAgentRouting.objects.filter(
        channel=channel,
        agent_id=agent_id,
    ).first()
    if config is None:
        # No routing config => treat as accepting (backward compat)
        return True
    return config.is_accepting_chats


def contact_assigned_agent_is_offline(contact):
    """
    For UI: True if contact has an assigned agent who is not accepting chats.
    Sticky assignment is kept; UI can show "Assigned Agent Offline" or offer fallback.
    """
    if not contact or not contact.assigned_agent_id:
        return False
    return not is_agent_accepting_chats(contact.channel, contact.assigned_agent_id)


# -----------------------------------------------------------------------------
# Weighted Distribution: new customers only
# -----------------------------------------------------------------------------

def get_agents_accepting_chats_with_routing(channel, use_dynamic_redistribution=None):
    """
    Fetch team members (and optionally AI) for weighted routing.

    - Always: in ChannelAgentRouting with routing_percentage > 0, is_accepting_chats == True.
    - If use_dynamic_redistribution (channel.dynamic_offline_redistribution): also require
      agent.is_online == True; then redistribute weights so only online agents (+ AI) are
      considered. AI is included as (None, ai_routing_percentage) when Full Autopilot is ON.
    - Returns list of (agent_id, weight). agent_id None means AI. Weights may sum to 100
      or to 1.0 when dynamically normalized; weighted_random_choice accepts any positive sum.
    """
    if not channel:
        return []
    dynamic = use_dynamic_redistribution if use_dynamic_redistribution is not None else getattr(channel, "dynamic_offline_redistribution", False)

    configs = ChannelAgentRouting.objects.filter(
        channel=channel,
        is_accepting_chats=True,
        routing_percentage__gt=0,
    ).select_related("agent")
    assigned_ids = set(channel.assigned_agents.values_list("id", flat=True))
    weighted = []
    for c in configs:
        if c.agent_id not in assigned_ids:
            continue
        if dynamic and getattr(c.agent, "is_online", True) is False:
            continue
        weighted.append((c.agent_id, c.routing_percentage))

    # Full Autopilot: add AI to pool (AI is "always online" for dynamic redistribution)
    ai_pct = getattr(channel, "ai_routing_percentage", 0) or 0
    if getattr(channel, "ai_auto_reply", False) and ai_pct > 0:
        weighted.append((None, ai_pct))

    if not weighted:
        return []

    if dynamic:
        total_online_weight = sum(p for _, p in weighted)
        if total_online_weight <= 0:
            return []
        # Normalize so weights sum to 1.0 (weighted_random_choice works with any sum)
        weighted = [(aid, p / total_online_weight) for aid, p in weighted]

    return weighted


def weighted_random_choice(weighted_list):
    """
    Weighted random selection.
    weighted_list: list of (agent_id, percentage) e.g. [(1, 80), (2, 20)].
    Sum of percentages should be 100 (caller validates).
    Returns selected agent_id or None if list empty/sum 0.
    """
    if not weighted_list:
        return None
    total = sum(p for _, p in weighted_list)
    if total <= 0:
        return None
    r = random.uniform(0, total)
    cum = 0
    for agent_id, pct in weighted_list:
        cum += pct
        if r < cum:
            return agent_id
    return weighted_list[-1][0]


def assign_contact_to_agent(contact, agent_id):
    """Set contact.assigned_agent_id to agent_id and save."""
    if contact is None:
        return
    contact.assigned_agent_id = agent_id
    contact.save(update_fields=["assigned_agent_id"])


def run_weighted_routing_for_new_contact(contact, channel):
    """
    For a NEW contact (no assigned_agent_id): run weighted distribution and assign.
    - Uses dynamic_offline_redistribution when enabled (only online agents + AI, normalized).
    - When Full Autopilot is ON, AI is in the pool; agent_id None means assign to AI.
    - If no one available, falls back to channel.owner or AI (when Full Autopilot ON).
    - Saves contact.assigned_agent_id immediately (None = AI).
    """
    if not contact or not channel:
        return
    if get_assigned_agent_for_contact(contact):
        return
    dynamic = getattr(channel, "dynamic_offline_redistribution", False)
    weighted = get_agents_accepting_chats_with_routing(channel, use_dynamic_redistribution=dynamic)
    agent_id = weighted_random_choice(weighted)
    if agent_id is None and not weighted:
        # No one in pool: fallback to owner or AI
        if getattr(channel, "ai_auto_reply", False):
            agent_id = None  # AI
        elif channel.owner_id:
            agent_id = channel.owner_id
    with transaction.atomic():
        assign_contact_to_agent(contact, agent_id)
