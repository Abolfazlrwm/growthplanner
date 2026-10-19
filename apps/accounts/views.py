"""Registration, account settings, data export, and account deletion.

(login/logout/password reset/password change use Django's built-in views, wired up in urls.py)
"""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, TemplateView
from django.conf import settings
from django.views.decorators.http import require_POST

from apps.goals.models import Goal
from apps.habits.models import Habit
from apps.journal.models import DayNote
from apps.tasks.models import Task

from .forms import RegistrationForm, ProfileForm


class RegisterView(CreateView):
    """Create an account and log the new user in immediately."""

    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("core:home")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class AccountSettingsView(LoginRequiredMixin, TemplateView):
    """Profile hub: change password, export data, or delete the account."""

    template_name = "accounts/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile_form"] = ProfileForm(instance=self.request.user)
        context["password_reset_enabled"] = settings.PASSWORD_RESET_ENABLED
        return context


@login_required
@require_POST
def update_profile(request):
    form = ProfileForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "پروفایل ذخیره شد." if getattr(request, "ui_lang", "fa") == "fa" else "Profile saved.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"profile_form": form, "password_reset_enabled": settings.PASSWORD_RESET_ENABLED}, status=400)


@login_required
def export_data(request):
    """Download everything the user has entered, as one JSON file (goals/tasks/habits/notes)."""
    user = request.user
    from apps.tasks.models import FocusSession, Tag, SubTask
    from apps.goals.models import Milestone
    from apps.assistant.models import AssistantConversation, AssistantMessage, AssistantDraft
    data = {
        "schema_version": "2.0",
        "username": user.get_username(),
        "profile": {"first_name": user.first_name, "last_name": user.last_name, "email": user.email, "date_joined": user.date_joined},
        "exported_at": timezone.now(),
        "goals": list(
            Goal.objects.filter(user=user).values(
                "id", "title", "description", "deadline", "status", "created_at"
            )
        ),
        "tasks": list(
            Task.objects.filter(user=user).values(
                "id", "title", "date", "start_time", "end_time", "status", "priority", "fail_reason", "goal_id", "habit_id", "goal__title", "created_at"
            )
        ),
        "habits": list(
            Habit.objects.filter(user=user).values(
                "id", "title", "weekdays", "starts_on", "start_time", "end_time", "priority", "active", "goal_id", "goal__title"
            )
        ),
        "notes": list(DayNote.objects.filter(user=user).values("date", "text", "mood")),
        "focus_sessions": list(FocusSession.objects.filter(user=user).values("id", "task_id", "date", "minutes", "created_at")),
        "tags": list(Tag.objects.filter(user=user).values("id", "name")),
        "task_tags": list(Task.tags.through.objects.filter(task__user=user).values("task_id", "tag_id")),
        "habit_tags": list(Habit.tags.through.objects.filter(habit__user=user).values("habit_id", "tag_id")),
        "subtasks": list(SubTask.objects.filter(task__user=user).values()),
        "milestones": list(Milestone.objects.filter(goal__user=user).values()),
        "assistant_conversations": list(AssistantConversation.objects.filter(user=user).values("id", "created_at", "updated_at")),
        "assistant_messages": list(AssistantMessage.objects.filter(conversation__user=user).values("id", "conversation_id", "role", "content", "created_at")),
        "assistant_drafts": list(AssistantDraft.objects.filter(user=user).values("id", "conversation_id", "payload", "accepted_at", "created_task_id", "created_at")),
    }
    response = JsonResponse(data, encoder=DjangoJSONEncoder, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = 'attachment; filename="growthplanner-data-v2.json"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def delete_account(request):
    """Confirm-then-delete the account and everything owned by it (cascades via FKs)."""
    if request.method == "POST":
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, "حساب کاربری‌ات با موفقیت حذف شد.")
        return redirect("accounts:login")
    return render(request, "accounts/confirm_delete_account.html")


from django.contrib.auth.views import PasswordResetView


class ManagedPasswordResetView(PasswordResetView):
    """Do not pretend that production console output is delivered email."""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['password_reset_disabled'] = not settings.PASSWORD_RESET_ENABLED
        return context

    def post(self, request, *args, **kwargs):
        if not settings.PASSWORD_RESET_ENABLED:
            return self.render_to_response(self.get_context_data(), status=503)
        return super().post(request, *args, **kwargs)
