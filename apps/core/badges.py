"""Achievements, computed on the fly from real data (no extra table to keep in sync)."""
from apps.goals.models import Goal, GoalStatus
from apps.habits.models import Habit
from apps.journal.models import DayNote
from apps.tasks.models import Task, TaskStatus

# key, title, description, icon (sprite id), which counter it tracks, target
BADGES = (
    ("first-step", "اولین قدم", "اولین تسکت را انجام بده", "i-check-circle", "done", 1),
    ("ten-done", "ده‌تایی", "۱۰ تسک انجام‌شده", "i-tasks", "done", 10),
    ("hundred-done", "صدتایی", "۱۰۰ تسک انجام‌شده", "i-trophy", "done", 100),
    ("week-streak", "یک هفته پشت‌سرهم", "۷ روز متوالی با حداقل یک تسک انجام‌شده", "i-flame", "streak", 7),
    ("month-streak", "یک ماه پشت‌سرهم", "۳۰ روز متوالی با حداقل یک تسک انجام‌شده", "i-flame", "streak", 30),
    ("goal-setter", "هدف‌گذار", "اولین هدفت را بساز", "i-goals", "goals", 1),
    ("goal-reached", "رسیدن به هدف", "اولین هدفت را تکمیل کن", "i-flag", "goals_done", 1),
    ("habit-builder", "عادت‌ساز", "اولین عادتت را تعریف کن", "i-habits", "habits", 1),
    ("writer", "نویسنده", "برای ۷ روز یادداشت بنویس", "i-book", "notes", 7),
)


def compute_badges(user, streak):
    """Return one dict per badge: title, description, icon, current, target, percent, earned."""
    counters = {
        "done": Task.objects.filter(user=user, status=TaskStatus.DONE).count(),
        "streak": streak,
        "goals": Goal.objects.filter(user=user).count(),
        "goals_done": Goal.objects.filter(user=user, status=GoalStatus.COMPLETED).count(),
        "habits": Habit.objects.filter(user=user).count(),
        "notes": DayNote.objects.filter(user=user).exclude(text="").count(),
    }
    badges = []
    for key, title, description, icon, counter, target in BADGES:
        current = counters[counter]
        badges.append({
            "key": key,
            "title": title,
            "description": description,
            "icon": icon,
            "current": min(current, target),
            "target": target,
            "percent": min(100, round(current * 100 / target)),
            "earned": current >= target,
        })
    return badges
