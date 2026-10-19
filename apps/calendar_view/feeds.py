"""Private iCalendar subscription management and read-only feed delivery."""
import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.habits.models import Habit
from apps.tasks.ics import CalendarEvent, build_subscription_ics
from apps.tasks.models import Task
from utils.jalali import to_jalali

from .forms import CalendarSubscriptionActionForm
from .models import CalendarSubscription

# A subscription is deliberately finite. It has enough history for calendar clients to
# reconcile recent events, while limiting both disclosure and response work.
FEED_PAST_DAYS = 30
FEED_FUTURE_DAYS = 365
FEED_MAX_EVENTS = 1000


def _language_is_english(request):
    return getattr(request, "ui_lang", "fa") == "en"


def _set_private_no_store(response):
    """Do not let a browser, proxy, or shared computer retain a bearer feed URL."""
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _subscription_window(today):
    return (
        today - dt.timedelta(days=FEED_PAST_DAYS),
        today + dt.timedelta(days=FEED_FUTURE_DAYS),
    )


def _event_from_task(task):
    # A materialised habit occurrence must keep the same UID as its earlier virtual
    # projection; otherwise a subscribing client can retain both versions.
    uid = (
        f"habit-{task.habit_id}-{task.date:%Y%m%d}@growth-planner"
        if task.habit_id is not None
        else f"task-{task.pk}@growth-planner"
    )
    return CalendarEvent(
        uid=uid,
        title=task.title,
        date=task.date,
        start_time=task.start_time,
        end_time=task.end_time,
    )


def subscription_events(user, start_date, end_date, *, today=None, limit=FEED_MAX_EVENTS):
    """Build bounded, deterministic feed events without creating Task rows.

    Habit tasks already materialised by normal planner views and missing virtual
    occurrences use the same stable ``habit-<id>-<YYYYMMDD>`` UID. Missing occurrences
    are projected only from today onward, so a later planner visit cannot create a
    second calendar event for the same habit date.
    """
    if limit <= 0:
        return []

    actual_tasks = list(
        Task.objects.filter(user=user, date__range=(start_date, end_date))
        .order_by("date", "start_time", "pk")[:limit]
    )
    events = [_event_from_task(task) for task in actual_tasks]

    # When the task list hit the cap, do not query/project habits.  This is both a hard
    # response bound and means every persisted Task in the queried range was considered
    # whenever there is space for a projected event.
    if len(events) >= limit:
        return events

    persisted_habit_dates = {
        (task.habit_id, task.date)
        for task in actual_tasks
        if task.habit_id is not None
    }
    projection_start = max(start_date, today or timezone.localdate())
    habits = list(Habit.objects.filter(user=user, active=True).order_by("pk"))

    day = projection_start
    while day <= end_date and len(events) < limit:
        jalali_weekday = to_jalali(day).weekday()
        for habit in habits:
            if len(events) >= limit:
                break
            if habit.starts_on and day < habit.starts_on:
                continue
            if not habit.occurs_on(jalali_weekday) or (habit.pk, day) in persisted_habit_dates:
                continue
            events.append(
                CalendarEvent(
                    uid=f"habit-{habit.pk}-{day:%Y%m%d}@growth-planner",
                    title=habit.title,
                    date=day,
                    start_time=habit.start_time,
                    end_time=habit.end_time,
                )
            )
        day += dt.timedelta(days=1)

    # The source query is chronological; projection is appended.  Sorting makes output
    # deterministic and conventional without affecting stable UIDs.
    return sorted(events, key=lambda event: (event.date, event.start_time or dt.time.min, event.uid))


@login_required
@require_http_methods(["GET", "POST"])
def subscription(request):
    """Show and rotate/revoke the authenticated user's bearer-link subscription."""
    calendar_subscription, _ = CalendarSubscription.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = CalendarSubscriptionActionForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            if action == CalendarSubscriptionActionForm.ROTATE:
                calendar_subscription.rotate()
                text = (
                    "A fresh calendar link was created. The old link no longer works."
                    if _language_is_english(request)
                    else "یک پیوند تازه ساخته شد؛ پیوند قبلی دیگر کار نمی‌کند."
                )
            else:
                calendar_subscription.revoke()
                text = (
                    "The calendar link was revoked. It no longer works."
                    if _language_is_english(request)
                    else "پیوند تقویم باطل شد و دیگر کار نمی‌کند."
                )
            messages.success(request, text)
            return redirect("calendar_view:subscription")

        messages.error(
            request,
            "Invalid subscription request." if _language_is_english(request) else "درخواست اشتراک نامعتبر است.",
        )
        return redirect("calendar_view:subscription")

    start_date, end_date = _subscription_window(timezone.localdate())
    feed_path = reverse("calendar_view:feed", kwargs={"token": calendar_subscription.token})
    response = render(
        request,
        "calendar_view/subscription.html",
        {
            "subscription": calendar_subscription,
            "feed_path": feed_path,
            "feed_past_days": FEED_PAST_DAYS,
            "feed_future_days": FEED_FUTURE_DAYS,
            "feed_max_events": FEED_MAX_EVENTS,
            "window_start": start_date,
            "window_end": end_date,
            "action_form": CalendarSubscriptionActionForm(),
        },
    )
    return _set_private_no_store(response)


@require_GET
def calendar_feed(request, token):
    """Serve a bearer-token calendar feed; this view never syncs or writes Tasks."""
    calendar_subscription = (
        CalendarSubscription.objects.select_related("user")
        .filter(
            token=token,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if calendar_subscription is None:
        # Do not include the bearer secret in an error message or log entry.
        raise Http404("Calendar feed is unavailable.")

    today = timezone.localdate()
    start_date, end_date = _subscription_window(today)
    events = subscription_events(
        calendar_subscription.user,
        start_date,
        end_date,
        today=today,
    )
    content = build_subscription_ics(events)
    response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="growth-planner.ics"'
    return _set_private_no_store(response)
