"""The Today page: today's tasks, near deadlines, today's note, and the review panel."""
import datetime as dt

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Avg, Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.badges import compute_badges
from apps.core.focus import FOCUS_MAX_MINUTES, FOCUS_MIN_MINUTES, focus_summary
from apps.core.insights import compute_insights
from apps.goals.models import Goal, GoalStatus
from apps.habits.services import sync_habits_for_date
from apps.journal.forms import DayNoteForm
from apps.journal.models import DayNote
from apps.tasks.forms import TaskForm
from apps.tasks.models import OPEN_STATUSES, FocusSession, Task, TaskStatus
from utils.dates import day_number, full_date, month_key, month_label, week_offset
from utils.jalali import to_persian_digits

DEADLINE_LOOKAHEAD_DAYS = 7


def greeting_for_hour(hour: int) -> str:
    """A time-of-day greeting for the Today header (hour is 0-23, local time)."""
    if 5 <= hour < 12:
        return "صبح بخیر"
    if 12 <= hour < 17:
        return "ظهر بخیر"
    if 17 <= hour < 21:
        return "عصر بخیر"
    return "شب بخیر"


def hero_message(done: int, total: int) -> str:
    """The short status line under the greeting; mirrored client-side after each change."""
    if total == 0:
        return "یک کار کوچک بنویس و روزت را شروع کن."
    if done == total:
        return "همه‌ی کارهای امروز انجام شد. دستت درد نکنه!"
    return f"{to_persian_digits(total - done)} کار مونده؛ قدم‌به‌قدم."


def _next_up(tasks, now_time):
    """The task to do next: the earliest timed open task from now on, else one already in progress."""
    open_tasks = [t for t in tasks if t.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS)]
    upcoming = sorted((t for t in open_tasks if t.start_time and t.start_time >= now_time), key=lambda t: t.start_time)
    if upcoming:
        return upcoming[0]
    return next((t for t in open_tasks if t.status == TaskStatus.IN_PROGRESS), None)


def _onboarding(user):
    """Four first-run steps, each ticked from real data; the card hides itself once all are done."""
    from apps.habits.models import Habit  # local import: keep module import order simple

    steps = [
        {"key": "goal", "title": "یک هدف بساز", "hint": "مثلاً «تمام کردن پروژه‌ی ترم»", "icon": "i-goals",
         "url": "goals:create", "done": Goal.objects.filter(user=user).exists()},
        {"key": "habit", "title": "یک عادت تعریف کن", "hint": "کاری که می‌خواهی هر روز تکرار شود", "icon": "i-habits",
         "url": "habits:create", "done": Habit.objects.filter(user=user).exists()},
        {"key": "task", "title": "یک تسک را انجام بده", "hint": "اولین تیک را بزن", "icon": "i-check-circle",
         "url": "tasks:list", "done": Task.objects.filter(user=user, status=TaskStatus.DONE).exists()},
        {"key": "note", "title": "یادداشت امروز را بنویس", "hint": "چند خط از حال‌وهوایت", "icon": "i-book",
         "url": "core:home", "done": DayNote.objects.filter(user=user).exclude(text="", mood__isnull=True).exists()},
    ]
    done = sum(1 for s in steps if s["done"])
    return {"steps": steps, "done": done, "total": len(steps), "percent": round(done * 100 / len(steps)),
            "complete": done == len(steps)}


def home(request):
    """Landing page for visitors; for signed-in users, the Today page.

    Today shows tasks/note/deadlines, a progress ring, and a nightly-review trigger.
    """
    if not request.user.is_authenticated:
        return render(request, "core/landing.html")
    today = timezone.localdate()
    sync_habits_for_date(request.user, today)
    tasks = Task.objects.filter(user=request.user, date=today).select_related("goal").priority_ordered()
    upcoming_goals = Goal.objects.filter(
        user=request.user,
        status=GoalStatus.ACTIVE,
        deadline__range=(today, today + dt.timedelta(days=DEADLINE_LOOKAHEAD_DAYS)),
    ).order_by("deadline")
    note = DayNote.objects.filter(user=request.user, date=today).first()
    counts = tasks.aggregate(total=Count("id"), done=Count("id", filter=Q(status=TaskStatus.DONE)))
    total_count, done_count = counts["total"], counts["done"]
    from apps.habits.models import Habit
    overview_goals = list(Goal.objects.filter(user=request.user, status=GoalStatus.ACTIVE).annotate(task_total=Count("tasks"), task_done=Count("tasks", filter=Q(tasks__status=TaskStatus.DONE))).order_by("deadline")[:3])
    for goal in overview_goals:
        goal.overview_progress = round(goal.task_done * 100 / goal.task_total) if goal.task_total else 0
    week_start = today - dt.timedelta(days=week_offset(today))
    week_counts = {row["date"]: row for row in Task.objects.filter(user=request.user, date__range=(week_start, week_start + dt.timedelta(days=6))).values("date").annotate(total=Count("id"), done=Count("id", filter=Q(status=TaskStatus.DONE)))}
    week_strip = []
    from utils.dates import weekday_name
    for offset in range(7):
        day = week_start + dt.timedelta(days=offset)
        row = week_counts.get(day, {"total": 0, "done": 0})
        week_strip.append({"date": day, "label": weekday_name(day), "day": day_number(day), "total": row["total"], "done": row["done"], "is_today": day == today})

    context = {
        "greeting": greeting_for_hour(timezone.localtime().hour),
        "overview_goals": overview_goals,
        "week_strip": week_strip,
        "focus_summary": focus_summary(request.user, today),
        "active_habits_count": Habit.objects.filter(user=request.user, active=True).count(),
        "week_summary": _completion_rate(request.user, today - dt.timedelta(days=6), today),
        "streak": _current_streak(request.user, today),
        "next_up": _next_up(list(tasks), timezone.localtime().time()),
        "onboarding": _onboarding(request.user),
        "hero_message": hero_message(done_count, total_count),
        "total_count": total_count,
        "done_count": done_count,
        "progress_percent": round(done_count * 100 / total_count) if total_count else 0,
        "today": today,
        "today_jalali": full_date(today),
        "tasks": tasks,
        "task_form": TaskForm(user=request.user, initial={"date": today}),
        "upcoming_goals": upcoming_goals,
        "note_form": DayNoteForm(instance=note or DayNote(user=request.user, date=today)),
        "has_open_tasks": tasks.filter(status__in=OPEN_STATUSES).exists(),
    }
    return render(request, "core/home.html", context)


