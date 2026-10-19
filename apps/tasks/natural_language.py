"""Deterministic, offline parsing for the task quick-add screen.

This module intentionally does not guess from an LLM.  A phrase is only removed from the
visible title when it matches one of the documented rules; ambiguous or conflicting input is
reported to the caller so the preview screen can ask for confirmation.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import jdatetime
from django.utils import timezone

from utils.jalali import to_jalali


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTER_NORMALIZATION = str.maketrans({"ي": "ی", "ك": "ک", "‌": " "})


@dataclass
class ParsedTask:
    """Preview-ready result of parsing one quick-add phrase."""

    title: str = ""
    date: dt.date | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    priority: str = "medium"
    tags: list[str] = field(default_factory=list)
    recurrence: str = "none"  # none, daily, weekly
    weekly_weekday: int | None = None  # Jalali weekday: Saturday=0 ... Friday=6
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.warnings)

    def initial(self) -> dict:
        """Values suitable for ``SmartTaskPreviewForm(initial=...)``."""
        return {
            "title": self.title,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "priority": self.priority,
            "tag_names": ", ".join(self.tags),
            "recurrence": self.recurrence,
            "weekly_weekday": "" if self.weekly_weekday is None else str(self.weekly_weekday),
        }


def normalize_text(value: str) -> str:
    """Normalise Arabic/Persian digit variants and letter variants for parsing."""
    return (value or "").translate(_DIGITS).translate(_LETTER_NORMALIZATION)


def _clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\n,،؛|-–—")
    return value


def _set_once(result: ParsedTask, field_name: str, value, label: str) -> None:
    current = getattr(result, field_name)
    if current is not None and current != value:
        result.errors.append(f"بیش از یک {label} در متن پیدا شد؛ تاریخ/ساعت را در پیش‌نمایش مشخص کنید.")
        return
    setattr(result, field_name, value)


def _parse_numeric_date(match: re.Match[str], result: ParsedTask) -> str:
    year, month, day = (int(match.group(i)) for i in range(1, 4))
    try:
        if 1300 <= year <= 1599:
            parsed = jdatetime.date(year, month, day).togregorian()
        elif 1900 <= year <= 2200:
            parsed = dt.date(year, month, day)
        else:
            result.errors.append("سال تاریخ را به صورت میلادی ۱۹۰۰–۲۲۰۰ یا جلالی ۱۳۰۰–۱۵۹۹ بنویسید.")
            return match.group(0)
    except ValueError:
        result.errors.append(f"تاریخ «{match.group(0)}» معتبر نیست.")
        return match.group(0)
    _set_once(result, "date", parsed, "تاریخ")
    return " "


def _parse_time(value: str, result: ParsedTask) -> dt.time | None:
    hour, minute = int(value.split(":")[0]), int(value.split(":")[1] or 0) if ":" in value else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        result.errors.append(f"ساعت «{value}» معتبر نیست.")
        return None
    return dt.time(hour, minute)


def _weekday_date(today: dt.date, target: int, *, next_week: bool) -> dt.date:
    current = to_jalali(today).weekday()
    distance = (target - current) % 7
    if next_week:
        distance += 7
    return today + dt.timedelta(days=distance)


# Most specific forms come first.  Day indexes are in the existing Habit convention.
_WEEKDAYS = (
    ("سه شنبه", 3), ("سه‌شنبه", 3), ("چهارشنبه", 4), ("پنجشنبه", 5),
    ("یکشنبه", 1), ("دوشنبه", 2), ("شنبه", 0), ("جمعه", 6),
    ("monday", 2), ("tuesday", 3), ("wednesday", 4), ("thursday", 5),
    ("friday", 6), ("saturday", 0), ("sunday", 1),
)


def parse_task_phrase(phrase: str, *, today: dt.date | None = None) -> ParsedTask:
    """Parse supported Persian/English task syntax without network access.

    Supported deterministic markers are: today/tomorrow/day-after-tomorrow, Persian or
    English weekdays, ISO dates, numeric Jalali dates, ``ساعت ۹``/``at 9:30``, explicit
    durations, high/low priority words, hashtags, and daily/weekly recurrence words.
    """
    today = today or timezone.localdate()
    text = normalize_text(phrase)
    # Keep date unset while parsing: today is a fallback, not a competing explicit date.
    result = ParsedTask()

    # Recurrence is removed early; it is a scheduling instruction, not title text.
    daily_rx = re.compile(r"(?<!\w)(?:هر\s*روز|روزانه|every\s+day|daily)(?!\w)", re.I)
    weekly_rx = re.compile(r"(?<!\w)(?:هر\s*هفته|هفتگی|every\s+week|weekly)(?!\w)", re.I)
    has_daily = bool(daily_rx.search(text))
    has_weekly = bool(weekly_rx.search(text))
    if has_daily and has_weekly:
        result.errors.append("تکرار روزانه و هفتگی هم‌زمان مشخص شده؛ یکی را انتخاب کنید.")
    elif has_daily:
        result.recurrence = "daily"
    elif has_weekly:
        result.recurrence = "weekly"
    text = daily_rx.sub(" ", text)
    text = weekly_rx.sub(" ", text)

    # ISO (Gregorian) and numeric Jalali formats.  Year range decides calendar deterministically.
    date_rx = re.compile(r"(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)")
    text = date_rx.sub(lambda m: _parse_numeric_date(m, result), text)

    relatives = (
        (r"(?<!\w)(?:پس\s*فردا|day\s*after\s*tomorrow)(?!\w)", 2),
        (r"(?<!\w)(?:فردا|tomorrow)(?!\w)", 1),
        (r"(?<!\w)(?:امروز|today)(?!\w)", 0),
    )
    for pattern, days in relatives:
        if re.search(pattern, text, flags=re.I):
            _set_once(result, "date", today + dt.timedelta(days=days), "تاریخ")
            text = re.sub(pattern, " ", text, flags=re.I)

    # A bare weekday deliberately produces a warning: it is predictably nearest upcoming day,
    # but users should see that interpretation before saving.
    weekday_hit: tuple[int, bool, bool] | None = None
    for word, weekday in _WEEKDAYS:
        rx = re.compile(
            rf"(?<!\w)(?P<prefix>این\s+|next\s+|this\s+)?{re.escape(word)}(?P<suffix>\s+(?:هفته\s*(?:بعد|آینده)|week))?(?!\w)",
            re.I,
        )
        match = rx.search(text)
        if not match:
            continue
        explicit_next = bool(match.group("suffix")) or (match.group("prefix") or "").strip().lower() == "next"
        explicit_this = (match.group("prefix") or "").strip() in {"این", "this"}
        weekday_hit = (weekday, explicit_next, explicit_this)
        _set_once(result, "date", _weekday_date(today, weekday, next_week=explicit_next), "تاریخ")
        text = text[:match.start()] + " " + text[match.end():]
        if not explicit_next and not explicit_this:
            result.warnings.append("روز هفته بدون «این/هفته بعد» به نزدیک‌ترین روز آینده تعبیر شد؛ پیش‌نمایش را بررسی کنید.")
        break

    # ``09:30`` is unambiguously a time; a bare ``9`` never is.  Persian uses «ساعت»،
    # English uses ``at`` so ordinary title numbers are left untouched.
    time_rx = re.compile(r"(?<!\w)(?:ساعت\s*|at\s+)(\d{1,2}(?::\d{1,2})?)(?!\w)|(?<!\d)(\d{1,2}:\d{2})(?!\d)", re.I)

    def take_time(match: re.Match[str]) -> str:
        raw = match.group(1) or match.group(2)
        parsed = _parse_time(raw, result)
        if parsed is not None:
            _set_once(result, "start_time", parsed, "ساعت شروع")
            return " "
        return match.group(0)

    text = time_rx.sub(take_time, text)

    duration_rx = re.compile(
        r"(?<!\w)(?:برای|به\s*مدت|for)\s*(\d+)\s*(دقیقه|دقیقه‌ای|min(?:ute)?s?|ساعت|hours?|hrs?)(?!\w)",
        re.I,
    )

    def take_duration(match: re.Match[str]) -> str:
        amount, unit = int(match.group(1)), match.group(2).lower()
        minutes = amount * 60 if unit.startswith(("ساعت", "hour", "hr")) else amount
        if not 1 <= minutes <= 24 * 60:
            result.errors.append("مدت باید بین ۱ دقیقه و ۲۴ ساعت باشد.")
            return match.group(0)
        if result.start_time is None:
            result.warnings.append("مدت زمان پیدا شد اما ساعت شروعی نبود؛ ساعت شروع را در پیش‌نمایش وارد کنید.")
        else:
            start = dt.datetime.combine(today, result.start_time)
            end = start + dt.timedelta(minutes=minutes)
            if end.date() != start.date():
                result.errors.append("مدت انتخاب‌شده از نیمه‌شب می‌گذرد؛ ساعت پایان را دستی تعیین کنید.")
            else:
                result.end_time = end.time()
        return " "

    text = duration_rx.sub(take_duration, text)

    priority_rules = (
        ("high", r"(?<!\w)(?:اولویت\s*بالا|فوری|high\s+priority|urgent)(?!\w)"),
        ("low", r"(?<!\w)(?:اولویت\s*کم|کم\s*اولویت|low\s+priority)(?!\w)"),
        ("medium", r"(?<!\w)(?:اولویت\s*متوسط|medium\s+priority)(?!\w)"),
    )
    priority_hits = []
    for priority, pattern in priority_rules:
        if re.search(pattern, text, flags=re.I):
            priority_hits.append(priority)
            text = re.sub(pattern, " ", text, flags=re.I)
    if len(set(priority_hits)) > 1:
        result.errors.append("بیش از یک اولویت در متن پیدا شد؛ یک اولویت را در پیش‌نمایش انتخاب کنید.")
    elif priority_hits:
        result.priority = priority_hits[0]

    tags: list[str] = []
    def take_tag(match: re.Match[str]) -> str:
        tag = match.group(1).strip("_-").lower()
        if tag and tag not in tags:
            tags.append(tag)
        return " "

    text = re.sub(r"(?<!\w)#([\w\-\u0600-\u06ff]{1,40})", take_tag, text, flags=re.UNICODE)
    result.tags = tags

    if result.date is None:
        result.date = today
    if result.recurrence == "weekly":
        if weekday_hit:
            result.weekly_weekday = weekday_hit[0]
        else:
            result.weekly_weekday = to_jalali(result.date).weekday()
            result.warnings.append("تکرار هفتگی بدون روز مشخص بود؛ روزِ تاریخ انتخاب‌شده برای آن در نظر گرفته شد.")

    result.title = _clean_title(text)
    if not result.title:
        result.errors.append("عنوان تسک باقی نماند؛ عنوانی برای کار بنویسید.")
    return result
