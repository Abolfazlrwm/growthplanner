"""Habit model: a recurring task template that generates real Task rows day by day."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Habit(models.Model):
    """A recurring task template (e.g. 'ورزش صبحگاهی', هر روز یا روزهای خاصی از هفته)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="habits",
        verbose_name="کاربر",
    )
    goal = models.ForeignKey(
        "goals.Goal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="habits",
        verbose_name="هدف",
    )
    title = models.CharField("عنوان", max_length=200)
    # Comma-separated jalali weekdays (Saturday=0 ... Friday=6); empty means every day.
    weekdays = models.CharField("روزهای هفته", max_length=20, blank=True)
    start_time = models.TimeField("ساعت شروع", null=True, blank=True)
    end_time = models.TimeField("ساعت پایان", null=True, blank=True)
    active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    priority = models.CharField("اولویت", max_length=10, choices=[("low", "کم"), ("medium", "متوسط"), ("high", "زیاد")], default="medium")
    tags = models.ManyToManyField("tasks.Tag", blank=True, related_name="habits", verbose_name="برچسب‌ها")
    starts_on = models.DateField("شروع تکرار", null=True, blank=True)

    class Meta:
        verbose_name = "عادت"
        verbose_name_plural = "عادت‌ها"
        ordering = ["-active", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            raise ValidationError({"goal": "این هدف متعلق به کاربر دیگری است."})
        if self.end_time and (not self.start_time or self.end_time <= self.start_time):
            raise ValidationError({"end_time": "ساعت پایان باید بعد از ساعت شروع باشد."})
        try:
            days = self.weekday_list
        except (ValueError, TypeError):
            raise ValidationError({"weekdays": "روزهای تکرار معتبر نیستند."})
        if any(day < 0 or day > 6 for day in days):
            raise ValidationError({"weekdays": "روزهای هفته باید بین صفر و شش باشند."})

    @property
    def weekday_list(self) -> list[int]:
        """Parsed weekday numbers, or [] meaning 'every day'."""
        if not self.weekdays:
            return []
        return [int(x) for x in self.weekdays.split(",") if x.strip() != ""]

    def occurs_on(self, jalali_weekday: int) -> bool:
        """True if this habit is scheduled on a day with this jalali weekday (0=Saturday)."""
        wl = self.weekday_list
        return not wl or jalali_weekday in wl

    def weekday_labels(self) -> list[str]:
        from utils.jalali import JALALI_WEEKDAYS
        return [JALALI_WEEKDAYS[i] for i in self.weekday_list]
