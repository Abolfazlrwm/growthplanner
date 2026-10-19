"""Turn active Habit templates into real Task rows for a given day (called lazily from views)."""
import datetime as dt
from django.utils import timezone

from apps.tasks.models import Task, TaskStatus
from utils.jalali import to_jalali

from .models import Habit


def sync_habits_for_date(user, date):
    """Ensure every active habit scheduled on `date` has a matching Task; return the created ones."""
    if abs((date - timezone.localdate()).days) > 366:
        return []
    weekday = to_jalali(date).weekday()
    created = []
    for habit in Habit.objects.filter(user=user, active=True).select_related("goal").prefetch_related("tags"):
        if habit.starts_on and date < habit.starts_on:
            continue
        if not habit.occurs_on(weekday):
            continue
        task, was_created = Task.objects.get_or_create(
            user=user,
            date=date,
            habit=habit,
            defaults={
                "title": habit.title,
                "goal": habit.goal,
                "start_time": habit.start_time,
                "end_time": habit.end_time,
                "priority": habit.priority,
            },
        )
        if was_created:
            task.tags.set(habit.tags.all())
            created.append(task)
    return created


def sync_habits_for_range(user, start_date, end_date):
    """Like sync_habits_for_date, but for every day in [start_date, end_date] in one pass.

    Used by the monthly calendar so a habit's dot shows up on every scheduled day in the
    visible month, not only on days the user has individually opened.
    """
    today = timezone.localdate()
    start_date = max(start_date, today - dt.timedelta(days=366))
    end_date = min(end_date, today + dt.timedelta(days=366))
    if end_date < start_date or (end_date - start_date).days > 62:
        return []
    habits = list(Habit.objects.filter(user=user, active=True).select_related("goal").prefetch_related("tags"))
    if not habits:
        return []

    existing = set(
        Task.objects.filter(
            user=user, habit__in=habits, date__range=(start_date, end_date),
        ).values_list("date", "habit_id")
    )

    to_create = []
    day = start_date
    while day <= end_date:
        weekday = to_jalali(day).weekday()
        for habit in habits:
            if (not habit.starts_on or day >= habit.starts_on) and habit.occurs_on(weekday) and (day, habit.id) not in existing:
                to_create.append(Task(
                    user=user, date=day, habit=habit, title=habit.title,
                    goal=habit.goal, start_time=habit.start_time, end_time=habit.end_time,
                    priority=habit.priority,
                ))
        day += dt.timedelta(days=1)

    if to_create:
        Task.objects.bulk_create(to_create, ignore_conflicts=True)
        planned = {(t.date, t.habit_id) for t in to_create}
        tags_by_habit = {h.id: list(h.tags.all()) for h in habits}
        relations = []
        for task in Task.objects.filter(user=user, habit__in=habits, date__range=(start_date, end_date)):
            if (task.date, task.habit_id) in planned:
                relations.extend(Task.tags.through(task_id=task.id, tag_id=tag.id) for tag in tags_by_habit[task.habit_id])
        Task.tags.through.objects.bulk_create(relations, ignore_conflicts=True)
    return to_create


STREAK_MAX_LOOKBACK_DAYS = 3650  # ~10 years; a safety cap, not an expected real streak length


def habit_streak(habit, today):
    """Consecutive days (ending today or yesterday) this habit's task was completed.

    Same "grace" rule as the overall streak on the stats page: today not being done yet
    doesn't zero the streak, it just means we start counting from yesterday.
    """
    done_dates = set(
        Task.objects.filter(
            habit=habit,
            status=TaskStatus.DONE,
            date__gt=today - dt.timedelta(days=STREAK_MAX_LOOKBACK_DAYS),
        ).values_list("date", flat=True)
    )
    day = today if today in done_dates else today - dt.timedelta(days=1)
    streak = 0
    while day in done_dates and streak < STREAK_MAX_LOOKBACK_DAYS:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def habit_best_streak(habit):
    """The longest-ever run of consecutive completed days for this habit (a personal record)."""
    done_dates = sorted(
        Task.objects.filter(habit=habit, status=TaskStatus.DONE).values_list("date", flat=True)
    )
    if not done_dates:
        return 0
    best = current = 1
    for previous, current_date in zip(done_dates, done_dates[1:]):
        if (current_date - previous).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best



HISTORY_WEEKS = 12


def habit_history(habit, today, weeks=HISTORY_WEEKS):
    """A Saturday-first grid of the last `weeks` weeks for one habit, plus completion numbers.

    Cell states: done, missed (task exists, not done, day is over), pending (today, still open),
    none (no task that day), future. Moved occurrences are detached from the habit, so they
    count as neither done nor missed.
    """
    from utils.jalali import to_jalali

    from utils.dates import week_start, weekday_name

    this_week_start = week_start(today)
    start = this_week_start - dt.timedelta(days=7 * (weeks - 1))
    by_date = {t.date: t for t in Task.objects.filter(habit=habit, date__range=(start, today))}

    def state_of(day):
        if day > today:
            return "future"
        task = by_date.get(day)
        if task is None:
            return "none"
        if task.status == TaskStatus.DONE:
            return "done"
        if task.status == TaskStatus.FAILED or day < today:
            return "missed"
        return "pending"

    columns = []
    weekday_done = [0] * 7
    weekday_total = [0] * 7
    done = missed = 0
    for w in range(weeks):
        cells = []
        for d in range(7):
            day = start + dt.timedelta(days=7 * w + d)
            state = state_of(day)
            if state == "done":
                done += 1
                weekday_done[d] += 1
                weekday_total[d] += 1
            elif state == "missed":
                missed += 1
                weekday_total[d] += 1
            cells.append({"date": day, "state": state})
        columns.append({"cells": cells})

    counted = done + missed
    weekdays = [
        {
            "label": weekday_name(start + dt.timedelta(days=i)),
            "done": weekday_done[i],
            "total": weekday_total[i],
            "percent": round(weekday_done[i] * 100 / weekday_total[i]) if weekday_total[i] else 0,
        }
        for i in range(7)
    ]
    return {
        "columns": columns,
        "done": done,
        "missed": missed,
        "rate": round(done * 100 / counted) if counted else None,
        "weekdays": weekdays,
        "has_data": counted > 0,
    }


def reconcile_future_occurrences(habit):
    """Apply an edited habit template only to future, unfinished generated tasks.

    Today/past records and completed/failed records are history and stay untouched.
    Only the owner's rows linked to this exact template may be changed.
    """
    from apps.tasks.models import OPEN_STATUSES
    future = Task.objects.filter(user=habit.user, habit=habit, date__gt=timezone.localdate(), status__in=OPEN_STATUSES)
    tags = list(habit.tags.all())
    for task in future:
        if not habit.active or (habit.starts_on and task.date < habit.starts_on) or not habit.occurs_on(to_jalali(task.date).weekday()):
            task.delete()
            continue
        task.title = habit.title
        task.goal = habit.goal
        task.start_time = habit.start_time
        task.end_time = habit.end_time
        task.priority = habit.priority
        task.save(update_fields=['title','goal','start_time','end_time','priority'])
        task.tags.set(tags)
