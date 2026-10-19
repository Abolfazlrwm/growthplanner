"""Template filters that expose utils/jalali.py to templates."""
import datetime as dt

from django import template

from utils.jalali import format_jalali

register = template.Library()


@register.filter
def jalali(value, mode=""):
    if not isinstance(value, (dt.date, dt.datetime)):
        return value
    return format_jalali(value, with_weekday=(mode == "withweekday"))


@register.filter
def add_days(value, days):
    if not isinstance(value, dt.date):
        return value
    return value + dt.timedelta(days=int(days))
