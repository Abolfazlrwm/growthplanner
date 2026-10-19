import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.goals.models import Goal
from apps.habits.models import Habit

from .ics import build_ics
from .models import Task, TaskStatus

User = get_user_model()


class TaskModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")

    def make_task(self, **kwargs):
        data = {"user": self.user, "title": "تسک تست", "date": dt.date(2026, 9, 24)}
        data.update(kwargs)
        return Task.objects.create(**data)

    def test_move_to_tomorrow_shifts_date_and_marks_moved(self):
        task = self.make_task()
        task.move_to_tomorrow()
        task.refresh_from_db()
        self.assertEqual(task.date, dt.date(2026, 9, 25))
        self.assertEqual(task.status, TaskStatus.MOVED)

    def test_move_to_tomorrow_crosses_month_boundary(self):
        task = self.make_task(date=dt.date(2026, 9, 30))
        task.move_to_tomorrow()
        self.assertEqual(task.date, dt.date(2026, 10, 1))

    def test_done_task_cannot_be_moved(self):
        task = self.make_task(status=TaskStatus.DONE)
        with self.assertRaises(ValueError):
            task.move_to_tomorrow()

    def test_moving_a_habit_task_detaches_it_from_the_habit(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        task = self.make_task(habit=habit)
        task.move_to_tomorrow()
        task.refresh_from_db()
        self.assertIsNone(task.habit)

    def test_moving_a_plain_task_leaves_habit_field_alone(self):
        task = self.make_task()  # no habit
        task.move_to_tomorrow()
        task.refresh_from_db()
        self.assertIsNone(task.habit)  # was already None; nothing broke

    def test_end_time_must_be_after_start_time(self):
        task = Task(user=self.user, title="x", date=dt.date(2026, 9, 24),
                     start_time=dt.time(10, 0), end_time=dt.time(9, 0))
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_database_rejects_bad_time_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_task(start_time=dt.time(10, 0), end_time=dt.time(9, 0))

    def test_goal_must_belong_to_same_user(self):
        goal = Goal.objects.create(user=self.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))
        task = Task(user=self.user, goal=goal, title="x", date=dt.date(2026, 9, 24))
        with self.assertRaises(ValidationError):
            task.full_clean()


class TaskViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def make_task(self, **kwargs):
        data = {"user": self.user, "title": "تسک", "date": self.today}
        data.update(kwargs)
        return Task.objects.create(**data)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("tasks:list")).status_code, 302)

    def test_list_defaults_to_today_and_only_own_tasks(self):
        mine = self.make_task()
        others = Task.objects.create(user=self.other, title="تسک سارا", date=self.today)
        response = self.client.get(reverse("tasks:list"))
        tasks = list(response.context["tasks"])
        self.assertIn(mine, tasks)
        self.assertNotIn(others, tasks)
        self.assertEqual(response.context["date"], self.today)

    def test_list_accepts_explicit_date(self):
        other_day = self.today + dt.timedelta(days=3)
        task = self.make_task(date=other_day)
        response = self.client.get(reverse("tasks:list"), {"date": other_day.isoformat()})
        self.assertEqual(list(response.context["tasks"]), [task])

    def test_create_task_via_htmx(self):
        response = self.client.post(
            reverse("tasks:create"),
            {"title": "تسک جدید", "goal": "", "date": self.today.isoformat(), "start_time": "", "end_time": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Task.objects.filter(user=self.user, title="تسک جدید").exists())

    def test_create_with_invalid_time_range_returns_422(self):
        response = self.client.post(
            reverse("tasks:create"),
            {"title": "بد", "goal": "", "date": self.today.isoformat(),
             "start_time": "10:00", "end_time": "09:00"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Task.objects.filter(title="بد").exists())

    def test_set_status_done(self):
        task = self.make_task(status=TaskStatus.TODO)
        response = self.client.post(reverse("tasks:set_status", args=[task.pk, "done"]))
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DONE)

    def test_fail_task_records_reason(self):
        task = self.make_task()
        response = self.client.post(reverse("tasks:fail", args=[task.pk]), {"fail_reason": "وقت نشد"})
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.fail_reason, "وقت نشد")

    def test_move_task_shifts_date(self):
        task = self.make_task()
        self.client.post(reverse("tasks:move", args=[task.pk]))
        task.refresh_from_db()
        self.assertEqual(task.date, self.today + dt.timedelta(days=1))
        self.assertEqual(task.status, TaskStatus.MOVED)

    def test_delete_task(self):
        task = self.make_task()
        self.client.post(reverse("tasks:delete", args=[task.pk]))
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_cannot_modify_other_users_task(self):
        task = Task.objects.create(user=self.other, title="تسک سارا", date=self.today)
        response = self.client.post(reverse("tasks:set_status", args=[task.pk, "done"]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("tasks:delete", args=[task.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_set_status_rejects_unknown_status(self):
        task = self.make_task(status=TaskStatus.TODO)
        self.client.post(reverse("tasks:set_status", args=[task.pk, "bogus"]))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.TODO)


class TaskApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.today = timezone.localdate()

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get("/api/tasks/").status_code, 403)

    def test_list_only_returns_own_tasks(self):
        Task.objects.create(user=self.user, title="من", date=self.today)
        Task.objects.create(user=self.other, title="سارا", date=self.today)
        self.client.force_login(self.user)
        response = self.client.get("/api/tasks/")
        titles = [t["title"] for t in response.json()["results"]]
        self.assertEqual(titles, ["من"])

    def test_cannot_create_task_on_another_users_goal(self):
        other_goal = Goal.objects.create(user=self.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/tasks/",
            {"title": "x", "date": self.today.isoformat(), "goal": other_goal.pk},
        )
        self.assertEqual(response.status_code, 400)


class TaskSearchViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("tasks:search"), {"q": "چیزی"})
        self.assertEqual(response.status_code, 302)

    def test_empty_query_shows_no_results_and_does_not_error(self):
        response = self.client.get(reverse("tasks:search"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["results"], [])

    def test_matches_are_case_and_position_insensitive(self):
        Task.objects.create(user=self.user, title="خرید نان", date=dt.date(2026, 9, 1))
        Task.objects.create(user=self.user, title="نان تازه", date=dt.date(2026, 9, 2))
        Task.objects.create(user=self.user, title="بی‌ربط", date=dt.date(2026, 9, 3))
        response = self.client.get(reverse("tasks:search"), {"q": "نان"})
        titles = {t.title for t in response.context["results"]}
        self.assertEqual(titles, {"خرید نان", "نان تازه"})

    def test_results_are_scoped_to_the_current_user(self):
        Task.objects.create(user=self.other, title="تسک سارا", date=dt.date(2026, 9, 1))
        response = self.client.get(reverse("tasks:search"), {"q": "تسک"})
        self.assertEqual(list(response.context["results"]), [])

    def test_results_are_ordered_newest_first(self):
        older = Task.objects.create(user=self.user, title="گزارش", date=dt.date(2026, 9, 1))
        newer = Task.objects.create(user=self.user, title="گزارش", date=dt.date(2026, 9, 10))
        response = self.client.get(reverse("tasks:search"), {"q": "گزارش"})
        self.assertEqual(list(response.context["results"]), [newer, older])


class TaskPriorityOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.day = dt.date(2026, 9, 24)

    def test_high_priority_comes_before_medium_and_low(self):
        low = Task.objects.create(user=self.user, title="کم", date=self.day, priority="low")
        high = Task.objects.create(user=self.user, title="زیاد", date=self.day, priority="high")
        medium = Task.objects.create(user=self.user, title="متوسط", date=self.day, priority="medium")
        ordered = list(Task.objects.filter(user=self.user).priority_ordered())
        self.assertEqual(ordered, [high, medium, low])

    def test_same_priority_falls_back_to_start_time(self):
        later = Task.objects.create(
            user=self.user, title="دیر", date=self.day, priority="high", start_time=dt.time(14, 0),
        )
        earlier = Task.objects.create(
            user=self.user, title="زود", date=self.day, priority="high", start_time=dt.time(9, 0),
        )
        ordered = list(Task.objects.filter(user=self.user).priority_ordered())
        self.assertEqual(ordered, [earlier, later])

    def test_default_priority_is_medium(self):
        task = Task.objects.create(user=self.user, title="x", date=self.day)
        self.assertEqual(task.priority, "medium")


class TaskDuplicateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.day = dt.date(2026, 9, 24)

    def setUp(self):
        self.client.force_login(self.user)

    def test_duplicate_creates_an_independent_copy_for_tomorrow(self):
        goal = Goal.objects.create(user=self.user, title="هدف", deadline=dt.date(2026, 12, 1))
        original = Task.objects.create(
            user=self.user, title="تمرین", date=self.day, goal=goal,
            start_time=dt.time(9, 0), end_time=dt.time(10, 0), priority="high",
        )
        self.client.post(reverse("tasks:duplicate", args=[original.pk]))
        copy = Task.objects.exclude(pk=original.pk).get(user=self.user)
        self.assertEqual(copy.date, self.day + dt.timedelta(days=1))
        self.assertEqual(copy.title, "تمرین")
        self.assertEqual(copy.goal, goal)
        self.assertEqual(copy.priority, "high")
        self.assertEqual(copy.status, TaskStatus.TODO)

    def test_duplicating_a_habit_task_does_not_link_the_copy_to_the_habit(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        original = Task.objects.create(user=self.user, title="آب خوردن", date=self.day, habit=habit)
        self.client.post(reverse("tasks:duplicate", args=[original.pk]))
        copy = Task.objects.exclude(pk=original.pk).get(user=self.user)
        self.assertIsNone(copy.habit)

    def test_cannot_duplicate_another_users_task(self):
        task = Task.objects.create(user=self.other, title="x", date=self.day)
        response = self.client.post(reverse("tasks:duplicate", args=[task.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Task.objects.filter(user=self.other).count(), 1)

    def test_duplicate_response_includes_a_toast_trigger(self):
        task = Task.objects.create(user=self.user, title="x", date=self.day)
        response = self.client.post(reverse("tasks:duplicate", args=[task.pk]))
        self.assertIn("toast", response.headers.get("HX-Trigger", ""))


class TaskExportIcsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("tasks:export_ics"))
        self.assertEqual(response.status_code, 302)

    def test_returns_a_calendar_file_with_correct_headers(self):
        response = self.client.get(reverse("tasks:export_ics"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("tasks.ics", response["Content-Disposition"])

    def test_includes_tasks_within_the_horizon_only(self):
        Task.objects.create(user=self.user, title="نزدیک", date=self.today + dt.timedelta(days=5))
        Task.objects.create(user=self.user, title="خیلی دور", date=self.today + dt.timedelta(days=200))
        Task.objects.create(user=self.user, title="گذشته", date=self.today - dt.timedelta(days=1))
        content = self.client.get(reverse("tasks:export_ics")).content.decode("utf-8")
        self.assertIn("نزدیک", content)
        self.assertNotIn("خیلی دور", content)
        self.assertNotIn("گذشته", content)

    def test_excludes_other_users_tasks(self):
        Task.objects.create(user=self.other, title="مال سارا", date=self.today + dt.timedelta(days=1))
        content = self.client.get(reverse("tasks:export_ics")).content.decode("utf-8")
        self.assertNotIn("مال سارا", content)


class IcsBuildTests(SimpleTestCase):
    """Unit tests for the pure .ics string-building logic (no DB needed)."""

    def make(self, **kwargs):
        data = {"id": 1, "title": "تسک", "date": dt.date(2026, 10, 1)}
        data.update(kwargs)
        return Task(**data)

    def test_wraps_events_in_a_valid_vcalendar(self):
        content = build_ics([self.make()])
        self.assertTrue(content.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(content.endswith("END:VCALENDAR\r\n"))
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("END:VEVENT", content)

    def test_timed_task_gets_dtstart_and_dtend(self):
        content = build_ics([self.make(start_time=dt.time(9, 0), end_time=dt.time(10, 30))])
        self.assertIn("DTSTART:20261001T090000", content)
        self.assertIn("DTEND:20261001T103000", content)

    def test_missing_end_time_uses_default_duration(self):
        content = build_ics([self.make(start_time=dt.time(9, 0))])
        self.assertIn("DTSTART:20261001T090000", content)
        self.assertIn("DTEND:20261001T093000", content)  # +30 minutes

    def test_task_without_a_time_is_an_all_day_event(self):
        content = build_ics([self.make()])
        self.assertIn("DTSTART;VALUE=DATE:20261001", content)

    def test_commas_and_semicolons_in_title_are_escaped(self):
        content = build_ics([self.make(title="خرید نان, شیر; و تخم‌مرغ")])
        self.assertIn("خرید نان\\, شیر\\; و تخم‌مرغ", content)

    def test_empty_task_list_still_produces_a_valid_empty_calendar(self):
        content = build_ics([])
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("END:VCALENDAR", content)
        self.assertNotIn("BEGIN:VEVENT", content)
