"""
Role-based access: admins/owners see all orders, agents see only assigned.
"""
from django.db import models


class OrderQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return self
        # Team admin or store owner: see all orders of their stores
        if getattr(user, "is_team_admin", False) or (hasattr(user, "owned_stores") and user.owned_stores.exists()):
            return self.filter(store__owner=user)
        # Agent: only orders assigned to them
        return self.filter(assigned_agent=user)


class OrderManager(models.Manager):
    def get_queryset(self):
        return OrderQuerySet(self.model, using=self._db)

    def for_user(self, user):
        return self.get_queryset().for_user(user)
