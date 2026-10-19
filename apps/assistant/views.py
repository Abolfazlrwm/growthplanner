"""Authenticated web endpoints for the opt-in planning assistant."""
import datetime as dt
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.goals.models import Goal
from apps.tasks.models import Task

from .models import AssistantConversation, AssistantDraft, AssistantMessage
from .services import (
    ALLOWED_MODES,
    MAX_MESSAGE_CHARS,
    AssistantServiceError,
    ProviderOutputInvalid,
    UsageLimited,
    build_messages,
    call_provider,
    consume_usage_slot,
    conversation_history,
    validate_output,
)


COPY = {
    "fa": {
        "bad_request": "درخواست قابل پردازش نیست. لطفاً پیام را کوتاه‌تر و دوباره امتحان کن.",
        "rate_limited": "برای حفظ کیفیت، فعلاً سقف درخواست این ساعت پر شده است. کمی بعد دوباره امتحان کن.",
        "timeout": "پاسخ دستیار بیشتر از حد معمول طول کشید. پیام شما حفظ شده؛ دوباره امتحان کن.",
        "unavailable": "دستیار فعلاً در دسترس نیست. لطفاً کمی بعد دوباره امتحان کن.",
        "invalid_output": "پاسخ قابل‌اعتماد از دستیار دریافت نشد. چیزی ایجاد نشده است؛ دوباره امتحان کن.",
        "draft_missing": "این پیشنهاد پیدا نشد یا به حساب شما تعلق ندارد.",
        "draft_invalid": "این پیشنهاد دیگر معتبر نیست؛ هیچ تسکی ساخته نشد.",
    },
    "en": {
        "bad_request": "We could not process that request. Please shorten it and try again.",
        "rate_limited": "The hourly assistant limit has been reached. Please try again later.",
        "timeout": "The assistant took too long. Your message was kept; please retry.",
        "unavailable": "The assistant is temporarily unavailable. Please try again later.",
        "invalid_output": "The assistant returned an unusable response. Nothing was created; please retry.",
        "draft_missing": "That suggestion was not found or does not belong to your account.",
        "draft_invalid": "That suggestion is no longer valid; no task was created.",
    },
}


def _language(request) -> str:
    return "en" if getattr(request, "ui_lang", "fa") == "en" else "fa"


def _message(request, code: str) -> str:
    return COPY[_language(request)][code]


def _json_body(request) -> dict:
    if request.content_type and request.content_type.split(";", 1)[0] == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST.dict()


def _conversation_for_user(user, raw_token: object) -> AssistantConversation | None:
    if not raw_token:
        return None
    if not isinstance(raw_token, str):
        raise Http404
    try:
        token = uuid.UUID(raw_token)
    except (ValueError, AttributeError):
        raise Http404
    try:
        return AssistantConversation.objects.get(token=token, user=user)
    except AssistantConversation.DoesNotExist:
        raise Http404 from None


def _public_suggestion(draft: AssistantDraft) -> dict:
    return {"draft_id": str(draft.token), **draft.payload}


@login_required
@require_GET
def index(request):
    """Render one user's latest thread; the browser never receives other threads."""
    conversation = AssistantConversation.objects.filter(user=request.user).first()
    messages = []
    if conversation:
        messages = conversation.messages.all()[:40]
    return render(request, "assistant/index.html", {"conversation": conversation, "messages": messages})


