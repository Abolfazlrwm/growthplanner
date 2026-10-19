"""Day-list + HTMX status-change views for tasks, all scoped to request.user."""
import datetime as dt
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.habits.services import sync_habits_for_date
from apps.journal.forms import DayNoteForm
from apps.journal.models import DayNote

from .forms import FailTaskForm, SubTaskForm, TaskDetailForm, TaskForm
from .ics import build_ics
from .models import OPEN_STATUSES, SubTask, Task, TaskStatus


def _get_date(request):
    raw = request.GET.get("date") or request.POST.get("date")
    if raw:
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


@login_required
def task_list(request):
    """Tasks for one day (default: today), with a form to add a new one."""
    date = _get_date(request)
    sync_habits_for_date(request.user, date)
    tasks = Task.objects.filter(user=request.user, date=date).select_related("goal").prefetch_related("tags").priority_ordered()
    form = TaskForm(user=request.user, initial={"date": date})
    note = DayNote.objects.filter(user=request.user, date=date).first()
    note_form = DayNoteForm(instance=note or DayNote(user=request.user, date=date))
    return render(
        request, "tasks/list.html",
        {
            "tasks": tasks, "form": form, "date": date,
            "is_today": date == timezone.localdate(), "note_form": note_form,
        },
    )


@login_required
@require_POST
def task_create(request):
    form = TaskForm(request.POST, user=request.user)
    if form.is_valid():
        task = form.save(commit=False)
        task.user = request.user
        task.save()
        return render(request, "tasks/_task_row.html", {"task": task})
    # Re-render just the form so HTMX can swap the errors in place.
    date = _get_date(request)
    return render(request, "tasks/_task_form.html", {"form": form, "date": date}, status=422)


@login_required
@require_POST
def task_set_status(request, pk, status):
    if status not in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE):
        return redirect("tasks:list")
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.status = status
    task.save(update_fields=["status"])
    return render(request, "tasks/_task_row.html", {"task": task})


@login_required
def task_fail(request, pk):
    """Small inline form to record why a task failed."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == "POST":
        form = FailTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.instance.status = TaskStatus.FAILED
            form.save()
            return render(request, "tasks/_task_row.html", {"task": task})
    else:
        form = FailTaskForm(instance=task)
    return render(request, "tasks/_task_fail_form.html", {"form": form, "task": task})


@login_required
@require_POST
def task_move(request, pk):
    """Move to tomorrow; the row disappears from today's list (hx-swap="delete")."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    try:
        task.move_to_tomorrow()
    except ValueError:
        return HttpResponse("Only unfinished tasks can be moved.", status=400)
    return render(request, "tasks/_empty.html")


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.delete()
    return render(request, "tasks/_empty.html")


@login_required
@require_POST
def task_duplicate(request, pk):
    """Make an independent copy of this task for tomorrow (e.g. a one-off repeat).

    Deliberately not linked to the original's habit (if any) — a habit already manages
    its own recurrence, so a manual duplicate is always a standalone, one-off task.
    """
    original = get_object_or_404(Task, pk=pk, user=request.user)
    new_task = Task.objects.create(
        user=request.user,
        title=original.title,
        goal=original.goal,
        date=original.date + dt.timedelta(days=1),
        start_time=original.start_time,
        end_time=original.end_time,
        priority=original.priority,
    )
    new_task.tags.set(original.tags.filter(user=request.user))
    SubTask.objects.bulk_create([
        SubTask(user=request.user, task=new_task, title=sub.title, position=sub.position)
        for sub in original.subtasks.filter(user=request.user)
    ])
    response = render(request, "tasks/_task_row.html", {"task": original})
    response["HX-Trigger"] = json.dumps({"toast": "یک کپی برای فردا ساخته شد ✅"})
    return response


@login_required
def task_search(request):
    """Search this user's tasks by title across every date, newest first."""
    query = request.GET.get("q", "").strip()
    results = []
    if query:
        results = list(
            Task.objects.filter(user=request.user, title__icontains=query)
            .select_related("goal").prefetch_related("tags")
            .order_by("-date")[:100]
        )
    return render(request, "tasks/search.html", {"query": query, "results": results})


