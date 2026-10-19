"""Positioning math for the daily hourly timeline (kept separate from views.py for testability)."""
import datetime as dt

MINUTES_PER_DAY = 24 * 60
DEFAULT_BLOCK_MINUTES = 30  # used when a task has a start_time but no end_time


def _minutes_since_midnight(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def position_task(task) -> dict:
    """Return {top, height} as percentages (0-100) of a full 24h column for one task."""
    start_minutes = _minutes_since_midnight(task.start_time)
    if task.end_time:
        end_minutes = _minutes_since_midnight(task.end_time)
    else:
        end_minutes = start_minutes + DEFAULT_BLOCK_MINUTES
    duration = max(end_minutes - start_minutes, 15)  # keep very short tasks visible
    return {
        "task": task,
        "top": round(start_minutes / MINUTES_PER_DAY * 100, 2),
        "height": round(duration / MINUTES_PER_DAY * 100, 2),
    }


def split_timed_and_untimed(tasks):
    """(positioned timed tasks sorted by start time, untimed tasks) for one day's queryset."""
    timed = [t for t in tasks if t.start_time]
    untimed = [t for t in tasks if not t.start_time]
    timed.sort(key=lambda t: t.start_time)
    return [position_task(t) for t in timed], untimed
