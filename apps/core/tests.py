import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.goals.models import Goal, GoalStatus
from apps.tasks.models import Task, TaskStatus

User = get_user_model()


class HomeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_user_sees_the_public_landing_page(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/landing.html")
        self.assertContains(response, reverse("accounts:register"))
        self.assertContains(response, reverse("accounts:login"))

    def test_logged_in_user_sees_rtl_persian_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, 'lang="fa"')

    def test_home_shows_only_todays_tasks(self):
        today_task = Task.objects.create(user=self.user, title="امروز", date=self.today)
        Task.objects.create(user=self.user, title="فردا", date=self.today + dt.timedelta(days=1))
        response = self.client.get(reverse("core:home"))
        self.assertEqual(list(response.context["tasks"]), [today_task])

    def test_home_shows_active_goals_within_a_week(self):
        near = Goal.objects.create(user=self.user, title="نزدیک", deadline=self.today + dt.timedelta(days=3))
        Goal.objects.create(user=self.user, title="دور", deadline=self.today + dt.timedelta(days=30))
        Goal.objects.create(
            user=self.user, title="تکمیل‌شده", deadline=self.today + dt.timedelta(days=2),
            status=GoalStatus.COMPLETED,
        )
        response = self.client.get(reverse("core:home"))
        self.assertEqual(list(response.context["upcoming_goals"]), [near])

    def test_home_excludes_past_deadline_goals(self):
        Goal.objects.create(user=self.user, title="گذشته", deadline=self.today - dt.timedelta(days=1))
        response = self.client.get(reverse("core:home"))
        self.assertEqual(list(response.context["upcoming_goals"]), [])

    def test_has_open_tasks_flag(self):
        response = self.client.get(reverse("core:home"))
        self.assertFalse(response.context["has_open_tasks"])
        Task.objects.create(user=self.user, title="x", date=self.today, status=TaskStatus.TODO)
        response = self.client.get(reverse("core:home"))
        self.assertTrue(response.context["has_open_tasks"])


class ReviewViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:review")).status_code, 302)

    def test_review_only_shows_open_tasks(self):
        todo = Task.objects.create(user=self.user, title="باز", date=self.today, status=TaskStatus.TODO)
        Task.objects.create(user=self.user, title="انجام‌شده", date=self.today, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="نشد", date=self.today, status=TaskStatus.FAILED)
        response = self.client.get(reverse("core:review"))
        self.assertEqual(list(response.context["tasks"]), [todo])

    def test_review_ignores_other_days(self):
        Task.objects.create(user=self.user, title="فردا", date=self.today + dt.timedelta(days=1))
        response = self.client.get(reverse("core:review"))
        self.assertEqual(list(response.context["tasks"]), [])

    def test_review_ignores_other_users_tasks(self):
        Task.objects.create(user=self.other, title="سارا", date=self.today)
        response = self.client.get(reverse("core:review"))
        self.assertEqual(list(response.context["tasks"]), [])


class HealthzTests(TestCase):
    def test_healthz_is_public_and_checks_the_database(self):
        response = self.client.get(reverse("core:healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class StatsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:stats")).status_code, 302)

    def test_week_completion_percent(self):
        Task.objects.create(user=self.user, title="a", date=self.today, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="b", date=self.today, status=TaskStatus.TODO)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["week"]["percent"], 50)
        self.assertEqual(response.context["week"]["total"], 2)

    def test_week_percent_is_none_with_no_tasks(self):
        response = self.client.get(reverse("core:stats"))
        self.assertIsNone(response.context["week"]["percent"])

    def test_tasks_outside_the_window_are_excluded(self):
        old_day = self.today - dt.timedelta(days=40)
        Task.objects.create(user=self.user, title="قدیمی", date=old_day, status=TaskStatus.DONE)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["month"]["total"], 0)

    def test_mood_average_only_counts_notes_with_mood_set(self):
        from apps.journal.models import DayNote
        DayNote.objects.create(user=self.user, date=self.today, mood=4)
        DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=1), mood=2)
        DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=2), mood=None, text="بدون امتیاز")
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["mood_avg"], 3.0)

    def test_goal_counts_by_status(self):
        Goal.objects.create(user=self.user, title="فعال", deadline=self.today, status=GoalStatus.ACTIVE)
        Goal.objects.create(user=self.user, title="تمام‌شده", deadline=self.today, status=GoalStatus.COMPLETED)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["active_goals"], 1)
        self.assertEqual(response.context["completed_goals"], 1)
        self.assertEqual(response.context["abandoned_goals"], 0)

    def test_daily_breakdown_has_seven_days_oldest_first(self):
        response = self.client.get(reverse("core:stats"))
        daily = response.context["daily"]
        self.assertEqual(len(daily), 7)
        self.assertEqual(daily[0]["date"], self.today - dt.timedelta(days=6))
        self.assertEqual(daily[-1]["date"], self.today)

    def test_other_users_data_is_excluded(self):
        other = User.objects.create_user("sara", password="pass12345")
        Task.objects.create(user=other, title="سارا", date=self.today, status=TaskStatus.DONE)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["week"]["total"], 0)

    def test_streak_is_zero_with_no_done_tasks(self):
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["streak"], 0)

    def test_streak_counts_consecutive_done_days_including_today(self):
        for offset in range(3):
            day = self.today - dt.timedelta(days=offset)
            Task.objects.create(user=self.user, title=f"t{offset}", date=day, status=TaskStatus.DONE)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["streak"], 3)

    def test_streak_still_counts_yesterday_if_today_not_done_yet(self):
        yesterday = self.today - dt.timedelta(days=1)
        Task.objects.create(user=self.user, title="دیروز", date=yesterday, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="امروز", date=self.today, status=TaskStatus.TODO)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["streak"], 1)

    def test_streak_breaks_on_a_gap_day(self):
        Task.objects.create(user=self.user, title="امروز", date=self.today, status=TaskStatus.DONE)
        two_days_ago = self.today - dt.timedelta(days=2)
        Task.objects.create(user=self.user, title="پریروز", date=two_days_ago, status=TaskStatus.DONE)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.context["streak"], 1)