@login_required
def review(request):
    """HTMX partial: today's unfinished tasks, each with move/fail/delete actions."""
    today = timezone.localdate()
    tasks = Task.objects.filter(
        user=request.user, date=today, status__in=OPEN_STATUSES
    ).select_related("goal").priority_ordered()
    return render(request, "core/_review.html", {"tasks": tasks})


def healthz(request):
    """Liveness/readiness probe for uptime monitors and load balancers.

    No login required (monitors don't have a session); checks the DB connection
    so a broken database also shows up as unhealthy, not just a 200 from Django.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


STATS_WEEK_DAYS = 7
STATS_MONTH_DAYS = 30
STREAK_MAX_LOOKBACK_DAYS = 3650  # ~10 years; a safety cap, not an expected real streak length


def _current_streak(user, today):
    """Consecutive days (ending today or yesterday) with at least one completed task.

    Today doesn't break the streak just because it isn't finished yet: if today has
    no done task, we start counting from yesterday instead of zeroing it out.
    """
    done_dates = set(
        Task.objects.filter(
            user=user, status=TaskStatus.DONE, date__gt=today - dt.timedelta(days=STREAK_MAX_LOOKBACK_DAYS),
        ).values_list("date", flat=True)
    )
    day = today if today in done_dates else today - dt.timedelta(days=1)
    streak = 0
    while day in done_dates and streak < STREAK_MAX_LOOKBACK_DAYS:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def _completion_rate(user, start, end):
    qs = Task.objects.filter(user=user, date__range=(start, end))
    total = qs.count()
    done = qs.filter(status=TaskStatus.DONE).count()
    return {"total": total, "done": done, "percent": round(done * 100 / total) if total else None}


HEATMAP_WEEKS = 14


def build_heatmap(user, today, weeks=HEATMAP_WEEKS):
    """Activity map: completed tasks per day for the last `weeks` Persian weeks.

    Returns columns (one per week, Saturday first) of 7 cells each. `level` is 0 (nothing
    done) to 4 (the user's busiest day in the window), so the scale adapts to the person.
    """
    start = today - dt.timedelta(days=week_offset(today) + 7 * (weeks - 1))  # first day of the week: Sat (fa) / Mon (en)
    counts = {
        row["date"]: row["n"]
        for row in Task.objects.filter(user=user, status=TaskStatus.DONE, date__range=(start, today))
        .values("date")
        .annotate(n=Count("id"))
    }
    peak = max(counts.values(), default=0)
    columns, previous_month = [], None
    for week in range(weeks):
        first_day = start + dt.timedelta(days=week * 7)
        month = month_key(first_day)
        cells = []
        for offset in range(7):
            day = first_day + dt.timedelta(days=offset)
            if day > today:
                cells.append({"date": day, "count": 0, "level": 0, "future": True, "label": ""})
                continue
            count = counts.get(day, 0)
            level = min(4, max(1, -(-4 * count // peak))) if count else 0
            when = full_date(day)
            label = f"{when}: {to_persian_digits(count)} تسک انجام‌شده" if count else f"{when}: بدون تسک انجام‌شده"
            cells.append({"date": day, "count": count, "level": level, "future": False, "label": label})
        columns.append({"cells": cells, "month_label": month_label(first_day) if month != previous_month else ""})
        previous_month = month
    return {"columns": columns, "total_done": sum(counts.values()), "active_days": len(counts)}


@login_required
def focus(request):
    """Pomodoro-style focus timer; optionally tied to one of today's open tasks (?task=<id>)."""
    today = timezone.localdate()
    tasks = (
        Task.objects.filter(user=request.user, date=today, status__in=OPEN_STATUSES)
        .select_related("goal")
        .priority_ordered()
    )
    raw = request.GET.get("task", "")
    return render(request, "core/focus.html", {
        "tasks": tasks,
        "selected_id": int(raw) if raw.isdigit() else None,
        "focus": focus_summary(request.user, today),
    })


@login_required
@require_POST
def focus_log(request):
    """Record one finished focus block (called by the timer); answers with today's totals."""
    try:
        minutes = int(request.POST.get("minutes", ""))
    except ValueError:
        return JsonResponse({"ok": False, "error": "minutes must be a number"}, status=400)
    if not FOCUS_MIN_MINUTES <= minutes <= FOCUS_MAX_MINUTES:
        return JsonResponse({"ok": False, "error": "minutes out of range"}, status=400)
    task = None
    raw = request.POST.get("task", "")
    if raw:
        task = Task.objects.filter(pk=int(raw), user=request.user).first() if raw.isdigit() else None
        if task is None:
            return JsonResponse({"ok": False, "error": "unknown task"}, status=400)
    today = timezone.localdate()
    FocusSession.objects.create(user=request.user, task=task, minutes=minutes, date=today)
    summary = focus_summary(request.user, today)
    return JsonResponse({
        "ok": True,
        "today_sessions": summary["today_sessions"],
        "today_minutes": summary["today_minutes"],
        "week_minutes": summary["week_minutes"],
    })


@login_required
def stats(request):
    """Simple weekly/monthly dashboard: task completion, mood average, goal counts."""
    today = timezone.localdate()
    week_start = today - dt.timedelta(days=STATS_WEEK_DAYS - 1)
    month_start = today - dt.timedelta(days=STATS_MONTH_DAYS - 1)

    week = _completion_rate(request.user, week_start, today)
    month = _completion_rate(request.user, month_start, today)

    mood_avg = DayNote.objects.filter(
        user=request.user, date__range=(week_start, today), mood__isnull=False,
    ).aggregate(avg=Avg("mood"))["avg"]

    goal_counts = {
        row["status"]: row["count"]
        for row in Goal.objects.filter(user=request.user).values("status").annotate(count=Count("id"))
    }

    per_day = {
        row["date"]: row
        for row in Task.objects.filter(user=request.user, date__range=(week_start, today))
        .values("date")
        .annotate(total=Count("id"), done=Count("id", filter=Q(status=TaskStatus.DONE)))
    }
    daily = []
    for offset in range(STATS_WEEK_DAYS - 1, -1, -1):
        day = today - dt.timedelta(days=offset)
        row = per_day.get(day, {"total": 0, "done": 0})
        total, done = row["total"], row["done"]
        daily.append({
            "date": day,
            "label": day_number(day),
            "percent": round(done * 100 / total) if total else 0,
            "total": total,
        })

    streak = _current_streak(request.user, today)
    badges = compute_badges(request.user, streak)

    context = {
        "week": week,
        "month": month,
        "streak": streak,
        "badges": badges,
        "insights": compute_insights(request.user, today),
        "focus": focus_summary(request.user, today),
        "badges_earned": sum(1 for b in badges if b["earned"]),
        "week_spark": _sparkline([d["percent"] for d in daily]),
        "mood_avg": round(mood_avg, 1) if mood_avg is not None else None,
        "active_goals": goal_counts.get(GoalStatus.ACTIVE, 0),
        "completed_goals": goal_counts.get(GoalStatus.COMPLETED, 0),
        "abandoned_goals": goal_counts.get(GoalStatus.ABANDONED, 0),
        "daily": daily,
        "heatmap": build_heatmap(request.user, today),
    }
    return render(request, "core/stats.html", context)


def _sparkline(values, width=100, height=30, pad=3):
    """SVG polyline points (viewBox 0 0 100 30) for a series of 0-100 values; '' if fewer than 2."""
    if len(values) < 2:
        return ""
    step = width / (len(values) - 1)
    span = height - 2 * pad
    return " ".join(f"{i * step:.1f},{height - pad - (v or 0) * span / 100:.1f}" for i, v in enumerate(values))


def offline_page(request):
    """Static fallback the service worker shows when a navigation fails with no connection."""
    return render(request, "core/offline.html")


def service_worker(request):
    """Serve sw.js from the site root (not /static/) so its default scope covers the whole app.

    A service worker's scope defaults to the directory it's served from; registering it from
    under /static/ would only ever let it control static assets, not page navigations.
    """
    sw_path = settings.BASE_DIR / "static" / "sw.js"
    response = HttpResponse(sw_path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def set_language(request, code):
    """Remember the interface language in a cookie and go back where the visitor came from."""
    from .ui import COOKIE_MAX_AGE, LANG_COOKIE, SUPPORTED_LANGS

    if code not in SUPPORTED_LANGS:
        raise Http404("unknown language")
    target = request.GET.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = "/"
    response = redirect(target)
    response.set_cookie(LANG_COOKIE, code, max_age=COOKIE_MAX_AGE, samesite="Lax", path="/")
    return response
