"""Private, user-scoped persistence for the planning assistant."""
import uuid

from django.conf import settings
from django.db import models


class AssistantConversation(models.Model):
    """A user-owned chat thread.  The UUID is safe to send to the browser."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["user", "-updated_at"])]


class AssistantMessage(models.Model):
    """A bounded transcript entry; only its conversation owner may access it."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        AssistantConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=12, choices=Role)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]


class AssistantDraft(models.Model):
    """One validated, explicitly confirmable task suggestion from an assistant answer."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_drafts",
    )
    conversation = models.ForeignKey(
        AssistantConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
    )
    payload = models.JSONField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"])]


class AssistantUsageWindow(models.Model):
    """A database-backed request counter, robust across worker processes/restarts."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_usage_windows",
    )
    window_started = models.DateTimeField()
    count = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "window_started"],
                name="assistant_usage_user_window_unique",
            )
        ]
        indexes = [models.Index(fields=["user", "window_started"])]