@login_required
def task_detail(request, pk):
    """Edit one task and its private, owner-scoped checkable subtasks."""
    task = get_object_or_404(Task.objects.prefetch_related("tags", "subtasks"), pk=pk, user=request.user)
    original_date = task.date
    subtasks = task.subtasks.filter(user=request.user)
    form = TaskDetailForm(instance=task, user=request.user)
    subtask_form = SubTaskForm()

    if request.method == "POST":
        action = request.POST.get("action", "update")
        if action == "add_subtask":
            subtask_form = SubTaskForm(request.POST)
            if subtask_form.is_valid():
                subtask = subtask_form.save(commit=False)
                subtask.user = request.user
                subtask.task = task
                subtask.position = task.subtasks.count()
                subtask.full_clean()
                subtask.save()
                messages.success(request, "ریزکار اضافه شد.")
                return redirect("tasks:detail", pk=task.pk)
        elif action in {"toggle_subtask", "delete_subtask"}:
            subtask = get_object_or_404(
                SubTask, pk=request.POST.get("subtask_id"), task=task, user=request.user
            )
            if action == "toggle_subtask":
                subtask.is_completed = not subtask.is_completed
                subtask.save(update_fields=["is_completed"])
            else:
                subtask.delete()
            return redirect("tasks:detail", pk=task.pk)
        else:
            form = TaskDetailForm(request.POST, instance=task, user=request.user)
            if form.is_valid():
                if task.habit_id and form.cleaned_data["date"] != original_date:
                    form.add_error("date", "رخداد عادت را نمی‌شود جابه‌جا کرد؛ زمان‌بندی عادت را عوض کنید.")
                else:
                    form.save()
                    messages.success(request, "تغییرات تسک ذخیره شد.")
                    return redirect("tasks:detail", pk=task.pk)

    return render(request, "tasks/detail.html", {
        "task": task,
        "form": form,
        "subtask_form": subtask_form,
        "subtasks": subtasks,
    })


EXPORT_HORIZON_DAYS = 90


@login_required
def task_export_ics(request):
    """Download the next 90 days of tasks as a .ics file (import into any calendar app)."""
    today = timezone.localdate()
    tasks = (
        Task.objects.filter(user=request.user, date__range=(today, today + dt.timedelta(days=EXPORT_HORIZON_DAYS)))
        .select_related("goal")
        .order_by("date", "start_time")
    )
    content = build_ics(tasks)
    response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="tasks.ics"'
    return response


RESCHEDULE_MAX_DAYS = 3650  # keep typos like year 3026 out of the calendar


@login_required
@require_POST
def task_reschedule(request, pk):
    """Change an open task's day (date picker, week-board drag & drop).

    Habit tasks are tied to their day by the habit schedule, and finished tasks are
    history, so both are refused. Returns the refreshed row for the client to place.
    """
    task = get_object_or_404(Task, pk=pk, user=request.user)
    try:
        new_date = dt.date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        return HttpResponse("تاریخ نامعتبر است.", status=400, content_type="text/plain; charset=utf-8")
    if abs((new_date - timezone.localdate()).days) > RESCHEDULE_MAX_DAYS:
        return HttpResponse("این تاریخ خیلی دور است.", status=400, content_type="text/plain; charset=utf-8")
    if task.habit_id:
        return HttpResponse(
            "تسک‌های عادت را نمی‌شود جابه‌جا کرد؛ زمان‌بندی‌شان را از خود عادت عوض کن.",
            status=400, content_type="text/plain; charset=utf-8",
        )
    if task.status not in OPEN_STATUSES:
        return HttpResponse("فقط تسک‌های ناتمام قابل جابه‌جایی‌اند.", status=400, content_type="text/plain; charset=utf-8")
    task.date = new_date
    task.save(update_fields=["date"])
    return render(request, "tasks/_task_row.html", {"task": task})
