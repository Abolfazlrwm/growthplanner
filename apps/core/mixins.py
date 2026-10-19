"""Shared view mixins used across apps."""
from django.contrib.auth.mixins import LoginRequiredMixin


class UserOwnedMixin(LoginRequiredMixin):
    """Restrict the queryset to objects owned by the current user."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
