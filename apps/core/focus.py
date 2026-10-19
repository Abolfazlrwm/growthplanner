"""Focus-time numbers for the focus page and the stats page (all from logged FocusSession rows)."""
import datetime as dt

from django.db.models import Count, Sum

from apps.tasks.models import FocusSession
from utils.jalali import JALALI_WEEKDAYS, to_jalali

FOCUS_MIN_MINUTES = 1
FOCUS_MAX_MINUTES = 240


def focus_summary(user, today, days=7):
    """Today's sessions/minutes plus a per-day series for the last `days` days (oldest first)."""
    start = today - dt.timedelta(days=days - 1)
    rows = (
        FocusSession.objects.filter(user=user, date__range=(start, today))
        .values("date")
        .annotate(minutes=Sum("minutes"), sessions=Count("id"))
    )
    by_day = {r["date"]: r for r in rows}
    series = []
    for i in range(days):
        day = start + dt.timedelta(days=i)
        row = by_day.get(day)
        series.append({
            "date": day,
            "label": JALALI_WEEKDAYS[to_jalali(day).weekday()],
            "minutes": row["minutes"] if row else 0,
            "sessions": row["sessions"] if row else 0,
        })
    peak = max((d["minutes"] for d in series), default=0)
    for d in series:
        d["percent"] = round(d["minutes"] * 100 / peak) if peak else 0
    today_row = by_day.get(today)
    return {
        "today_minutes": today_row["minutes"] if today_row else 0,
        "today_sessions": today_row["sessions"] if today_row else 0,
        "week_minutes": sum(d["minutes"] for d in series),
        "week_sessions": sum(d["sessions"] for d in series),
        "series": series,
        "has_data": peak > 0,
    }
