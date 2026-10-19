import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.habits.models import Habit
from apps.tasks.models import FocusSession, SubTask, Tag, Task, TaskStatus
from apps.tasks.natural_language import parse_task_phrase

User = get_user_model()


class NaturalLanguageParserTests(TestCase):
    def test_persian_digits_duration_priority_and_tag_are_deterministic(self):
        parsed = parse_task_phrase(
            "فردا ساعت ۹ گزارش را بنویس برای ۴۵ دقیقه #کار اولویت بالا",
            today=dt.date(2026, 3, 20),
        )
        self.assertEqual(parsed.title, "گزارش را بنویس")
        self.assertEqual(parsed.date, dt.date(2026, 3, 21))
        self.assertEqual(parsed.start_time, dt.time(9, 0))
        self.assertEqual(parsed.end_time, dt.time(9, 45))
        self.assertEqual(parsed.priority, "high")
        self.assertEqual(parsed.tags, ["کار"])
        self.assertFalse(parsed.errors)

    def test_iso_and_jalali_dates_are_unambiguous_by_year(self):
        iso = parse_task_phrase("Report 2026-04-05", today=dt.date(2026, 3, 20))
        jalali = parse_task_phrase("گزارش 1405/01/16", today=dt.date(2026, 3, 20))
        self.assertEqual(iso.date, dt.date(2026, 4, 5))
        self.assertEqual(jalali.date, dt.date(2026, 4, 5))

    def test_bare_weekday_requires_preview_confirmation_and_weekly_keeps_day(self):
        parsed = parse_task_phrase("مطالعه هفتگی دوشنبه", today=dt.date(2026, 3, 20))
        self.assertEqual(parsed.recurrence, "weekly")
        self.assertEqual(parsed.weekly_weekday, 2)  # Monday in the app's Saturday-first calendar
        self.assertTrue(parsed.warnings)
        self.assertFalse(parsed.errors)


class SmartTaskFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def smart_post(self, **overrides):
        data = {
            "intent": "save", "phrase": "", "parser_warnings": "", "title": "گزارش",
            "goal": "", "date": self.today.isoformat(), "start_time": "09:00", "end_time": "10:00",
            "priority": "high", "tag_names": "کار, فوری", "recurrence": "none", "weekly_weekday": "",
        }
        data.update(overrides)
        preview = self.client.post(reverse("tasks:smart_add"), {"intent": "preview", "phrase": data["phrase"]})
        data["preview_token"] = preview.context["preview_token"]
        return self.client.post(reverse("tasks:smart_add"), data)

    def test_preview_does_not_write_and_exposes_editable_parsed_fields(self):
        response = self.client.post(
            reverse("tasks:smart_add"),
            {"intent": "preview", "phrase": "فردا ساعت ۹ گزارش #کار اولویت بالا"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(response.context["preview_form"].initial["priority"], "high")
        self.assertEqual(response.context["preview_form"].initial["tag_names"], "کار")

    def test_smart_save_creates_private_tags_and_task(self):
        response = self.smart_post()
        self.assertRedirects(response, reverse("tasks:detail", args=[Task.objects.get().pk]))
        task = Task.objects.get(user=self.user)
        self.assertEqual(task.priority, "high")
        self.assertEqual(set(task.tags.values_list("name", flat=True)), {"کار", "فوری"})
        self.assertEqual(Tag.objects.get(name="کار").user, self.user)

    def test_daily_recurrence_creates_one_habit_and_only_selected_occurrence(self):
        response = self.smart_post(recurrence="daily", tag_names="کار")
        self.assertEqual(response.status_code, 302)
        habit = Habit.objects.get(user=self.user)
        task = Task.objects.get(user=self.user, habit=habit)
        self.assertEqual(Task.objects.filter(user=self.user, habit=habit).count(), 1)
        self.assertEqual(task.date, self.today)
        self.assertEqual(task.priority, "high")
        self.assertEqual(list(task.tags.values_list("name", flat=True)), ["کار"])

    def test_board_is_owner_scoped_and_filters_by_private_tag(self):
        tag = Tag.objects.create(user=self.user, name="work")
        mine = Task.objects.create(user=self.user, title="Report", date=self.today, status=TaskStatus.TODO)
        mine.tags.add(tag)
        Task.objects.create(user=self.other, title="Report", date=self.today)
        response = self.client.get(reverse("tasks:board"), {"q": "report", "tag": tag.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tasks_count"], 1)
        self.assertContains(response, "Report")

    def test_task_detail_adds_subtask_only_to_owned_task(self):
        task = Task.objects.create(user=self.user, title="Parent", date=self.today)
        response = self.client.post(reverse("tasks:detail", args=[task.pk]), {"action": "add_subtask", "title": "Step one"})
        self.assertEqual(response.status_code, 302)
        subtask = SubTask.objects.get(task=task)
        self.assertEqual(subtask.user, self.user)
        self.assertFalse(subtask.is_completed)
        response = self.client.post(
            reverse("tasks:detail", args=[task.pk]), {"action": "toggle_subtask", "subtask_id": subtask.pk}
        )
        self.assertEqual(response.status_code, 302)
        subtask.refresh_from_db()
        self.assertTrue(subtask.is_completed)

    def test_detail_and_model_guards_reject_other_users_related_data(self):
        other_task = Task.objects.create(user=self.other, title="Private", date=self.today)
        self.assertEqual(self.client.get(reverse("tasks:detail", args=[other_task.pk])).status_code, 404)
        foreign_habit = Habit.objects.create(user=self.other, title="Other habit")
        invalid = Task(user=self.user, habit=foreign_habit, title="x", date=self.today)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        invalid_session = FocusSession(user=self.user, task=other_task, minutes=25, date=self.today)
        with self.assertRaises(ValidationError):
            invalid_session.full_clean()

    def test_api_partial_time_update_returns_400_instead_of_db_integrity_error(self):
        task = Task.objects.create(
            user=self.user, title="Timed", date=self.today, start_time=dt.time(9, 0), end_time=dt.time(10, 0)
        )
        response = self.client.patch(
            f"/api/tasks/{task.pk}/", data=json.dumps({"start_time": "11:00"}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("end_time", response.json())

    def test_api_rejects_another_users_tag_and_returns_task_owner(self):
        other_tag = Tag.objects.create(user=self.other, name="private")
        response = self.client.post(
            "/api/tasks/",
            {"title": "x", "date": self.today.isoformat(), "tag_ids": [other_tag.pk]},
        )
        self.assertEqual(response.status_code, 400)
        task = Task.objects.create(user=self.user, title="visible", date=self.today)
        response = self.client.get(f"/api/tasks/{task.pk}/")
        self.assertEqual(response.json()["user"], self.user.pk)
