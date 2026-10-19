"""Template filters that expose utils/jalali.py to templates."""
import datetime as dt

from django import template

from utils.dates import full_date
from utils.jalali import to_persian_digits

register = template.Library()


@register.filter
def jalali(value, mode=""):
    if not isinstance(value, (dt.date, dt.datetime)):
        return value
    return full_date(value, with_weekday=(mode == "withweekday"))


@register.filter
def add_days(value, days):
    if not isinstance(value, dt.date):
        return value
    return value + dt.timedelta(days=int(days))


@register.filter
def fa(value):
    """Show any number (or text containing digits) with Persian digits: 12 -> ۱۲."""
    if value is None:
        return ""
    return to_persian_digits(value)


@register.filter
def duration(minutes):
    """90 -> '۱ ساعت و ۳۰ دقیقه', 45 -> '۴۵ دقیقه', 120 -> '۲ ساعت' (Persian digits)."""
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(total, 60)
    if hours and rest:
        text = f"{hours} ساعت و {rest} دقیقه"
    elif hours:
        text = f"{hours} ساعت"
    else:
        text = f"{rest} دقیقه"
    return to_persian_digits(text)
