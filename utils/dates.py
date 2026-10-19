"""Display helpers that follow the active UI language.

Persian UI  -> Jalali dates, weeks start on Saturday, Friday is the weekend.
English UI  -> Gregorian dates, weeks start on Monday, Saturday/Sunday are the weekend.

The stored data never changes (the database keeps Gregorian dates); only how it is shown and
where a "week" begins.
"""
import datetime as dt

from django.utils import translation

from .jalali import JALALI_MONTHS, JALALI_WEEKDAYS, format_jalali, to_jalali, to_persian_digits

EN_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December")
EN_MONTHS_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")  # date.weekday()
EN_WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def is_english() -> bool:
    return (translation.get_language() or "fa").split("-")[0].lower() == "en"


def week_offset(day: dt.date) -> int:
    """Days since the first day of `day`'s week (Saturday in Persian, Monday in English)."""
    return day.weekday() if is_english() else to_jalali(day).weekday()


def week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=week_offset(day))


def is_weekend(day: dt.date) -> bool:
    return day.weekday() in (5, 6) if is_english() else day.weekday() == 4  # Friday


def weekday_name(day: dt.date) -> str:
    return EN_WEEKDAYS[day.weekday()] if is_english() else JALALI_WEEKDAYS[to_jalali(day).weekday()]


def day_number(day: dt.date) -> str:
    return str(day.day) if is_english() else to_persian_digits(to_jalali(day).day)


def month_key(day: dt.date) -> int:
    """A value that changes when the (calendar-appropriate) month changes."""
    return day.month if is_english() else to_jalali(day).month


def month_label(day: dt.date) -> str:
    return EN_MONTHS_SHORT[day.month - 1] if is_english() else JALALI_MONTHS[to_jalali(day).month - 1]


def short_date(day: dt.date) -> str:
    """'Oct 5' / '۱۳ مهر'."""
    if is_english():
        return f"{EN_MONTHS_SHORT[day.month - 1]} {day.day}"
    j = to_jalali(day)
    return f"{to_persian_digits(j.day)} {JALALI_MONTHS[j.month - 1]}"


def full_date(day: dt.date, with_weekday: bool = True) -> str:
    """'Mon, Oct 5, 2026' / 'دوشنبه ۱۳ مهر ۱۴۰۵'."""
    if isinstance(day, dt.datetime):
        day = day.date()
    if is_english():
        text = f"{EN_MONTHS_SHORT[day.month - 1]} {day.day}, {day.year}"
        return f"{EN_WEEKDAYS_SHORT[day.weekday()]}, {text}" if with_weekday else text
    return format_jalali(day, with_weekday=with_weekday)


def year_text(day: dt.date) -> str:
    return str(day.year) if is_english() else to_persian_digits(to_jalali(day).year)


def week_range_text(start: dt.date, end: dt.date) -> str:
    if is_english():
        return f"{short_date(start)} – {short_date(end)}, {end.year}"
    return f"{short_date(start)} تا {short_date(end)} {year_text(end)}"
