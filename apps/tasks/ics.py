"""Small, dependency-free RFC 5545 serializers for exports and subscriptions."""
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo


DEFAULT_DURATION_MINUTES = 30  # used when a task has a start time but no end time
TEHRAN = ZoneInfo("Asia/Tehran")


@dataclass(frozen=True)
class CalendarEvent:
    """A serializable event independent of any ORM model."""

    uid: str
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    description: str = ""


def _escape(text):
    """Escape RFC 5545 TEXT and neutralize CR/LF property-injection attempts."""
    text = str(text).replace("\\", "\\\\")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold_line(line):
    """Fold one content line at 75 UTF-8 octets without splitting a character."""
    chunks = []
    current = []
    octets = 0
    limit = 75
    for char in line:
        size = len(char.encode("utf-8"))
        if current and octets + size > limit:
            chunks.append("".join(current))
            current = [char]
            octets = size
            limit = 74  # one leading SP consumes the 75th octet after folding
        else:
            current.append(char)
            octets += size
    chunks.append("".join(current))
    return "\r\n ".join(chunks)


def _serialize(lines):
    return "\r\n".join(_fold_line(line) for line in lines) + "\r\n"


def _event_lines(task, dtstamp):
    """Legacy export event: intentionally retains floating local time compatibility."""
    uid = f"task-{task.id}@growth-planner"
    summary = _escape(task.title)
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dtstamp}"]

    if task.start_time:
        start = dt.datetime.combine(task.date, task.start_time)
        end_time = task.end_time
        end = (
            dt.datetime.combine(task.date, end_time)
            if end_time
            else start + dt.timedelta(minutes=DEFAULT_DURATION_MINUTES)
        )
        lines.append(f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}")
    else:
        lines.append(f"DTSTART;VALUE=DATE:{task.date.strftime('%Y%m%d')}")

    lines.append(f"SUMMARY:{summary}")
    if task.goal_id:
        lines.append(f"DESCRIPTION:{_escape('هدف: ' + task.goal.title)}")
    lines.append("END:VEVENT")
    return lines


def build_ics(tasks, calendar_name="تسک‌های من"):
    """Return legacy .ics content, retaining the original floating timed events."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//growth-planner//FA",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        "X-WR-TIMEZONE:Asia/Tehran",
    ]
    for task in tasks:
        lines.extend(_event_lines(task, now))
    lines.append("END:VCALENDAR")
    return _serialize(lines)


def _utc_value(date, time):
    local = dt.datetime.combine(date, time, tzinfo=TEHRAN)
    return local.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _subscription_event_lines(event, dtstamp):
    lines = ["BEGIN:VEVENT", f"UID:{event.uid}", f"DTSTAMP:{dtstamp}"]
    if event.start_time is None:
        lines.append(f"DTSTART;VALUE=DATE:{event.date:%Y%m%d}")
        # DTSTART/DTEND DATE is an exclusive range in iCalendar.
        lines.append(f"DTEND;VALUE=DATE:{event.date + dt.timedelta(days=1):%Y%m%d}")
    else:
        start = dt.datetime.combine(event.date, event.start_time)
        end = (
            dt.datetime.combine(event.date, event.end_time)
            if event.end_time is not None
            else start + dt.timedelta(minutes=DEFAULT_DURATION_MINUTES)
        )
        lines.append(f"DTSTART:{_utc_value(start.date(), start.time())}")
        lines.append(f"DTEND:{_utc_value(end.date(), end.time())}")
    lines.append(f"SUMMARY:{_escape(event.title)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape(event.description)}")
    lines.append("END:VEVENT")
    return lines


def build_subscription_ics(events, calendar_name="Growth Planner"):
    """Serialize a subscription feed with UTC timed events and strict RFC folding."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//growth-planner//Calendar Subscription//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        "X-WR-TIMEZONE:Asia/Tehran",
    ]
    for event in events:
        lines.extend(_subscription_event_lines(event, now))
    lines.append("END:VCALENDAR")
    return _serialize(lines)
