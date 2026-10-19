"""CRUD views for goals, each scoped to the logged-in user, plus filter/search."""
import datetime as dt
import math
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import UserOwnedMixin

from .forms import GoalForm, MilestoneForm
from apps.tasks.models import OPEN_STATUSES, TaskStatus
from utils.dates import short_date, week_start

from .models import Goal, GoalStatus, Milestone


class GoalListView(UserOwnedMixin, ListView):
    """Goal list with a status tab (active / archive / all) and a title/description search."""

    model = Goal
    template_name = "goals/list.html"
    context_object_name = "goals"

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get("status", "active")
        if status == "archive":
            qs = qs.exclude(status=GoalStatus.ACTIVE)
        elif status in GoalStatus.values:
            qs = qs.filter(status=status)
        # status == "all" (or anything unrecognized) leaves the queryset unfiltered.

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(description__icontains=query))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status"] = self.request.GET.get("status", "active")
        context["current_q"] = self.request.GET.get("q", "")
        context["statuses"] = [("active", "فعال"), ("archive", "آرشیو"), ("all", "همه")]
        return context


class GoalCreateView(LoginRequiredMixin, CreateView):
    model = Goal
    form_class = GoalForm
    template_name = "goals/form.html"
    success_url = reverse_lazy("goals:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "هدف جدید ساخته شد ✅")
        return response


class GoalUpdateView(UserOwnedMixin, UpdateView):
    model = Goal
    form_class = GoalForm
    template_name = "goals/form.html"
    success_url = reverse_lazy("goals:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "تغییرات هدف ذخیره شد.")
        return response


class GoalDeleteView(UserOwnedMixin, DeleteView):
    model = Goal
    template_name = "goals/confirm_delete.html"
    success_url = reverse_lazy("goals:list")

    def form_valid(self, form):
        messages.success(self.request, "هدف حذف شد.")
        return super().form_valid(form)


DETAIL_WEEKS = 8
DETAIL_DONE_LIMIT = 30


@login_required
def goal_detail(request, pk):
    """One goal: progress, deadline pace, its open tasks by day, recent wins and a weekly chart."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    today = timezone.localdate()
    tasks = list(goal.tasks.select_related("habit").order_by("date", "start_time", "id"))

    open_tasks = [t for t in tasks if t.status in OPEN_STATUSES]
    done_tasks = [t for t in tasks if t.status == TaskStatus.DONE]
    failed_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
    total = len(tasks)
    percent = round(len(done_tasks) * 100 / total) if total else 0

    days_left = (goal.deadline - today).days
    is_active = goal.status == GoalStatus.ACTIVE
    overdue = is_active and days_left < 0 and bool(open_tasks)
    needed_per_day = pace_count = pace_unit = None
    if is_active and open_tasks and days_left > 0:
        per_day = len(open_tasks) / days_left
        needed_per_day = round(per_day, 1)
        # Say it in the unit that reads naturally: "2 a day" or "2 a week", never "0.2 a day".
        if per_day >= 1:
            pace_count, pace_unit = math.ceil(per_day), "روز"
        else:
            pace_count, pace_unit = math.ceil(per_day * 7), "هفته"

    # Done tasks per jalali week (Saturday-first) for the last DETAIL_WEEKS weeks, oldest first.
    this_week_start = week_start(today)
    weeks = []
    for i in range(DETAIL_WEEKS - 1, -1, -1):
        start = this_week_start - dt.timedelta(days=7 * i)
        end = start + dt.timedelta(days=6)
        count = sum(1 for t in done_tasks if start <= t.date <= end)
        weeks.append({"start": start, "label": short_date(start), "count": count})
    peak = max((w["count"] for w in weeks), default=0)
    for w in weeks:
        w["percent"] = round(w["count"] * 100 / peak) if peak else 0

    groups = [{"date": day, "tasks": list(items)} for day, items in groupby(open_tasks, key=lambda t: t.date)]
    recent_done = sorted(done_tasks, key=lambda t: (t.date, t.id), reverse=True)[:DETAIL_DONE_LIMIT]

    return render(request, "goals/detail.html", {
        "goal": goal,
        "today": today,
        "groups": groups,
        "open_count": len(open_tasks),
        "done_count": len(done_tasks),
        "failed_count": failed_count,
        "total": total,
        "percent": percent,
        "days_left": days_left,
        "days_over": -days_left if days_left < 0 else 0,
        "is_active": is_active,
        "overdue": overdue,
        "needed_per_day": needed_per_day,
        "pace_count": pace_count,
        "pace_unit": pace_unit,
        "can_complete": is_active,
        "weeks": weeks,
        "has_week_data": peak > 0,
        "recent_done": recent_done,
        "habits": list(goal.habits.filter(active=True)),
        "milestones": goal.milestones.filter(user=request.user),
        "milestone_form": MilestoneForm(),
        "celebrate": request.GET.get("celebrate") == "1",
    })


@login_required
@require_POST
def goal_complete(request, pk):
    """Mark an active goal as completed, then show the goal page with a small celebration."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if goal.status == GoalStatus.ACTIVE:
        goal.status = GoalStatus.COMPLETED
        goal.save(update_fields=["status"])
        messages.success(request, f"آفرین! «{goal.title}» تکمیل شد.")
        return redirect(f"{reverse('goals:detail', args=[goal.pk])}?celebrate=1")
    return redirect("goals:detail", pk=goal.pk)


@login_required
@require_POST
def milestone_add(request, pk):
    """Add a checkpoint, always pinning both goal and milestone to request.user."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    form = MilestoneForm(request.POST)
    if form.is_valid():
        milestone = form.save(commit=False)
        milestone.user = request.user
        milestone.goal = goal
        milestone.position = goal.milestones.count()
        milestone.full_clean()
        milestone.save()
        messages.success(request, "نقطه عطف اضافه شد.")
    else:
        messages.error(request, "نقطه عطف ذخیره نشد؛ عنوان و تاریخ را بررسی کنید.")
    return redirect(f"{reverse('goals:detail', args=[goal.pk])}#milestones")


@login_required
@require_POST
def milestone_toggle(request, pk, milestone_pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    milestone = get_object_or_404(Milestone, pk=milestone_pk, goal=goal, user=request.user)
    milestone.is_completed = not milestone.is_completed
    milestone.completed_at = timezone.now() if milestone.is_completed else None
    milestone.save(update_fields=["is_completed", "completed_at"])
    return redirect(f"{reverse('goals:detail', args=[goal.pk])}#milestones")


@login_required
@require_POST
def milestone_delete(request, pk, milestone_pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    milestone = get_object_or_404(Milestone, pk=milestone_pk, goal=goal, user=request.user)
    milestone.delete()
    messages.success(request, "نقطه عطف حذف شد.")
    return redirect(f"{reverse('goals:detail', args=[goal.pk])}#milestones")
