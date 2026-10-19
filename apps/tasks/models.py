"""Task model: one unit of work on a specific day."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone
from datetime import timedelta


class TaskStatus(models.TextChoices):
    TODO = "todo", "انجام نشده"
    IN_PROGRESS = "in_progress", "در جریان"
    DONE = "done", "انجام شد"
    FAILED = "failed", "نشد"
    MOVED = "moved", "منتقل شد"


class TaskPriority(models.TextChoices):
    LOW = "low", "کم"
    MEDIUM = "medium", "متوسط"
    HIGH = "high", "زیاد"


# Statuses that still need attention (shown in the nightly review).
OPEN_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.MOVED)


class TaskQuerySet(models.QuerySet):
    def priority_ordered(self):
        """Order by priority (high first), then time of day — for a single day's list."""
        priority_rank = Case(
            When(priority=TaskPriority.HIGH, then=Value(0)),
            When(priority=TaskPriority.MEDIUM, then=Value(1)),
            When(priority=TaskPriority.LOW, then=Value(2)),
            output_field=IntegerField(),
        )
        return self.annotate(_priority_rank=priority_rank).order_by(
            "_priority_rank", "start_time", "id"
        )


class Task(models.Model):
    """A task on a given (Gregorian) date, optionally linked to a goal and a time slot."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="کاربر",
    )
    goal = models.ForeignKey(
        "goals.Goal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="هدف",
    )
    habit = models.ForeignKey(
        "habits.Habit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="عادت",
        help_text="اگر این تسک از یک عادت تکرارشونده ساخته شده، اینجا مشخص می‌شود.",
    )
    title = models.CharField("عنوان", max_length=200)
    date = models.DateField("تاریخ", default=timezone.localdate)
    start_time = models.TimeField("ساعت شروع", null=True, blank=True)
    end_time = models.TimeField("ساعت پایان", null=True, blank=True)
    status = models.CharField(
        "وضعیت", max_length=20, choices=TaskStatus, default=TaskStatus.TODO
    )
    priority = models.CharField(
        "اولویت", max_length=10, choices=TaskPriority, default=TaskPriority.MEDIUM
    )
    fail_reason = models.CharField("چرا نشد؟", max_length=255, blank=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    tags = models.ManyToManyField(
        "Tag", blank=True, related_name="tasks", verbose_name="برچسب‌ها"
    )

    objects = TaskQuerySet.as_manager()

    class Meta:
        verbose_name = "تسک"
        verbose_name_plural = "تسک‌ها"
        ordering = ["date", "start_time", "id"]
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [
            # An end time requires a start time, and must be after it.
            models.CheckConstraint(
                condition=Q(end_time__isnull=True)
                | Q(start_time__isnull=False, end_time__gt=F("start_time")),
                name="task_end_after_start",
                violation_error_message="ساعت پایان باید بعد از ساعت شروع باشد (و بدون ساعت شروع نمی‌شود ساعت پایان داشت).",
            ),
            # Avoid double-generating the same habit's task for the same day under a race.
            models.UniqueConstraint(
                fields=["date", "habit"],
                name="unique_habit_task_per_day",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self) -> bool:
        """True if the task is not finished (todo / in progress / moved)."""
        return self.status in OPEN_STATUSES

    def clean(self):
        super().clean()
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            raise ValidationError({"goal": "این هدف متعلق به کاربر دیگری است."})
        if self.habit_id and self.user_id and self.habit.user_id != self.user_id:
            raise ValidationError({"habit": "این عادت متعلق به کاربر دیگری است."})

    def move_to_tomorrow(self):
        """Push the task one day forward and mark it as moved.

        If this task came from a recurring habit, detach it from the habit first: the
        habit still owns tomorrow's (and every future) occurrence on its own schedule,
        so without detaching here, re-visiting today's page would regenerate a duplicate
        for today via the habit sync while this moved copy sits on tomorrow.
        """
        if not self.is_open:
            raise ValueError("Only open tasks can be moved.")
        self.date += timedelta(days=1)
        self.status = TaskStatus.MOVED
        update_fields = ["date", "status"]
        if self.habit_id:
            self.habit = None
            update_fields.append("habit")
        self.save(update_fields=update_fields)


class Tag(models.Model):
    """A private, owner-scoped label that can be attached to more than one task."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_tags",
        verbose_name="کاربر",
    )
    name = models.CharField("نام", max_length=40)
    normalized_name = models.CharField("نام نرمال", max_length=40)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "برچسب تسک"
        verbose_name_plural = "برچسب‌های تسک"
        ordering = ["normalized_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_name"], name="tasks_unique_user_tag_name"
            )
        ]

    @staticmethod
    def normalize(value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def clean(self):
        super().clean()
        self.name = " ".join((self.name or "").strip().split())
        self.normalized_name = self.normalize(self.name)
        if not self.normalized_name:
            raise ValidationError({"name": "نام برچسب نمی‌تواند خالی باشد."})

    def save(self, *args, **kwargs):
        # Keep programmatic ``get_or_create`` and admin writes aligned with the unique key.
        self.name = " ".join((self.name or "").strip().split())
        self.normalized_name = self.normalize(self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SubTask(models.Model):
    """A small checkable step belonging to one task and the same account owner."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="کاربر",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="تسک",
    )
    title = models.CharField("عنوان", max_length=200)
    is_completed = models.BooleanField("انجام شده", default=False)
    position = models.PositiveSmallIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "ریزکار"
        verbose_name_plural = "ریزکارها"
        ordering = ["is_completed", "position", "id"]
        indexes = [models.Index(fields=["user", "task"], name="tasks_subtask_user_task_idx")]

    def clean(self):
        super().clean()
        if self.user_id and self.task_id and self.task.user_id != self.user_id:
            raise ValidationError({"task": "این تسک متعلق به کاربر دیگری است."})

    def __str__(self):
        return self.title


class FocusSession(models.Model):
    """One finished focus (pomodoro) block, logged by the timer when it completes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="focus_sessions",
        verbose_name="کاربر",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="focus_sessions",
        verbose_name="تسک",
    )
    date = models.DateField("تاریخ", default=timezone.localdate)
    minutes = models.PositiveSmallIntegerField("دقیقه")
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "جلسه تمرکز"
        verbose_name_plural = "جلسات تمرکز"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "date"], name="tasks_focus_user_date_idx")]

    def __str__(self):
        return f"{self.minutes} min on {self.date}"

    def clean(self):
        super().clean()
        if self.task_id and self.user_id and self.task.user_id != self.user_id:
            raise ValidationError({"task": "این تسک متعلق به کاربر دیگری است."})
