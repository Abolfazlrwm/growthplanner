"""Goal model."""
from django.conf import settings
from django.db import models
from django.db.models import Count, Q

from apps.tasks.models import TaskStatus


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    COMPLETED = "completed", "تکمیل‌شده"
    ABANDONED = "abandoned", "رها‌شده"


class Goal(models.Model):
    """A goal with a deadline; its progress is derived from its tasks."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
        verbose_name="کاربر",
    )
    title = models.CharField("عنوان", max_length=200)
    description = models.TextField("توضیحات", blank=True)
    deadline = models.DateField("ددلاین")
    status = models.CharField(
        "وضعیت", max_length=20, choices=GoalStatus, default=GoalStatus.ACTIVE
    )
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "هدف"
        verbose_name_plural = "اهداف"
        ordering = ["deadline", "id"]

    def __str__(self):
        return self.title

    @property
    def progress_percent(self) -> int:
        """Done tasks / all tasks, as a rounded percentage (0 if no tasks)."""
        stats = self.tasks.aggregate(
            total=Count("id"),
            done=Count("id", filter=Q(status=TaskStatus.DONE)),
        )
        if not stats["total"]:
            return 0
        return round(stats["done"] * 100 / stats["total"])


class Milestone(models.Model):
    """A private checkpoint owned by the same user as its parent goal."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="milestones",
        verbose_name="کاربر",
    )
    goal = models.ForeignKey(
        Goal,
        on_delete=models.CASCADE,
        related_name="milestones",
        verbose_name="هدف",
    )
    title = models.CharField("عنوان", max_length=200)
    due_date = models.DateField("تاریخ هدف", null=True, blank=True)
    is_completed = models.BooleanField("تکمیل شده", default=False)
    completed_at = models.DateTimeField("زمان تکمیل", null=True, blank=True)
    position = models.PositiveSmallIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "نقطه عطف"
        verbose_name_plural = "نقاط عطف"
        ordering = ["is_completed", "due_date", "position", "id"]
        indexes = [models.Index(fields=["user", "goal"], name="goals_milestone_user_goal_idx")]

    def clean(self):
        super().clean()
        if self.user_id and self.goal_id and self.goal.user_id != self.user_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({"goal": "این هدف متعلق به کاربر دیگری است."})

    def __str__(self):
        return self.title
