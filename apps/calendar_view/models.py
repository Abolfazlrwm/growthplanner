"""Models for private calendar subscriptions."""
import datetime as dt
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


SUBSCRIPTION_VALIDITY_DAYS = 365


def generate_subscription_token():
    """Return a URL-safe bearer secret with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def default_subscription_expiry():
    return timezone.now() + dt.timedelta(days=SUBSCRIPTION_VALIDITY_DAYS)


class CalendarSubscription(models.Model):
    """One revocable, private iCalendar bearer link per user.

    The token is deliberately stored as a random opaque secret rather than derived from
    user data. It is displayed only to its authenticated owner on the management page;
    keeping it permits that page to show the current subscription URL after a refresh.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_subscription",
        verbose_name="کاربر",
    )
    token = models.CharField(
        "توکن اشتراک",
        max_length=128,
        unique=True,
        default=generate_subscription_token,
    )
    expires_at = models.DateTimeField("تاریخ انقضا", default=default_subscription_expiry)
    revoked_at = models.DateTimeField("زمان ابطال", null=True, blank=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)

    class Meta:
        verbose_name = "اشتراک تقویم"
        verbose_name_plural = "اشتراک‌های تقویم"

    def __str__(self):
        # Never include a bearer token in an admin label, exception, or log message.
        return f"Calendar subscription for user {self.user_id}"

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()

    def rotate(self):
        """Create a fresh link and invalidate the previous bearer secret."""
        token = generate_subscription_token()
        # A collision is cryptographically negligible, but retaining the unique check
        # makes the model correct even if a token generator is patched in a test.
        while type(self).objects.filter(token=token).exclude(pk=self.pk).exists():
            token = generate_subscription_token()
        self.token = token
        self.expires_at = default_subscription_expiry()
        self.revoked_at = None
        self.save(update_fields=["token", "expires_at", "revoked_at", "updated_at"])

    def revoke(self):
        """Invalidate the current link without deleting the audit-friendly row."""
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at", "updated_at"])