class ServiceWorkerAndOfflinePageTests(TestCase):
    def test_offline_page_works_without_login(self):
        response = self.client.get(reverse("core:offline"))
        self.assertEqual(response.status_code, 200)

    def test_service_worker_is_served_as_javascript_from_the_root(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_service_worker_does_not_require_login(self):
        # Anonymous visitors get the shell cached too, before they ever log in.
        response = self.client.get(reverse("core:service_worker"))
        self.assertEqual(response.status_code, 200)


class LandingPageSeoTests(TestCase):
    def setUp(self):
        from django.test import override_settings
        self.origin_override = override_settings(PUBLIC_ORIGIN="https://growthplanner.example")
        self.origin_override.enable()
        self.addCleanup(self.origin_override.disable)
        self.response = self.client.get("/")

    def test_has_meta_description_and_is_indexable(self):
        self.assertContains(self.response, '<meta name="description"')
        self.assertContains(self.response, 'content="index,follow"')

    def test_has_open_graph_and_twitter_tags_with_absolute_urls(self):
        self.assertContains(self.response, '<meta property="og:title"')
        self.assertContains(self.response, 'property="og:image" content="https://growthplanner.example/static/')
        self.assertContains(self.response, 'rel="canonical" href="https://growthplanner.example/"')
        self.assertContains(self.response, 'name="twitter:card"')

    def test_has_valid_json_ld(self):
        import json
        import re

        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.response.content.decode(), re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(data["@type"], "WebApplication")
        self.assertEqual(data["inLanguage"], "fa")

    def test_is_rtl_persian(self):
        self.assertContains(self.response, 'dir="rtl"')
        self.assertContains(self.response, 'lang="fa"')

    def test_app_pages_are_not_indexable(self):
        user = User.objects.create_user("sara", password="pass12345")
        self.client.force_login(user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'content="noindex,nofollow"')


class GreetingTests(TestCase):
    def test_greeting_covers_every_hour_of_the_day(self):
        from apps.core.views import greeting_for_hour

        self.assertEqual(greeting_for_hour(5), "صبح بخیر")
        self.assertEqual(greeting_for_hour(11), "صبح بخیر")
        self.assertEqual(greeting_for_hour(12), "ظهر بخیر")
        self.assertEqual(greeting_for_hour(16), "ظهر بخیر")
        self.assertEqual(greeting_for_hour(17), "عصر بخیر")
        self.assertEqual(greeting_for_hour(20), "عصر بخیر")
        self.assertEqual(greeting_for_hour(21), "شب بخیر")
        self.assertEqual(greeting_for_hour(0), "شب بخیر")
        self.assertEqual(greeting_for_hour(4), "شب بخیر")

    def test_hero_message_states(self):
        from apps.core.views import hero_message

        self.assertIn("شروع کن", hero_message(0, 0))
        self.assertIn("انجام شد", hero_message(3, 3))
        self.assertEqual(hero_message(1, 3), "۲ کار مونده؛ قدم‌به‌قدم.")


class TodayProgressRingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("reza", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_ring_counts_come_from_todays_real_tasks(self):
        Task.objects.create(user=self.user, title="الف", date=self.today, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="ب", date=self.today, status=TaskStatus.TODO)
        Task.objects.create(user=self.user, title="فردا", date=self.today + dt.timedelta(days=1), status=TaskStatus.DONE)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["total_count"], 2)
        self.assertEqual(response.context["done_count"], 1)
        self.assertEqual(response.context["progress_percent"], 50)
        self.assertContains(response, "--p: 50")

    def test_ring_is_zero_with_no_tasks_and_does_not_divide_by_zero(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["progress_percent"], 0)
        self.assertEqual(response.context["total_count"], 0)

    def test_other_users_tasks_are_not_counted(self):
        other = User.objects.create_user("other", password="pass12345")
        Task.objects.create(user=other, title="x", date=self.today, status=TaskStatus.DONE)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["total_count"], 0)

    def test_page_includes_greeting_and_empty_state(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'class="hero-greet"')
        self.assertContains(response, "empty-state")
        self.assertContains(response, 'id="task-list"')


class PersianDigitsFilterTests(TestCase):
    def test_fa_filter(self):
        from apps.core.templatetags.jalali_tags import fa

        self.assertEqual(fa(1405), "۱۴۰۵")
        self.assertEqual(fa("12:30"), "۱۲:۳۰")
        self.assertEqual(fa(None), "")
