"""Tests for the focus page, the activity heatmap and the new navigation shell."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.views import HEATMAP_WEEKS, build_heatmap
from apps.tasks.models import Task, TaskStatus

User = get_user_model()


class FocusPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("sara", password="pass12345")
        cls.other = User.objects.create_user("omid", password="pass12345")
        cls.today = timezone.localdate()

    def test_requires_login(self):
        response = self.client.get(reverse("core:focus"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('core:focus')}")

    def test_lists_only_my_open_tasks_for_today(self):
        mine = Task.objects.create(user=self.user, title="باز امروز", date=self.today)
        Task.objects.create(user=self.user, title="انجام‌شده", date=self.today, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="فردا", date=self.today + dt.timedelta(days=1))
        Task.objects.create(user=self.other, title="مال دیگری", date=self.today)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:focus"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["tasks"]), [mine])
        self.assertContains(response, "باز امروز")
        self.assertNotContains(response, "مال دیگری")
        self.assertContains(response, reverse("tasks:set_status", args=[mine.id, "done"]))

    def test_task_query_param_preselects_and_ignores_garbage(self):
        task = Task.objects.create(user=self.user, title="الف", date=self.today)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("core:focus"), {"task": task.id}).context["selected_id"], task.id)
        self.assertIsNone(self.client.get(reverse("core:focus"), {"task": "abc"}).context["selected_id"])
        self.assertIsNone(self.client.get(reverse("core:focus")).context["selected_id"])

    def test_empty_state_when_no_open_tasks(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:focus"))
        self.assertContains(response, "تسک بازی برای امروز نداری")


class HeatmapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("nina", password="pass12345")
        cls.other = User.objects.create_user("kian", password="pass12345")
        cls.today = timezone.localdate()

    def done(self, day, user=None, n=1):
        for i in range(n):
            Task.objects.create(user=user or self.user, title=f"t{i}", date=day, status=TaskStatus.DONE)

    def test_shape_is_weeks_by_seven_and_starts_on_saturday(self):
        heat = build_heatmap(self.user, self.today)
        self.assertEqual(len(heat["columns"]), HEATMAP_WEEKS)
        for column in heat["columns"]:
            self.assertEqual(len(column["cells"]), 7)
        first = heat["columns"][0]["cells"][0]["date"]
        self.assertEqual((first.weekday() + 2) % 7, 0)  # Persian week starts on Saturday

    def test_today_is_the_last_non_future_cell_and_later_cells_are_future(self):
        heat = build_heatmap(self.user, self.today)
        cells = [c for col in heat["columns"] for c in col["cells"]]
        non_future = [c for c in cells if not c["future"]]
        self.assertEqual(non_future[-1]["date"], self.today)
        self.assertTrue(all(c["date"] > self.today for c in cells if c["future"]))

    def test_counts_only_my_done_tasks(self):
        self.done(self.today, n=2)
        self.done(self.today - dt.timedelta(days=1), n=1)
        Task.objects.create(user=self.user, title="ناتمام", date=self.today, status=TaskStatus.TODO)
        self.done(self.today, user=self.other, n=5)
        heat = build_heatmap(self.user, self.today)
        self.assertEqual(heat["total_done"], 3)
        self.assertEqual(heat["active_days"], 2)

    def test_levels_scale_to_the_busiest_day(self):
        self.done(self.today, n=4)
        self.done(self.today - dt.timedelta(days=1), n=1)
        heat = build_heatmap(self.user, self.today)
        by_date = {c["date"]: c for col in heat["columns"] for c in col["cells"]}
        self.assertEqual(by_date[self.today]["level"], 4)
        self.assertEqual(by_date[self.today - dt.timedelta(days=1)]["level"], 1)
        self.assertEqual(by_date[self.today - dt.timedelta(days=2)]["level"], 0)

    def test_empty_account_has_no_activity_and_does_not_crash(self):
        heat = build_heatmap(self.user, self.today)
        self.assertEqual((heat["total_done"], heat["active_days"]), (0, 0))
        self.assertTrue(all(c["level"] == 0 for col in heat["columns"] for c in col["cells"]))

    def test_old_tasks_outside_the_window_are_ignored(self):
        self.done(self.today - dt.timedelta(days=7 * HEATMAP_WEEKS + 10), n=3)
        self.assertEqual(build_heatmap(self.user, self.today)["total_done"], 0)

    def test_stats_page_renders_the_heatmap(self):
        self.done(self.today, n=2)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:stats"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["heatmap"]["total_done"], 2)
        self.assertContains(response, 'class="heat"')
        self.assertContains(response, "heat-cell lv4")


class NavigationShellTests(TestCase):
    def test_signed_in_pages_have_the_drawer_with_every_section(self):
        user = User.objects.create_user("ali", password="pass12345")
        self.client.force_login(user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="drawer"')
        self.assertContains(response, "data-drawer-open")
        for name in ("goals:list", "habits:list", "calendar_view:month", "calendar_view:timeline",
                     "core:focus", "core:stats", "tasks:search", "accounts:settings"):
            self.assertContains(response, f'href="{reverse(name)}"', msg_prefix=name)
        self.assertContains(response, reverse("accounts:logout"))

    def test_header_keeps_only_a_few_quick_links(self):
        user = User.objects.create_user("ali2", password="pass12345")
        self.client.force_login(user)
        html = self.client.get(reverse("core:home")).content.decode()
        nav = html.split('aria-label="دسترسی سریع"')[1].split("</nav>")[0]
        self.assertLessEqual(nav.count("<a "), 3)

    def test_landing_has_no_drawer_for_visitors(self):
        response = self.client.get("/")
        self.assertNotContains(response, 'id="drawer"')

    def test_content_is_not_hidden_without_javascript(self):
        # The "js" class (which enables reveal animations) is only added by script.
        response = self.client.get("/")
        self.assertNotContains(response, '<html lang="fa" dir="rtl" class="js"')
        self.assertContains(response, 'classList.add("js")')
