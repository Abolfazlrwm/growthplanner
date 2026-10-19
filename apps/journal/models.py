"""DayNote model: one note + mood per user per day."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Mood(models.IntegerChoices):
    VERY_BAD = 1, "خیلی بد"
    BAD = 2, "بد"
    NEUTRAL = 3, "معمولی"
    GOOD = 4, "خوب"
    GREAT = 5, "عالی"


class DayNote(models.Model):
    """Daily journal entry. Text and mood are both optional."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="day_notes",
        verbose_name="کاربر",
    )
    date = models.DateField("تاریخ", default=timezone.localdate)
    text = models.TextField("یادداشت", blank=True)
    mood = models.PositiveSmallIntegerField(
        "حال‌وهوا", choices=Mood, null=True, blank=True
    )

    class Meta:
        verbose_name = "یادداشت روزانه"
        verbose_name_plural = "یادداشت‌های روزانه"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"], name="unique_daynote_per_user_date"
            ),
            models.CheckConstraint(
                condition=Q(mood__isnull=True) | Q(mood__range=(1, 5)),
                name="daynote_mood_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.date}"
