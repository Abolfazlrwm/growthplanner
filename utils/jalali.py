"""Gregorian <-> Jalali helpers, plus a Saturday-first month grid for the calendar."""
import datetime as dt

import jdatetime
from django.utils import timezone

JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
# jdatetime weekday(): Saturday = 0 ... Friday = 6
JALALI_WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
FRIDAY_WEEKDAY = 6
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_jalali(value: dt.date) -> jdatetime.date:
    """Convert a date or datetime (aware datetimes use the current timezone)."""
    if isinstance(value, dt.datetime):  # check first: datetime is a date subclass
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        value = value.date()
    return jdatetime.date.fromgregorian(date=value)


def format_jalali(value: dt.date, with_weekday: bool = True, persian_digits: bool = True) -> str:
    """Return e.g. 'پنجشنبه ۲ مهر ۱۴۰۵'."""
    j = to_jalali(value)
    text = f"{j.day} {JALALI_MONTHS[j.month - 1]} {j.year}"
    if with_weekday:
        text = f"{JALALI_WEEKDAYS[j.weekday()]} {text}"
    return text.translate(_PERSIAN_DIGITS) if persian_digits else text


def to_persian_digits(value) -> str:
    return str(value).translate(_PERSIAN_DIGITS)


def _add_jalali_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add `delta` months to a (jalali year, month), wrapping the year."""
    index = (month - 1) + delta
    return year + index // 12, index % 12 + 1


def jalali_month_bounds(year: int, month: int) -> tuple[dt.date, int]:
    """Return (first day of the jalali month as a Gregorian date, day count)."""
    first_greg = jdatetime.date(year, month, 1).togregorian()
    next_year, next_month = _add_jalali_month(year, month, 1)
    next_first_greg = jdatetime.date(next_year, next_month, 1).togregorian()
    return first_greg, (next_first_greg - first_greg).days


def build_month_grid(year: int, month: int) -> list[list[dict]]:
    """Weeks (Saturday -> Friday) of dicts: gregorian date, jalali day, in_month, is_holiday."""
    first_greg, day_count = jalali_month_bounds(year, month)
    start_weekday = to_jalali(first_greg).weekday()  # 0 = Saturday
    grid_start = first_greg - dt.timedelta(days=start_weekday)

    last_greg = first_greg + dt.timedelta(days=day_count - 1)
    end_weekday = to_jalali(last_greg).weekday()
    grid_end = last_greg + dt.timedelta(days=FRIDAY_WEEKDAY - end_weekday)

    weeks, week, day = [], [], grid_start
    while day <= grid_end:
        j = to_jalali(day)
        week.append({
            "gregorian": day,
            "jalali_day": to_persian_digits(j.day),
            "in_month": j.year == year and j.month == month,
            "is_holiday": j.weekday() == FRIDAY_WEEKDAY,
        })
        if len(week) == 7:
            weeks.append(week)
            week = []
        day += dt.timedelta(days=1)
    return weeks


def prev_month(year: int, month: int) -> tuple[int, int]:
    return _add_jalali_month(year, month, -1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return _add_jalali_month(year, month, 1)
