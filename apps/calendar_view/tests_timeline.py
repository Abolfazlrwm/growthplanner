import datetime as dt

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.tasks.models import Task

from .timeline import position_task, split_timed_and_untimed

User = get_user_model()


class PositionMathTests(SimpleTestCase):
    def make(self, start, end=None):
        return Task(title="x", start_time=start, end_time=end)

    def test_nine_to_ten_thirty(self):
        pos = position_task(self.make(dt.time(9, 0), dt.time(10, 30)))
        self.assertAlmostEqual(pos["top"], 37.5)
        self.assertAlmostEqual(pos["height"], 6.25)

    def test_midnight_start(self):
        pos = position_task(self.make(dt.time(0, 0), dt.time(1, 0)))
        self.assertAlmostEqual(pos["top"], 0)
        self.assertAlmostEqual(pos["height"], round(60 / 1440 * 100, 2))

    def test_missing_end_time_uses_default_block(self):
        pos = position_task(self.make(dt.time(14, 0)))
        self.assertAlmostEqual(pos["height"], round(30 / 1440 * 100, 2))

    def test_very_short_task_has_a_minimum_visible_height(self):
        pos = position_task(self.make(dt.time(8, 0), dt.time(8, 5)))
        self.assertAlmostEqual(pos["height"], round(15 / 1440 * 100, 2))


class SplitTests(SimpleTestCase):
    def test_splits_and_sorts_by_start_time(self):
        late = Task(title="دیر", start_time=dt.time(18, 0))
        early = Task(title="زود", start_time=dt.time(8, 0))
        untimed = Task(title="بدون ساعت")
        timed_positions, untimed_tasks = split_timed_and_untimed([late, early, untimed])
        self.assertEqual([p["task"].title for p in timed_positions], ["زود", "دیر"])
        self.assertEqual(untimed_tasks, [untimed])


class TimelineViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar_view:timeline")).status_code, 302)

    def test_default_date_is_today(self):
        response = self.client.get(reverse("calendar_view:timeline"))
        self.assertEqual(response.context["date"], self.today)

    def test_only_shows_own_tasks(self):
        mine = Task.objects.create(user=self.user, title="من", date=self.today, start_time=dt.time(9, 0))
        Task.objects.create(user=self.other, title="سارا", date=self.today, start_time=dt.time(9, 0))
        response = self.client.get(reverse("calendar_view:timeline"))
        titles = [p["task"].title for p in response.context["timed_positions"]]
        self.assertEqual(titles, ["من"])

    def test_untimed_tasks_listed_separately(self):
        Task.objects.create(user=self.user, title="بدون ساعت", date=self.today)
        response = self.client.get(reverse("calendar_view:timeline"))
        self.assertEqual(response.context["timed_positions"], [])
        self.assertEqual(len(response.context["untimed_tasks"]), 1)

    def test_explicit_date_in_url(self):
        other_day = self.today + dt.timedelta(days=2)
        Task.objects.create(user=self.user, title="x", date=other_day, start_time=dt.time(10, 0))
        response = self.client.get(reverse("calendar_view:timeline", args=[other_day.isoformat()]))
        self.assertEqual(response.context["date"], other_day)
        self.assertEqual(len(response.context["timed_positions"]), 1)


class TimelineNowMarkerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("nina", password="pass12345")
        self.client.force_login(self.user)

    def test_now_marker_only_on_today(self):
        today = timezone.localdate()
        response = self.client.get(reverse("calendar_view:timeline"))
        now = timezone.localtime()
        self.assertTrue(0 <= response.context["now_minutes"] <= 24 * 60)
        self.assertAlmostEqual(response.context["now_minutes"], now.hour * 60 + now.minute, delta=2)
        other = self.client.get(reverse("calendar_view:timeline", args=[(today + dt.timedelta(days=3)).isoformat()]))
        self.assertIsNone(other.context["now_minutes"])
