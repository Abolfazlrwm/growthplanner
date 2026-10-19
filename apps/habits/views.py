"""CRUD + toggle-active views for habits (recurring task templates)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import UserOwnedMixin

from .forms import HabitForm
from .models import Habit
from .services import habit_best_streak, habit_history, habit_streak, reconcile_future_occurrences


class HabitListView(UserOwnedMixin, ListView):
    model = Habit
    template_name = "habits/list.html"
    context_object_name = "habits"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        # Attached directly to each instance so the template can just read `habit.streak`.
        for habit in context["habits"]:
            habit.streak = habit_streak(habit, today)
            habit.best_streak = habit_best_streak(habit)
        return context


class HabitFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class HabitCreateView(HabitFormMixin, UserOwnedMixin, CreateView):
    model = Habit
    form_class = HabitForm
    template_name = "habits/form.html"
    success_url = reverse_lazy("habits:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "عادت جدید ساخته شد ✅")
        return response


class HabitUpdateView(HabitFormMixin, UserOwnedMixin, UpdateView):
    model = Habit
    form_class = HabitForm
    template_name = "habits/form.html"
    success_url = reverse_lazy("habits:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        reconcile_future_occurrences(self.object)
        messages.success(self.request, "تغییرات عادت ذخیره شد.")
        return response


class HabitDeleteView(UserOwnedMixin, DeleteView):
    model = Habit
    template_name = "habits/confirm_delete.html"
    success_url = reverse_lazy("habits:list")

    def form_valid(self, form):
        messages.success(self.request, "عادت حذف شد.")
        return super().form_valid(form)


@login_required
@require_POST
def habit_toggle_active(request, pk):
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    habit.active = not habit.active
    habit.save(update_fields=["active"])
    reconcile_future_occurrences(habit)
    messages.success(request, "عادت فعال شد." if habit.active else "عادت غیرفعال شد.")
    return redirect("habits:list")


@login_required
def habit_detail(request, pk):
    """One habit: streaks, a 12-week history grid and how it goes on each weekday."""
    habit = get_object_or_404(Habit, pk=pk, user=request.user)
    today = timezone.localdate()
    habit.streak = habit_streak(habit, today)
    habit.best_streak = habit_best_streak(habit)
    return render(request, "habits/detail.html", {"habit": habit, "history": habit_history(habit, today)})
