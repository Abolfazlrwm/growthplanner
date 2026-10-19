"""Jalali monthly calendar + the single-day hourly timeline."""
import calendar
import datetime as dt

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from apps.habits.services import sync_habits_for_date, sync_habits_for_range
from apps.tasks.models import Task
from utils.jalali import (
    JALALI_MONTHS, build_month_grid, next_month, prev_month, to_jalali, to_persian_digits,
)

from utils.dates import (
    EN_MONTHS, EN_WEEKDAYS, is_english, is_weekend, short_date, week_range_text,
    week_start, weekday_name, day_number,
)

from .timeline import split_timed_and_untimed

# Order controls which dot shows first when a day has several statuses.
STATUS_DOT_ORDER = ["done", "in_progress", "todo", "moved", "failed"]
# CSS classes (see `.dot-*` in static/css/app.css), one per task status.
STATUS_DOT_CLASS = {
    "done": "dot-done",
    "in_progress": "dot-in_progress",
    "todo": "dot-todo",
    "moved": "dot-moved",
    "failed": "dot-failed",
}


def _gregorian_grid(year, month):
    """Monday-first weeks for a Gregorian month, in the same shape build_month_grid() returns."""
    return [
        [
            {"gregorian": d, "jalali_day": str(d.day), "in_month": d.month == month, "is_holiday": d.weekday() in (5, 6)}
            for d in week
        ]
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    ]


def _weekday_headers(english):
    """(full name, short label, is_weekend) for the month header, in display order."""
    if english:
        shorts = ("M", "T", "W", "T", "F", "S", "S")
        return [(EN_WEEKDAYS[i], shorts[i], i >= 5) for i in range(7)]
    names = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
    shorts = ("ش", "ی", "د", "س", "چ", "پ", "ج")
    return [(names[i], shorts[i], i == 6) for i in range(7)]


@login_required
def month_view(request, year=None, month=None):
    english = is_english()
    today = timezone.localdate()
    today_j = to_jalali(today)
    if english:
        # The URL carries a Gregorian year/month in English mode; fall back to "now" when a
        # Jalali-looking value (e.g. left over from switching language) arrives.
        if year is None or month is None or not (1900 <= year <= 2200 and 1 <= month <= 12):
            year, month = today.year, today.month
        grid = _gregorian_grid(year, month)
        prev_year, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
        next_year, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
        month_name, year_label = EN_MONTHS[month - 1], str(year)
        is_current = (year, month) == (today.year, today.month)
    else:
        if year is None or month is None or year >= 1900 or not (1 <= month <= 12):
            year, month = today_j.year, today_j.month
        grid = build_month_grid(year, month)
        prev_year, prev_m = prev_month(year, month)
        next_year, next_m = next_month(year, month)
        month_name, year_label = JALALI_MONTHS[month - 1], to_persian_digits(year)
        is_current = (year, month) == (today_j.year, today_j.month)

    grid_start = grid[0][0]["gregorian"]
    grid_end = grid[-1][-1]["gregorian"]
    sync_habits_for_range(request.user, grid_start, grid_end)

    statuses_by_date = {}
    task_qs = Task.objects.filter(
        user=request.user, date__range=(grid_start, grid_end)
    ).values_list("date", "status")
    for date, status in task_qs:
        statuses_by_date.setdefault(date, set()).add(status)

    for week in grid:
        for day in week:
            present = statuses_by_date.get(day["gregorian"], set())
            day["dots"] = [
                STATUS_DOT_CLASS[s] for s in STATUS_DOT_ORDER if s in present
            ]

    context = {
        "grid": grid,
        "year": year,
        "month": month,
        "month_name": month_name,
        "year_fa": year_label,
        "prev_year": prev_year, "prev_month": prev_m,
        "next_year": next_year, "next_month": next_m,
        "is_current_month": is_current,
        "today_gregorian": today,
        "weekdays": _weekday_headers(english),
    }
    return render(request, "calendar_view/month.html", context)


HOURS = range(24)


@login_required
def day_timeline(request, date=None):
    """A simple hourly view (no drag & drop) of one day's timed tasks."""
    if date is None:
        the_date = timezone.localdate()
    else:
        try:
            the_date = dt.date.fromisoformat(date)
        except ValueError:
            raise Http404("تاریخ نامعتبر است.")

    sync_habits_for_date(request.user, the_date)
    tasks = Task.objects.filter(user=request.user, date=the_date).select_related("goal")
    timed_positions, untimed_tasks = split_timed_and_untimed(list(tasks))

    is_today = the_date == timezone.localdate()
    now = timezone.localtime()
    context = {
        "date": the_date,
        "hours": HOURS,
        # Minutes since midnight (= pixels on the 60px/hour grid) for the "now" marker.
        "now_minutes": now.hour * 60 + now.minute if is_today else None,
        "timed_positions": timed_positions,
        "untimed_tasks": untimed_tasks,
        "prev_date": the_date - dt.timedelta(days=1),
        "next_date": the_date + dt.timedelta(days=1),
        "is_today": is_today,
    }
    return render(request, "calendar_view/timeline.html", context)


@login_required
def week_view(request, date=None):
    """A seven-day board (Saturday → Friday) around `date`, for planning the whole week."""
    if date is None:
        anchor = timezone.localdate()
    else:
        try:
            anchor = dt.date.fromisoformat(date)
        except ValueError:
            raise Http404("تاریخ نامعتبر است.")

    start = week_start(anchor)  # Saturday in Persian, Monday in English
    end = start + dt.timedelta(days=6)
    sync_habits_for_range(request.user, start, end)

    by_day = {}
    for task in Task.objects.filter(user=request.user, date__range=(start, end)).select_related(
        "goal", "habit"
    ).priority_ordered():
        by_day.setdefault(task.date, []).append(task)

    today = timezone.localdate()
    days = []
    week_total = week_done = 0
    for offset in range(7):
        day = start + dt.timedelta(days=offset)
        tasks = by_day.get(day, [])
        done = sum(1 for t in tasks if t.status == "done")
        week_total += len(tasks)
        week_done += done
        days.append({
            "date": day,
            "weekday": weekday_name(day),
            "label": short_date(day),
            "day_number": day_number(day),
            "is_today": day == today,
            "is_friday": is_weekend(day),
            "tasks": tasks,
            "total": len(tasks),
            "done": done,
            "percent": round(done * 100 / len(tasks)) if tasks else 0,
        })

    context = {
        "days": days,
        "week_start": start,
        "week_range": week_range_text(start, end),
        "prev_week": start - dt.timedelta(days=7),
        "next_week": start + dt.timedelta(days=7),
        "is_current_week": start <= today <= end,
        "week_total": week_total,
        "week_done": week_done,
        "week_percent": round(week_done * 100 / week_total) if week_total else 0,
    }
    return render(request, "calendar_view/week.html", context)
