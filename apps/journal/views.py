"""Upsert view for the one-note-per-day journal entry (HTMX partial)."""
import datetime as dt

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DayNoteForm
from .models import DayNote


def _parse_date(raw):
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise Http404("تاریخ نامعتبر است.")


@login_required
@require_POST
def save_note(request, date):
    date_obj = _parse_date(date)
    note, _ = DayNote.objects.get_or_create(user=request.user, date=date_obj)
    form = DayNoteForm(request.POST, instance=note)
    saved = form.is_valid()
    if saved:
        form.save()
    return render(
        request, "journal/_note_form.html",
        {"form": form, "date": date_obj, "saved": saved, "is_today": date_obj == timezone.localdate()},
    )


NOTES_PER_PAGE = 15
MOOD_DAYS = 30


@login_required
def note_list(request):
    """Journal archive: every day with a note or mood, newest first, searchable, plus a 30-day mood strip."""
    query = request.GET.get("q", "").strip()
    notes = DayNote.objects.filter(user=request.user).exclude(text="", mood__isnull=True)
    if query:
        notes = notes.filter(text__icontains=query)
    page = Paginator(notes.order_by("-date"), NOTES_PER_PAGE).get_page(request.GET.get("page"))

    today = timezone.localdate()
    since = today - dt.timedelta(days=MOOD_DAYS - 1)
    moods = dict(
        DayNote.objects.filter(user=request.user, date__range=(since, today), mood__isnull=False)
        .values_list("date", "mood")
    )
    strip = []
    for i in range(MOOD_DAYS):
        day = since + dt.timedelta(days=i)
        strip.append({"date": day, "mood": moods.get(day)})
    values = [m for m in moods.values()]
    return render(request, "journal/list.html", {
        "page": page,
        "query": query,
        "strip": strip,
        "mood_avg": round(sum(values) / len(values), 1) if values else None,
        "mood_days": len(values),
        "total_notes": DayNote.objects.filter(user=request.user).exclude(text="", mood__isnull=True).count(),
    })
