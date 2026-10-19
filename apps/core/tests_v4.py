"""Tests for focus logging, goal/habit detail pages, personal insights and the new shortcuts."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.focus import FOCUS_MAX_MINUTES, focus_summary
from apps.core.insights import (MIN_DAYS_PER_MOOD_GROUP, MIN_DONE_FOR_WEEKDAY, MIN_TIMED_FOR_TIME_OF_DAY,
                                _bucket_for, compute_insights)
from apps.core.templatetags.jalali_tags import duration
from apps.goals.models import Goal, GoalStatus
from apps.habits.models import Habit
from apps.habits.services import habit_history
from apps.journal.models import DayNote
from apps.tasks.models import FocusSession, Task, TaskStatus

User = get_user_model()


def make_user(name):
    return User.objects.create_user(name, password="pass12345")


class DurationFilterTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(duration(0), "۰ دقیقه")
        self.assertEqual(duration(45), "۴۵ دقیقه")
        self.assertEqual(duration(60), "۱ ساعت")
        self.assertEqual(duration(135), "۲ ساعت و ۱۵ دقیقه")

    def test_bad_input_is_empty(self):
        self.assertEqual(duration(None), "")
        self.assertEqual(duration("abc"), "")


class FocusLogTests(TestCase):
    def setUp(self):
        self.user = make_user("focus")
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def log(self, **data):
        return self.client.post(reverse("core:focus_log"), data)

    def test_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(self.log(minutes=25).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("core:focus_log")).status_code, 405)

    def test_logs_a_session_and_returns_todays_totals(self):
        first = self.log(minutes=25)
        self.assertEqual(first.status_code, 200)
        second = self.log(minutes=30).json()
        self.assertTrue(second["ok"])
        self.assertEqual((second["today_sessions"], second["today_minutes"], second["week_minutes"]), (2, 55, 55))
        self.assertEqual(FocusSession.objects.filter(user=self.user, date=self.today).count(), 2)

    def test_session_can_be_tied_to_my_task(self):
        task = Task.objects.create(user=self.user, title="کار", date=self.today)
        self.assertEqual(self.log(minutes=25, task=task.id).status_code, 200)
        self.assertEqual(FocusSession.objects.get().task_id, task.id)

    def test_rejects_foreign_or_unknown_task(self):
        other = make_user("other")
        theirs = Task.objects.create(user=other, title="x", date=self.today)
        self.assertEqual(self.log(minutes=25, task=theirs.id).status_code, 400)
        self.assertEqual(self.log(minutes=25, task=99999).status_code, 400)
        self.assertEqual(self.log(minutes=25, task="abc").status_code, 400)
        self.assertFalse(FocusSession.objects.exists())

    def test_rejects_bad_minutes(self):
        for bad in ("", "abc", "0", "-5", str(FOCUS_MAX_MINUTES + 1)):
            with self.subTest(minutes=bad):
                self.assertEqual(self.log(minutes=bad).status_code, 400)
        self.assertFalse(FocusSession.objects.exists())

    def test_deleting_the_task_keeps_the_session(self):
        task = Task.objects.create(user=self.user, title="کار", date=self.today)
        self.log(minutes=25, task=task.id)
        task.delete()
        session = FocusSession.objects.get()
        self.assertIsNone(session.task)

    def test_focus_page_shows_server_totals(self):
        FocusSession.objects.create(user=self.user, minutes=50, date=self.today)
        response = self.client.get(reverse("core:focus"))
        self.assertEqual(response.context["focus"]["today_sessions"], 1)
        self.assertContains(response, 'data-initial="1"')
        self.assertContains(response, reverse("core:focus_log"))
        self.assertContains(response, "۵۰ دقیقه")


class FocusSummaryTests(TestCase):
    def setUp(self):
        self.user = make_user("sum")
        self.other = make_user("sum2")
        self.today = timezone.localdate()

    def test_series_and_totals_for_the_last_seven_days(self):
        FocusSession.objects.create(user=self.user, minutes=25, date=self.today)
        FocusSession.objects.create(user=self.user, minutes=25, date=self.today)
        FocusSession.objects.create(user=self.user, minutes=40, date=self.today - dt.timedelta(days=2))
        FocusSession.objects.create(user=self.user, minutes=99, date=self.today - dt.timedelta(days=9))  # outside
        FocusSession.objects.create(user=self.other, minutes=77, date=self.today)  # someone else
        s = focus_summary(self.user, self.today)
        self.assertEqual(len(s["series"]), 7)
        self.assertEqual(s["series"][-1]["date"], self.today)
        self.assertEqual((s["today_sessions"], s["today_minutes"]), (2, 50))
        self.assertEqual((s["week_minutes"], s["week_sessions"]), (90, 3))
        self.assertEqual(max(d["percent"] for d in s["series"]), 100)
        self.assertTrue(s["has_data"])

    def test_empty_account(self):
        s = focus_summary(self.user, self.today)
        self.assertFalse(s["has_data"])
        self.assertEqual((s["today_minutes"], s["week_minutes"]), (0, 0))
        self.assertTrue(all(d["percent"] == 0 for d in s["series"]))

    def test_stats_page_includes_focus_and_insights_sections(self):
        FocusSession.objects.create(user=self.user, minutes=25, date=self.today)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:stats"))
        self.assertContains(response, "زمان تمرکز")
        self.assertContains(response, "بینش‌های شخصی")
        self.assertTrue(response.context["focus"]["has_data"])


class GoalDetailTests(TestCase):
    def setUp(self):
        self.user = make_user("gd")
        self.other = make_user("gd2")
        self.today = timezone.localdate()
        self.goal = Goal.objects.create(user=self.user, title="پروژه‌ی ترم", deadline=self.today + dt.timedelta(days=10))
        self.client.force_login(self.user)

    def task(self, title, days=0, status=TaskStatus.TODO, **kw):
        return Task.objects.create(user=self.user, goal=self.goal, title=title, date=self.today + dt.timedelta(days=days), status=status, **kw)

    def get(self, goal=None, **params):
        return self.client.get(reverse("goals:detail", args=[(goal or self.goal).pk]), params)

    def test_requires_login_and_ownership(self):
        self.client.logout()
        self.assertEqual(self.get().status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.get().status_code, 404)

    def test_numbers_and_pace(self):
        self.task("الف", -1, TaskStatus.DONE)
        self.task("ب", 0, TaskStatus.DONE)
        self.task("پ", 1)
        self.task("ت", 2, TaskStatus.IN_PROGRESS)
        self.task("ث", -2, TaskStatus.FAILED)
        ctx = self.get().context
        self.assertEqual((ctx["total"], ctx["done_count"], ctx["open_count"], ctx["failed_count"]), (5, 2, 2, 1))
        self.assertEqual(ctx["percent"], 40)
        self.assertEqual(ctx["days_left"], 10)
        self.assertEqual(ctx["needed_per_day"], 0.2)
        self.assertEqual((ctx["pace_count"], ctx["pace_unit"]), (2, "هفته"))  # 0.2/day -> about 2 a week
        self.assertFalse(ctx["overdue"])

    def test_open_tasks_are_grouped_by_day_and_exclude_done(self):
        self.task("امروز ۱", 0)
        self.task("امروز ۲", 0)
        self.task("فردا", 1)
        self.task("تمام", 0, TaskStatus.DONE)
        groups = self.get().context["groups"]
        self.assertEqual([len(g["tasks"]) for g in groups], [2, 1])
        self.assertEqual(groups[0]["date"], self.today)

    def test_weekly_chart_counts_done_tasks_in_their_week(self):
        self.task("الف", 0, TaskStatus.DONE)
        self.task("ب", 0, TaskStatus.DONE)
        self.task("پ", -14, TaskStatus.DONE)
        ctx = self.get().context
        self.assertEqual(len(ctx["weeks"]), 8)
        self.assertEqual(ctx["weeks"][-1]["count"], 2)
        self.assertEqual(ctx["weeks"][-1]["percent"], 100)
        self.assertEqual(sum(w["count"] for w in ctx["weeks"]), 3)
        self.assertTrue(ctx["has_week_data"])

    def test_other_users_tasks_and_goals_are_not_mixed_in(self):
        Task.objects.create(user=self.other, title="مال دیگری", date=self.today)
        self.task("مال من")
        response = self.get()
        self.assertContains(response, "مال من")
        self.assertNotContains(response, "مال دیگری")

    def test_overdue_goal_with_open_tasks(self):
        late = Goal.objects.create(user=self.user, title="عقب", deadline=self.today - dt.timedelta(days=3))
        Task.objects.create(user=self.user, goal=late, title="مانده", date=self.today)
        ctx = self.get(late).context
        self.assertTrue(ctx["overdue"])
        self.assertEqual(ctx["days_over"], 3)
        self.assertIsNone(ctx["needed_per_day"])

    def test_empty_goal_renders_with_zero_percent(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["percent"], 0)
        self.assertContains(response, "هنوز تسکی به این هدف وصل نشده")

    def test_quick_add_form_posts_to_task_create_with_the_goal(self):
        response = self.get()
        self.assertContains(response, reverse("tasks:create"))
        self.assertContains(response, f'name="goal" value="{self.goal.pk}"')

    def test_celebration_flag_only_with_the_query_param(self):
        self.assertNotContains(self.get(), "data-celebrate")
        self.assertContains(self.get(celebrate="1"), "data-celebrate")

    def test_list_links_to_detail(self):
        self.assertContains(self.client.get(reverse("goals:list")), reverse("goals:detail", args=[self.goal.pk]))


class GoalCompleteTests(TestCase):
    def setUp(self):
        self.user = make_user("gc")
        self.other = make_user("gc2")
        self.goal = Goal.objects.create(user=self.user, title="هدف", deadline=timezone.localdate())
        self.client.force_login(self.user)

    def complete(self, goal=None):
        return self.client.post(reverse("goals:complete", args=[(goal or self.goal).pk]))

    def test_completes_and_redirects_with_celebration(self):
        response = self.complete()
        self.assertRedirects(response, f"{reverse('goals:detail', args=[self.goal.pk])}?celebrate=1")
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, GoalStatus.COMPLETED)

    def test_requires_post_and_ownership(self):
        self.assertEqual(self.client.get(reverse("goals:complete", args=[self.goal.pk])).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.complete().status_code, 404)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, GoalStatus.ACTIVE)

    def test_already_completed_goal_is_left_alone(self):
        self.goal.status = GoalStatus.ABANDONED
        self.goal.save()
        response = self.complete()
        self.assertRedirects(response, reverse("goals:detail", args=[self.goal.pk]))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, GoalStatus.ABANDONED)

    def test_complete_button_only_for_active_goals(self):
        self.assertContains(self.client.get(reverse("goals:detail", args=[self.goal.pk])), reverse("goals:complete", args=[self.goal.pk]))
        self.goal.status = GoalStatus.COMPLETED
        self.goal.save()
        self.assertNotContains(self.client.get(reverse("goals:detail", args=[self.goal.pk])), reverse("goals:complete", args=[self.goal.pk]))


class HabitDetailTests(TestCase):
    def setUp(self):
        self.user = make_user("hd")
        self.other = make_user("hd2")
        self.today = timezone.localdate()
        self.habit = Habit.objects.create(user=self.user, title="ورزش")
        self.client.force_login(self.user)

    def occurrence(self, days_ago, status):
        return Task.objects.create(user=self.user, habit=self.habit, title="ورزش", date=self.today - dt.timedelta(days=days_ago), status=status)

    def states(self):
        history = habit_history(self.habit, self.today)
        return {c["date"]: c["state"] for col in history["columns"] for c in col["cells"]}

    def test_requires_login_and_ownership(self):
        url = reverse("habits:detail", args=[self.habit.pk])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_grid_shape_and_saturday_start(self):
        from utils.jalali import to_jalali

        history = habit_history(self.habit, self.today)
        self.assertEqual(len(history["columns"]), 12)
        self.assertTrue(all(len(c["cells"]) == 7 for c in history["columns"]))
        self.assertEqual(to_jalali(history["columns"][0]["cells"][0]["date"]).weekday(), 0)

    def test_cell_states(self):
        self.occurrence(1, TaskStatus.DONE)
        self.occurrence(2, TaskStatus.TODO)      # day is over -> missed
        self.occurrence(3, TaskStatus.FAILED)
        self.occurrence(0, TaskStatus.TODO)      # today, still open -> pending
        s = self.states()
        self.assertEqual(s[self.today - dt.timedelta(days=1)], "done")
        self.assertEqual(s[self.today - dt.timedelta(days=2)], "missed")
        self.assertEqual(s[self.today - dt.timedelta(days=3)], "missed")
        self.assertEqual(s[self.today], "pending")
        self.assertEqual(s[self.today - dt.timedelta(days=5)], "none")
        self.assertIn("future", s.values()) if (self.today.weekday() + 2) % 7 != 6 else None

    def test_rate_counts_only_finished_days(self):
        self.occurrence(1, TaskStatus.DONE)
        self.occurrence(2, TaskStatus.DONE)
        self.occurrence(3, TaskStatus.FAILED)
        self.occurrence(0, TaskStatus.TODO)  # pending: not counted either way
        history = habit_history(self.habit, self.today)
        self.assertEqual((history["done"], history["missed"], history["rate"]), (2, 1, 67))
        self.assertTrue(history["has_data"])

    def test_weekday_breakdown_adds_up(self):
        for d in (1, 2, 3, 4):
            self.occurrence(d, TaskStatus.DONE)
        history = habit_history(self.habit, self.today)
        self.assertEqual(sum(w["done"] for w in history["weekdays"]), 4)
        self.assertEqual(len(history["weekdays"]), 7)

    def test_empty_history(self):
        history = habit_history(self.habit, self.today)
        self.assertIsNone(history["rate"])
        self.assertFalse(history["has_data"])
        response = self.client.get(reverse("habits:detail", args=[self.habit.pk]))
        self.assertContains(response, "هنوز تاریخچه‌ای نیست")

    def test_other_habits_tasks_are_ignored(self):
        other = Habit.objects.create(user=self.user, title="مطالعه")
        Task.objects.create(user=self.user, habit=other, title="مطالعه", date=self.today - dt.timedelta(days=1), status=TaskStatus.DONE)
        self.assertEqual(habit_history(self.habit, self.today)["done"], 0)

    def test_page_shows_streaks_and_list_links_here(self):
        self.occurrence(1, TaskStatus.DONE)
        self.occurrence(2, TaskStatus.DONE)
        response = self.client.get(reverse("habits:detail", args=[self.habit.pk]))
        self.assertEqual(response.context["habit"].streak, 2)
        self.assertEqual(response.context["habit"].best_streak, 2)
        self.assertContains(response, "heat-cell hs-done")
        self.assertContains(self.client.get(reverse("habits:list")), reverse("habits:detail", args=[self.habit.pk]))


class InsightsTests(TestCase):
    def setUp(self):
        self.user = make_user("ins")
        self.today = timezone.localdate()

    def done_on(self, days_ago, start=None, n=1):
        for i in range(n):
            Task.objects.create(user=self.user, title=f"t{days_ago}-{i}", date=self.today - dt.timedelta(days=days_ago), status=TaskStatus.DONE, start_time=start)

    def keys(self):
        return {i["key"] for i in compute_insights(self.user, self.today)}

    def test_nothing_for_a_new_account(self):
        self.assertEqual(compute_insights(self.user, self.today), [])

    def test_weekday_needs_enough_done_tasks(self):
        self.done_on(1, n=MIN_DONE_FOR_WEEKDAY - 1)
        self.assertNotIn("weekday", self.keys())
        self.done_on(8, n=1)
        self.assertIn("weekday", self.keys())

    def test_weekday_names_the_busiest_day(self):
        from utils.jalali import JALALI_WEEKDAYS, to_jalali

        target = self.today - dt.timedelta(days=3)
        self.done_on(3, n=8)
        self.done_on(4, n=2)
        item = next(i for i in compute_insights(self.user, self.today) if i["key"] == "weekday")
        self.assertIn(JALALI_WEEKDAYS[to_jalali(target).weekday()], item["text"])

    def test_old_tasks_are_outside_the_window(self):
        self.done_on(120, n=20)
        self.assertEqual(compute_insights(self.user, self.today), [])

    def test_time_of_day_buckets(self):
        self.assertEqual(_bucket_for(dt.time(8, 0)), "صبح")
        self.assertEqual(_bucket_for(dt.time(14, 0)), "ظهر و بعدازظهر")
        self.assertEqual(_bucket_for(dt.time(19, 0)), "عصر")
        self.assertEqual(_bucket_for(dt.time(23, 0)), "شب")
        self.assertEqual(_bucket_for(dt.time(2, 0)), "شب")
        self.assertEqual(_bucket_for(dt.time(4, 59)), "شب")
        self.assertEqual(_bucket_for(dt.time(5, 0)), "صبح")

    def test_time_of_day_insight_needs_timed_tasks(self):
        self.done_on(1, start=None, n=MIN_TIMED_FOR_TIME_OF_DAY + 3)
        self.assertNotIn("time", self.keys())
        self.done_on(2, start=dt.time(8, 0), n=MIN_TIMED_FOR_TIME_OF_DAY)
        item = next(i for i in compute_insights(self.user, self.today) if i["key"] == "time")
        self.assertIn("صبح", item["text"])

    def _mood_day(self, days_ago, mood, done, total):
        day = self.today - dt.timedelta(days=days_ago)
        DayNote.objects.create(user=self.user, date=day, mood=mood)
        for i in range(total):
            Task.objects.create(user=self.user, title=f"m{days_ago}-{i}", date=day, status=TaskStatus.DONE if i < done else TaskStatus.TODO)

    def test_mood_comparison_needs_both_groups(self):
        for d in range(MIN_DAYS_PER_MOOD_GROUP):
            self._mood_day(d + 1, 5, 4, 4)
        self.assertNotIn("mood", self.keys())
        for d in range(MIN_DAYS_PER_MOOD_GROUP):
            self._mood_day(d + 10, 1, 1, 4)
        item = next(i for i in compute_insights(self.user, self.today) if i["key"] == "mood")
        self.assertIn("۱۰۰٪", item["text"])
        self.assertIn("۲۵٪", item["text"])

    def test_mood_days_without_tasks_do_not_count(self):
        for d in range(5):
            DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=d + 1), mood=5)
        for d in range(5):
            DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=d + 10), mood=1)
        self.assertNotIn("mood", self.keys())

    def test_other_users_data_is_ignored(self):
        other = make_user("someone")
        for i in range(30):
            Task.objects.create(user=other, title=f"x{i}", date=self.today, status=TaskStatus.DONE, start_time=dt.time(9))
        self.assertEqual(compute_insights(self.user, self.today), [])


class ShortcutMarkupTests(TestCase):
    def test_drawer_links_carry_unique_chord_keys(self):
        import re

        user = make_user("keys")
        self.client.force_login(user)
        html = self.client.get(reverse("core:home")).content.decode()
        keys = re.findall(r'data-cmd data-key="(\w)"', html)
        self.assertGreaterEqual(len(keys), 10)
        self.assertEqual(len(keys), len(set(keys)), "chord keys must be unique")

    def test_new_pages_render_for_a_signed_in_user(self):
        user = make_user("pages4")
        self.client.force_login(user)
        goal = Goal.objects.create(user=user, title="هدف", deadline=timezone.localdate())
        habit = Habit.objects.create(user=user, title="عادت")
        for url in (reverse("goals:detail", args=[goal.pk]), reverse("habits:detail", args=[habit.pk]),
                    reverse("core:focus"), reverse("core:stats")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class GoalPaceWordingTests(TestCase):
    def setUp(self):
        self.user = make_user("pace")
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def pace(self, open_tasks, days_left):
        goal = Goal.objects.create(user=self.user, title=f"g{open_tasks}-{days_left}", deadline=self.today + dt.timedelta(days=days_left))
        for i in range(open_tasks):
            Task.objects.create(user=self.user, goal=goal, title=f"t{i}", date=self.today)
        ctx = self.client.get(reverse("goals:detail", args=[goal.pk])).context
        return ctx["pace_count"], ctx["pace_unit"]

    def test_daily_unit_when_at_least_one_per_day(self):
        self.assertEqual(self.pace(10, 5), (2, "روز"))
        self.assertEqual(self.pace(5, 5), (1, "روز"))

    def test_weekly_unit_when_less_than_one_per_day(self):
        self.assertEqual(self.pace(3, 14), (2, "هفته"))
        self.assertEqual(self.pace(1, 30), (1, "هفته"))

    def test_no_pace_without_open_tasks_or_when_due_today(self):
        self.assertEqual(self.pace(0, 5), (None, None))
        self.assertEqual(self.pace(3, 0), (None, None))