@login_required
@require_POST
def chat(request):
    payload = _json_body(request)
    message = payload.get("message", "")
    mode = payload.get("mode", "general")
    share_metadata = payload.get("share_metadata") is True or payload.get("share_metadata") == "true"
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > MAX_MESSAGE_CHARS:
        return JsonResponse({"error": _message(request, "bad_request")}, status=400)
    if not isinstance(mode, str) or mode not in ALLOWED_MODES:
        return JsonResponse({"error": _message(request, "bad_request")}, status=400)

    try:
        conversation = _conversation_for_user(request.user, payload.get("conversation_id"))
    except Http404:
        return JsonResponse({"error": _message(request, "bad_request")}, status=404)
    if conversation is None:
        conversation = AssistantConversation.objects.create(user=request.user)

    try:
        consume_usage_slot(request.user)
        messages = build_messages(
            message=message.strip(),
            mode=mode,
            history=conversation_history(conversation),
            share_metadata=share_metadata,
            user=request.user,
        )
        output = validate_output(call_provider(messages), user=request.user)
    except UsageLimited:
        return JsonResponse({"error": _message(request, "rate_limited"), "code": "rate_limited"}, status=429)
    except AssistantServiceError as exc:
        return JsonResponse({"error": _message(request, exc.code), "code": exc.code}, status=503)
    except Exception:
        # Do not let upstream body text, credentials, or implementation details reach users.
        return JsonResponse({"error": _message(request, "unavailable"), "code": "unavailable"}, status=503)

    with transaction.atomic():
        AssistantMessage.objects.create(
            conversation=conversation, role=AssistantMessage.Role.USER, content=message.strip()
        )
        AssistantMessage.objects.create(
            conversation=conversation, role=AssistantMessage.Role.ASSISTANT, content=output.answer
        )
        drafts = [
            AssistantDraft.objects.create(
                user=request.user, conversation=conversation, payload=suggestion.as_dict()
            )
            for suggestion in output.suggestions
        ]
        # Makes the latest-thread ordering correct even if no model field otherwise changed.
        AssistantConversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())

    return JsonResponse(
        {
            "conversation_id": str(conversation.token),
            "answer": output.answer,
            "suggestions": [_public_suggestion(draft) for draft in drafts],
        }
    )


@login_required
@require_POST
def accept_draft(request):
    """Create exactly one task after a user confirms a server-validated opaque draft."""
    payload = _json_body(request)
    raw_token = payload.get("draft_id")
    try:
        token = uuid.UUID(raw_token) if isinstance(raw_token, str) else None
    except ValueError:
        token = None
    if token is None:
        return JsonResponse({"error": _message(request, "draft_missing")}, status=404)

    with transaction.atomic():
        try:
            draft = AssistantDraft.objects.select_for_update().get(token=token, user=request.user)
        except AssistantDraft.DoesNotExist:
            return JsonResponse({"error": _message(request, "draft_missing")}, status=404)
        if draft.accepted_at and not draft.created_task_id:
            return JsonResponse({"accepted": True, "already_accepted": True, "task": None})
        if draft.created_task_id:
            task = draft.created_task
            return JsonResponse(
                {
                    "accepted": True,
                    "already_accepted": True,
                    "task": {"id": task.id, "title": task.title, "date": task.date.isoformat()},
                }
            )
        try:
            # Revalidate from stored JSON. This also catches stale/deleted/foreign goals.
            suggestion = validate_output(
                {"answer": "confirmed", "suggestions": [draft.payload]}, user=request.user
            ).suggestions[0]
            goal = None
            if suggestion.goal_id is not None:
                goal = Goal.objects.get(pk=suggestion.goal_id, user=request.user)
            task = Task(
                user=request.user,
                goal=goal,
                title=suggestion.title,
                date=dt.date.fromisoformat(suggestion.date),
                start_time=dt.time.fromisoformat(suggestion.start_time) if suggestion.start_time else None,
                end_time=dt.time.fromisoformat(suggestion.end_time) if suggestion.end_time else None,
                priority=suggestion.priority,
            )
            task.full_clean()
            task.save()
        except (ProviderOutputInvalid, Goal.DoesNotExist, ValidationError, ValueError):
            return JsonResponse({"error": _message(request, "draft_invalid")}, status=422)
        draft.created_task = task
        draft.accepted_at = timezone.now()
        draft.save(update_fields=["created_task", "accepted_at"])

    return JsonResponse(
        {
            "accepted": True,
            "already_accepted": False,
            "task": {"id": task.id, "title": task.title, "date": task.date.isoformat()},
        },
        status=201,
    )


@login_required
@require_POST
def clear_history(request):
    """Delete only the requesting user's selected thread or all of their history."""
    payload = _json_body(request)
    raw_token = payload.get("conversation_id")
    queryset = AssistantConversation.objects.filter(user=request.user)
    if raw_token:
        try:
            token = uuid.UUID(raw_token) if isinstance(raw_token, str) else None
        except ValueError:
            token = None
        if token is None:
            return JsonResponse({"error": _message(request, "bad_request")}, status=400)
        queryset = queryset.filter(token=token)
    AssistantDraft.objects.filter(user=request.user, conversation__in=queryset).delete()
    deleted, _ = queryset.delete()
    return JsonResponse({"cleared": True, "deleted": deleted})
