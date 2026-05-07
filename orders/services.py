"""
Order business logic: bulk assign, etc.
"""
from django.contrib.auth import get_user_model

User = get_user_model()


def bulk_assign_orders(order_ids, agent_id, request_user):
    """
    Assign selected orders to an agent. Respects role-based access:
    only orders the user can see will be updated.
    """
    from .models import Order

    qs = Order.objects.for_user(request_user).filter(pk__in=order_ids)
    agent = None
    if agent_id:
        agent = User.objects.filter(pk=agent_id).first()
    updated = qs.update(assigned_agent=agent)
    return updated
