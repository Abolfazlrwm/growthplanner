import datetime as dt

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.tasks.models import Task, TaskStatus
from apps.habits.models import Habit
from apps.calendar_view.models import CalendarSubscription

User = get_user_model()


class MonthViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar_view:month")).status_code, 302)

    def test_default_view_shows_31_days_for_farvardin(self):
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        in_month = [d for week in response.context["grid"] for d in week if d["in_month"]]
        self.assertEqual(len(in_month), 31)
        self.assertEqual(response.context["month_name"], "فروردین")

    def test_every_week_has_seven_days_and_page_renders(self):
        response = self.client.get(reverse("calendar_view:month", args=[1405, 7]))
        self.assertEqual(response.status_code, 200)
        for week in response.context["grid"]:
            self.assertEqual(len(week), 7)

    def test_task_dot_appears_only_for_owner(self):
        Task.objects.create(user=self.user, title="من", date=dt.date(2026, 3, 25), status=TaskStatus.DONE)
        Task.objects.create(user=self.other, title="سارا", date=dt.date(2026, 3, 25), status=TaskStatus.DONE)
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        day = next(
            d for week in response.context["grid"] for d in week
            if d["gregorian"] == dt.date(2026, 3, 25)
        )
        self.assertEqual(day["dots"], ["dot-done"])

    def test_multiple_statuses_show_multiple_dots_in_priority_order(self):
        Task.objects.create(user=self.user, title="a", date=dt.date(2026, 3, 25), status=TaskStatus.FAILED)
        Task.objects.create(user=self.user, title="b", date=dt.date(2026, 3, 25), status=TaskStatus.DONE)
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        day = next(
            d for week in response.context["grid"] for d in week
            if d["gregorian"] == dt.date(2026, 3, 25)
        )
        self.assertEqual(day["dots"], ["dot-done", "dot-failed"])

    def test_prev_next_navigation_wraps_year(self):
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        self.assertEqual((response.context["prev_year"], response.context["prev_month"]), (1404, 12))
        self.assertEqual((response.context["next_year"], response.context["next_month"]), (1405, 2))

    def test_default_url_uses_current_jalali_month(self):
        response = self.client.get(reverse("calendar_view:month"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_current_month"])

    def test_habit_dot_shows_up_without_visiting_that_day_individually(self):
        Habit.objects.create(user=self.user, title="آب خوردن")  # every day
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        day = next(
            d for week in response.context["grid"] for d in week
            if d["gregorian"] == dt.date(2026, 3, 25)
        )
        self.assertEqual(day["dots"], ["dot-todo"])  # todo-colored dot for the generated task

    def test_habit_dots_are_scoped_to_the_owner(self):
        Habit.objects.create(user=self.other, title="مال دیگری")
        response = self.client.get(reverse("calendar_view:month", args=[1405, 1]))
        day = next(
            d for week in response.context["grid"] for d in week
            if d["gregorian"] == dt.date(2026, 3, 25)
        )
        self.assertEqual(day["dots"], [])


class CalendarSubscriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("subscriber", password="pass12345")
        cls.other = User.objects.create_user("other-subscriber", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)
        self.subscription = CalendarSubscription.objects.create(user=self.user)

    def feed_url(self, subscription=None):
        return reverse(
            "calendar_view:feed",
            kwargs={"token": (subscription or self.subscription).token},
        )

    def test_feed_is_a_private_bearer_endpoint_with_no_store_headers(self):
        Task.objects.create(user=self.user, title="رویداد خصوصی", date=timezone.localdate())
        self.client.logout()
        response = self.client.get(self.feed_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("رویداد خصوصی", response.content.decode("utf-8"))
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_expired_or_revoked_token_cannot_read_the_feed(self):
        self.subscription.expires_at = timezone.now() - dt.timedelta(seconds=1)
        self.subscription.save(update_fields=["expires_at"])
        self.assertEqual(self.client.get(self.feed_url()).status_code, 404)

        self.subscription.rotate()
        active_url = self.feed_url()
        self.subscription.revoke()
        self.assertEqual(self.client.get(active_url).status_code, 404)

    def test_rotation_is_scoped_to_current_user_and_invalidates_old_link(self):
        other_subscription = CalendarSubscription.objects.create(user=self.other)
        mine_before = self.subscription.token
        other_before = other_subscription.token

        response = self.client.post(reverse("calendar_view:subscription"), {"action": "rotate"})
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        other_subscription.refresh_from_db()
        self.assertNotEqual(self.subscription.token, mine_before)
        self.assertEqual(other_subscription.token, other_before)
        self.assertEqual(
            self.client.get(reverse("calendar_view:feed", kwargs={"token": mine_before})).status_code,
            404,
        )
        self.assertEqual(self.client.get(self.feed_url()).status_code, 200)

    def test_subscription_actions_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(reverse("calendar_view:subscription"), {"action": "revoke"})
        self.assertEqual(response.status_code, 403)
        self.subscription.refresh_from_db()
        self.assertIsNone(self.subscription.revoked_at)

    def test_manager_uses_browser_origin_for_private_url(self):
        response = self.client.get(reverse("calendar_view:subscription"))
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("window.location.origin + path", body)
        self.assertIn(self.feed_url(), body)
        self.assertNotIn("http://testserver", body)
        self.assertIn("no-store", response["Cache-Control"])

    def test_feed_projects_habits_without_creating_tasks_and_avoids_persisted_duplicate(self):
        today = timezone.localdate()
        habit = Habit.objects.create(user=self.user, title="عادت بدون ساخت تسک")
        before = Task.objects.count()
        content = self.client.get(self.feed_url()).content.decode("utf-8")
        self.assertEqual(Task.objects.count(), before)
        self.assertIn(f"UID:habit-{habit.pk}-{today:%Y%m%d}@growth-planner", content)

        persisted = Task.objects.create(
            user=self.user,
            habit=habit,
            title="نسخهٔ واقعی عادت",
            date=today,
        )
        content = self.client.get(self.feed_url()).content.decode("utf-8")
        habit_uid = f"UID:habit-{habit.pk}-{today:%Y%m%d}@growth-planner"
        self.assertIn(habit_uid, content)
        self.assertEqual(content.count(habit_uid), 1)

    def test_feed_uses_utc_for_timed_events_and_exclusive_end_for_all_day_events(self):
        day = timezone.localdate() + dt.timedelta(days=1)
        timed = Task.objects.create(
            user=self.user,
            title="جلسهٔ زمان‌دار",
            date=day,
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
        )
        Task.objects.create(user=self.user, title="کار تمام‌روز", date=day)
        content = self.client.get(self.feed_url()).content.decode("utf-8")
        self.assertIn(f"UID:task-{timed.pk}@growth-planner", content)
        # Tehran 09:00 is serialized as an absolute UTC value, not a floating local time.
        self.assertIn(f"DTSTART:{day:%Y%m%d}T053000Z", content)
        self.assertIn(f"DTEND:{day:%Y%m%d}T063000Z", content)
        self.assertIn(f"DTSTART;VALUE=DATE:{day:%Y%m%d}", content)
        self.assertIn(f"DTEND;VALUE=DATE:{day + dt.timedelta(days=1):%Y%m%d}", content)

    def test_long_persian_title_is_utf8_folded_and_crlf_safe(self):
        title = "عنوان بسیار بلند فارسی، " * 16 + "\r\nX-INJECTED:bad"
        Task.objects.create(user=self.user, title=title, date=timezone.localdate())
        content = self.client.get(self.feed_url()).content.decode("utf-8")
        physical_lines = content.split("\r\n")[:-1]
        self.assertTrue(any(line.startswith(" ") for line in physical_lines))
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in physical_lines))
        self.assertNotIn("\r\nX-INJECTED:bad", content)
        self.assertIn("\\nX-INJECTED:bad", content)
