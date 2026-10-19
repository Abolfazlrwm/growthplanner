"""Smart quick-add and board views kept separate from the legacy day-list views."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.habits.models import Habit
from apps.habits.services import sync_habits_for_date
from utils.jalali import JALALI_WEEKDAYS, to_jalali

from .forms import SmartTaskPreviewForm
from .models import Tag, Task, TaskPriority, TaskStatus
from .natural_language import parse_task_phrase


def _tags_for(user, raw_names: str) -> list[Tag]:
    """Find/create the user's normalised tags in one transaction."""
    names = SmartTaskPreviewForm.parse_tag_names(raw_names)
    found: list[Tag] = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(user=user, normalized_name=Tag.normalize(name), defaults={"name": name})
        found.append(tag)
    return found


@login_required
def smart_add(request):
    """Two-step offline quick add: parse -> editable preview -> explicit save."""
    if request.method == "GET":
        return render(request, "tasks/smart_add.html", {"phrase": "", "preview_form": None})

    intent = request.POST.get("intent", "preview")
    if intent == "preview":
        phrase = request.POST.get("phrase", "")
        parsed = parse_task_phrase(phrase)
        preview_token = signing.dumps({"user_id": request.user.pk, "phrase": " ".join(phrase.split()), "warnings": parsed.warnings}, salt="growthplanner.smart-preview.v1", compress=True)
        preview_form = SmartTaskPreviewForm(
            user=request.user, language=getattr(request, "ui_lang", "fa"), initial=parsed.initial()
        )
        return render(request, "tasks/smart_add.html", {
            "phrase": phrase,
            "parsed": parsed,
            "preview_form": preview_form,
            "preview_token": preview_token,
            "weekday_choices": enumerate(JALALI_WEEKDAYS),
        })

    preview_form = SmartTaskPreviewForm(
        request.POST, user=request.user, language=getattr(request, "ui_lang", "fa")
    )
    preview_token = request.POST.get("preview_token", "")
    parser_warnings = []
    try:
        state = signing.loads(preview_token, salt="growthplanner.smart-preview.v1", max_age=1800)
        if state["user_id"] != request.user.pk or state["phrase"] != " ".join(request.POST.get("phrase", "").split()):
            raise signing.BadSignature("Preview owner or phrase mismatch")
        parser_warnings = state["warnings"]
    except (signing.BadSignature, KeyError, TypeError):
        preview_form.add_error(None, "پیش‌نمایش نامعتبر یا منقضی شده است؛ دوباره پیش‌نمایش بگیر.")
    if parser_warnings and not request.POST.get("confirm_ambiguous"):
        preview_form.add_error("confirm_ambiguous", "برای ذخیره، تفسیرهای هشدار‌دار را تأیید کنید.")
    if preview_form.is_valid():
        with transaction.atomic():
            tags = _tags_for(request.user, preview_form.cleaned_data["tag_names"])
            recurrence = preview_form.cleaned_data["recurrence"]
            common = {
                "user": request.user,
                "title": preview_form.cleaned_data["title"],
                "goal": preview_form.cleaned_data.get("goal"),
                "date": preview_form.cleaned_data["date"],
                "start_time": preview_form.cleaned_data.get("start_time"),
                "end_time": preview_form.cleaned_data.get("end_time"),
                "priority": preview_form.cleaned_data["priority"],
            }
            if recurrence == "none":
                task = Task.objects.create(**common)
            else:
                weekdays = "" if recurrence == "daily" else str(preview_form.cleaned_data["weekly_weekday"])
                habit = Habit.objects.create(
                    user=request.user,
                    goal=common["goal"],
                    title=common["title"],
                    weekdays=weekdays,
                    start_time=common["start_time"],
                    end_time=common["end_time"],
                    priority=common["priority"],
                    starts_on=common["date"],
                )
                habit.tags.set(tags)
                # Generate only the explicitly chosen occurrence.  Existing lazy habit sync
                # creates future rows when their day is viewed; there is no unbounded write.
                sync_habits_for_date(request.user, common["date"])
                task = get_object_or_404(Task, user=request.user, habit=habit, date=common["date"])
                task.priority = common["priority"]
                task.save(update_fields=["priority"])
            task.tags.set(tags)
        messages.success(request, "Task saved." if getattr(request, "ui_lang", "fa") == "en" else "تسک ذخیره شد.")
        return redirect("tasks:detail", pk=task.pk)

    return render(request, "tasks/smart_add.html", {
        "phrase": request.POST.get("phrase", ""),
        "preview_form": preview_form,
        "parser_warnings": parser_warnings,
        "preview_token": preview_token,
        "weekday_choices": enumerate(JALALI_WEEKDAYS),
    }, status=422)


@login_required
def board(request):
    """An owner-scoped board of every dated task, with intentionally simple server filters."""
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    raw_tag = request.GET.get("tag", "")
    tasks = Task.objects.filter(user=request.user).select_related("goal").prefetch_related("tags", "subtasks")
    if query:
        tasks = tasks.filter(title__icontains=query)
    if status in TaskStatus.values:
        tasks = tasks.filter(status=status)
    if priority in TaskPriority.values:
        tasks = tasks.filter(priority=priority)
    if raw_tag.isdigit():
        tasks = tasks.filter(tags__id=int(raw_tag))
    tasks = list(tasks.order_by("date", "start_time", "id"))

    grouped = []
    by_date: dict[dt.date, list[Task]] = defaultdict(list)
    for task in tasks:
        by_date[task.date].append(task)
    for date, day_tasks in by_date.items():
        grouped.append({"date": date, "tasks": day_tasks})

    return render(request, "tasks/board.html", {
        "groups": grouped,
        "tasks_count": len(tasks),
        "query": query,
        "current_status": status,
        "current_priority": priority,
        "current_tag": raw_tag,
        "statuses": TaskStatus.choices,
        "priorities": TaskPriority.choices,
        "tags": Tag.objects.filter(user=request.user),
    })
