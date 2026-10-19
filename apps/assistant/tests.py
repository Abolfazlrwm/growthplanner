import datetime as dt
import json
import os
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.goals.models import Goal
from apps.journal.models import DayNote
from apps.tasks.models import Task

from .models import AssistantDraft, AssistantUsageWindow


User = get_user_model()


@override_settings(ROOT_URLCONF="apps.assistant.test_urls")
class AssistantViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("assistant-ali", password="pass12345")
        cls.other = User.objects.create_user("assistant-sara", password="pass12345")
        cls.goal = Goal.objects.create(
            user=cls.user, title="هدف خودم", deadline=timezone.localdate() + dt.timedelta(days=30)
        )
        cls.other_goal = Goal.objects.create(
            user=cls.other, title="هدف خصوصی سارا", deadline=timezone.localdate() + dt.timedelta(days=30)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.chat_url = reverse("assistant:chat")
        self.accept_url = reverse("assistant:accept")

    def provider_response(self, payload):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
        return response

    def chat(self, **overrides):
        payload = {"message": "برای هفته‌ام کمک کن", "mode": "plan", "share_metadata": False}
        payload.update(overrides)
        return self.client.post(self.chat_url, data=json.dumps(payload), content_type="application/json")

    def good_output(self, suggestions=None):
        return {"answer": "یک قدم کوچک را امروز شروع کن.", "suggestions": suggestions or []}

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_task_goal_metadata_is_sent_only_after_explicit_consent(self, post):
        Task.objects.create(user=self.user, goal=self.goal, title="تسک خصوصی من", date=timezone.localdate())
        post.return_value = self.provider_response(self.good_output())
        self.assertEqual(self.chat(share_metadata=False).status_code, 200)
        first_payload = post.call_args.kwargs["json"]
        first_text = "\n".join(message["content"] for message in first_payload["messages"])
        self.assertNotIn("تسک خصوصی من", first_text)
        self.assertNotIn("هدف خودم", first_text)

        post.reset_mock()
        post.return_value = self.provider_response(self.good_output())
        self.assertEqual(self.chat(share_metadata=True).status_code, 200)
        second_payload = post.call_args.kwargs["json"]
        second_text = "\n".join(message["content"] for message in second_payload["messages"])
        self.assertIn("تسک خصوصی من", second_text)
        self.assertIn("هدف خودم", second_text)

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_journal_text_is_never_sent_even_when_context_is_opted_in(self, post):
        DayNote.objects.create(user=self.user, date=timezone.localdate(), text="راز دفترچه: هرگز ارسال نشود")
        post.return_value = self.provider_response(self.good_output())
        response = self.chat(share_metadata=True)
        self.assertEqual(response.status_code, 200)
        sent = "\n".join(item["content"] for item in post.call_args.kwargs["json"]["messages"])
        self.assertNotIn("راز دفترچه: هرگز ارسال نشود", sent)
        self.assertNotIn("DayNote", sent)

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_provider_foreign_goal_id_is_rejected_before_draft_creation(self, post):
        suggestion = {
            "title": "کار نباید ساخته شود",
            "date": timezone.localdate().isoformat(),
            "start_time": None,
            "end_time": None,
            "priority": "high",
            "goal_id": self.other_goal.id,
        }
        post.return_value = self.provider_response(self.good_output([suggestion]))
        response = self.chat()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "invalid_output")
        self.assertFalse(AssistantDraft.objects.filter(user=self.user).exists())

    @override_settings(ASSISTANT_CHAT_LIMIT=1)
    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_durable_user_throttle_rejects_second_request(self, post):
        post.return_value = self.provider_response(self.good_output())
        self.assertEqual(self.chat().status_code, 200)
        response = self.chat(message="یک پیام دوم")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "rate_limited")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(AssistantUsageWindow.objects.get(user=self.user).count, 1)

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_http_200_provider_error_is_safe_and_never_leaks_details(self, post):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"error": {"message": "provider secret diagnostic"}}
        post.return_value = response
        result = self.chat()
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("provider secret diagnostic", result.content.decode())
        self.assertNotIn("server-only", result.content.decode())

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post", side_effect=requests.Timeout)
    def test_provider_timeout_has_a_safe_retryable_response(self, post):
        response = self.chat()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "timeout")
        self.assertTrue(response.json()["error"])
        self.assertEqual(post.call_args.kwargs["timeout"], 35)

    @mock.patch.dict(os.environ, {"MANUS_API_URL": "https://ai.example", "MANUS_API_KEY": "server-only"}, clear=False)
    @mock.patch("apps.assistant.services.requests.post")
    def test_same_draft_can_be_accepted_twice_without_duplicate_task(self, post):
        suggestion = {
            "title": "قدم بعدی",
            "date": timezone.localdate().isoformat(),
            "start_time": "09:00",
            "end_time": "10:00",
            "priority": "medium",
            "goal_id": self.goal.id,
        }
        post.return_value = self.provider_response(self.good_output([suggestion]))
        draft_id = self.chat().json()["suggestions"][0]["draft_id"]
        first = self.client.post(self.accept_url, data=json.dumps({"draft_id": draft_id}), content_type="application/json")
        second = self.client.post(self.accept_url, data=json.dumps({"draft_id": draft_id}), content_type="application/json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["already_accepted"])
        self.assertEqual(Task.objects.filter(user=self.user, title="قدم بعدی").count(), 1)

    def test_cannot_accept_another_users_opaque_draft(self):
        draft = AssistantDraft.objects.create(
            user=self.other,
            payload={
                "title": "دست نزن",
                "date": timezone.localdate().isoformat(),
                "start_time": None,
                "end_time": None,
                "priority": "low",
                "goal_id": None,
            },
        )
        response = self.client.post(self.accept_url, data=json.dumps({"draft_id": str(draft.token)}), content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Task.objects.filter(user=self.user, title="دست نزن").exists())
