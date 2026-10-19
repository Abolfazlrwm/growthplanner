"""Plain-language observations about the user's own habits, computed from their real data.

Every insight has a minimum amount of data before it is shown, so a brand-new account never
gets a confident-sounding sentence built on two tasks.
"""
import datetime as dt

from django.db.models import Count, Q

from apps.journal.models import DayNote
from apps.tasks.models import Task, TaskStatus
from utils.jalali import JALALI_WEEKDAYS, to_jalali, to_persian_digits

WINDOW_DAYS = 90
MIN_DONE_FOR_WEEKDAY = 10
MIN_TIMED_FOR_TIME_OF_DAY = 5
MIN_DAYS_PER_MOOD_GROUP = 3

# (label, first hour, last hour exclusive)
TIME_BUCKETS = (
    ("صبح", 5, 12),
    ("ظهر و بعدازظهر", 12, 17),
    ("عصر", 17, 21),
    ("شب", 21, 29),  # 21:00 up to 04:59 (hours 0-4 are mapped to 24-28 below)
)


def _fa(value):
    return to_persian_digits(value)


def _bucket_for(time):
    hour = time.hour if time.hour >= 5 else time.hour + 24
    for label, low, high in TIME_BUCKETS:
        if low <= hour < high:
            return label
    return TIME_BUCKETS[-1][0]


def compute_insights(user, today, days=WINDOW_DAYS):
    """Return a list of {key, icon, title, text} dicts (possibly empty)."""
    start = today - dt.timedelta(days=days - 1)
    insights = []

    done = list(
        Task.objects.filter(user=user, status=TaskStatus.DONE, date__range=(start, today))
        .values_list("date", "start_time")
    )

    if len(done) >= MIN_DONE_FOR_WEEKDAY:
        counts = {}
        for day, _ in done:
            wd = to_jalali(day).weekday()
            counts[wd] = counts.get(wd, 0) + 1
        best_wd, best_n = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
        insights.append({
            "key": "weekday",
            "icon": "i-calendar",
            "title": "قوی‌ترین روز هفته",
            "text": f"بیشتر تسک‌هایت را {JALALI_WEEKDAYS[best_wd]}‌ها انجام داده‌ای ({_fa(best_n)} از {_fa(len(done))} تسک در ۹۰ روز اخیر).",
        })

    timed = [t for _, t in done if t is not None]
    if len(timed) >= MIN_TIMED_FOR_TIME_OF_DAY:
        buckets = {}
        for t in timed:
            label = _bucket_for(t)
            buckets[label] = buckets.get(label, 0) + 1
        best_label, best_n = max(buckets.items(), key=lambda kv: (kv[1], kv[0]))
        insights.append({
            "key": "time",
            "icon": "i-clock",
            "title": "ساعت طلایی",
            "text": f"از تسک‌های ساعت‌دارت، بیشتر آن‌ها که تمام شده‌اند در «{best_label}» بوده‌اند ({_fa(best_n)} از {_fa(len(timed))}).",
        })

    per_day = {
        row["date"]: row
        for row in Task.objects.filter(user=user, date__range=(start, today))
        .values("date")
        .annotate(total=Count("id"), done=Count("id", filter=Q(status=TaskStatus.DONE)))
    }
    high, low = [], []
    for day, mood in DayNote.objects.filter(user=user, date__range=(start, today), mood__isnull=False).values_list("date", "mood"):
        row = per_day.get(day)
        if not row or not row["total"]:
            continue
        rate = row["done"] * 100 / row["total"]
        if mood >= 4:
            high.append(rate)
        elif mood <= 2:
            low.append(rate)
    if len(high) >= MIN_DAYS_PER_MOOD_GROUP and len(low) >= MIN_DAYS_PER_MOOD_GROUP:
        high_avg = round(sum(high) / len(high))
        low_avg = round(sum(low) / len(low))
        insights.append({
            "key": "mood",
            "icon": "i-mood-4",
            "title": "حال‌وهوا و انجام کارها",
            "text": (
                f"در روزهایی که حال‌وهوایت «خوب» یا «عالی» بوده، {_fa(high_avg)}٪ از تسک‌هایت انجام شده؛ "
                f"در روزهای «بد» یا «خیلی بد»، {_fa(low_avg)}٪."
            ),
        })
    return insights
