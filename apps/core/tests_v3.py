"""Tests for task rescheduling, the week board, the journal archive, achievements and the Today extras."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.badges import BADGES, compute_badges
from apps.core.views import _next_up, _onboarding, _sparkline
from apps.goals.models import Goal, GoalStatus
from apps.habits.models import Habit
from apps.journal.models import DayNote
from apps.tasks.models import Task, TaskStatus
from utils.jalali import to_jalali

User = get_user_model()


class RescheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("sara", password="pass12345")
        cls.other = User.objects.create_user("omid", password="pass12345")
        cls.today = timezone.localdate()
        cls.tomorrow = cls.today + dt.timedelta(days=3)

    def setUp(self):
        self.client.force_login(self.user)
        self.task = Task.objects.create(user=self.user, title="گزارش", date=self.today)

    def post(self, task, date):
        return self.client.post(reverse("tasks:reschedule", args=[task.pk]), {"date": date})

    def test_moves_the_task_and_returns_its_row(self):
        response = self.post(self.task, self.tomorrow.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گزارش")
        self.task.refresh_from_db()
        self.assertEqual(self.task.date, self.tomorrow)
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_requires_login_and_post(self):
        self.client.logout()
        response = self.post(self.task, self.tomorrow.isoformat())
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("tasks:reschedule", args=[self.task.pk])).status_code, 405)

    def test_cannot_touch_someone_elses_task(self):
        theirs = Task.objects.create(user=self.other, title="x", date=self.today)
        self.assertEqual(self.post(theirs, self.tomorrow.isoformat()).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.date, self.today)

    def test_rejects_bad_and_absurd_dates(self):
        self.assertEqual(self.post(self.task, "not-a-date").status_code, 400)
        self.assertEqual(self.post(self.task, "").status_code, 400)
        self.assertEqual(self.post(self.task, "3026-01-01").status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.date, self.today)

    def test_habit_tasks_are_refused(self):
        habit = Habit.objects.create(user=self.user, title="آب")
        task = Task.objects.create(user=self.user, title="آب", date=self.today, habit=habit)
        response = self.post(task, self.tomorrow.isoformat())
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.date, self.today)

    def test_finished_tasks_are_refused(self):
        for status in (TaskStatus.DONE, TaskStatus.FAILED):
            task = Task.objects.create(user=self.user, title=f"t-{status}", date=self.today, status=status)
            self.assertEqual(self.post(task, self.tomorrow.isoformat()).status_code, 400)

    def test_open_row_offers_the_date_button_but_habit_row_does_not(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("tasks:reschedule", args=[self.task.pk]))
        habit = Habit.objects.create(user=self.user, title="ورزش")
        habit_task = Task.objects.create(user=self.user, title="ورزش", date=self.today, habit=habit)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, reverse("tasks:reschedule", args=[habit_task.pk]))


class WeekBoardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("nina", password="pass12345")
        cls.other = User.objects.create_user("kian", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar_view:week")).status_code, 302)

    def test_seven_days_starting_on_a_persian_saturday(self):
        days = self.client.get(reverse("calendar_view:week")).context["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(to_jalali(days[0]["date"]).weekday(), 0)
        self.assertEqual(days[6]["date"] - days[0]["date"], dt.timedelta(days=6))
        self.assertTrue(days[6]["is_friday"])
        self.assertEqual([d["is_today"] for d in days].count(True), 1)

    def test_tasks_land_on_their_day_and_only_mine_show(self):
        start = self.client.get(reverse("calendar_view:week")).context["week_start"]
        Task.objects.create(user=self.user, title="شنبه‌کار", date=start)
        Task.objects.create(user=self.user, title="جمعه‌کار", date=start + dt.timedelta(days=6), status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="کارِ ماه آینده", date=start + dt.timedelta(days=7))
        Task.objects.create(user=self.other, title="مال دیگری", date=start)
        response = self.client.get(reverse("calendar_view:week"))
        days = response.context["days"]
        self.assertEqual([t.title for t in days[0]["tasks"]], ["شنبه‌کار"])
        self.assertEqual([t.title for t in days[6]["tasks"]], ["جمعه‌کار"])
        self.assertEqual((days[6]["done"], days[6]["percent"]), (1, 100))
        self.assertEqual((response.context["week_total"], response.context["week_done"], response.context["week_percent"]), (2, 1, 50))
        self.assertNotContains(response, "مال دیگری")
        self.assertNotContains(response, "کارِ ماه آینده")

    def test_navigation_and_anchor_date(self):
        anchor = dt.date(2026, 1, 15)
        response = self.client.get(reverse("calendar_view:week", args=[anchor.isoformat()]))
        ctx = response.context
        self.assertLessEqual(ctx["week_start"], anchor)
        self.assertLessEqual(anchor, ctx["week_start"] + dt.timedelta(days=6))
        self.assertEqual(ctx["next_week"] - ctx["prev_week"], dt.timedelta(days=14))
        self.assertFalse(ctx["is_current_week"])
        self.assertContains(response, reverse("calendar_view:week"))  # "this week" shortcut

    def test_bad_date_is_404(self):
        self.assertEqual(self.client.get(reverse("calendar_view:week", args=["nope"])).status_code, 404)

    def test_habits_are_synced_for_the_visible_week(self):
        Habit.objects.create(user=self.user, title="آب خوردن")  # every day
        days = self.client.get(reverse("calendar_view:week")).context["days"]
        self.assertTrue(all(any(t.title == "آب خوردن" for t in d["tasks"]) for d in days))

    def test_every_day_has_a_quick_add_form_for_its_own_date(self):
        response = self.client.get(reverse("calendar_view:week"))
        for day in response.context["days"]:
            self.assertContains(response, f'name="date" value="{day["date"].isoformat()}"')


class JournalArchiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("mina", password="pass12345")
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def note(self, days_ago, text="", mood=None, user=None):
        return DayNote.objects.create(user=user or self.user, date=self.today - dt.timedelta(days=days_ago), text=text, mood=mood)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("journal:list")).status_code, 302)

    def test_lists_only_my_non_empty_notes_newest_first(self):
        self.note(3, "قدیمی")
        self.note(1, "تازه", mood=4)
        self.note(2, "", mood=None)  # nothing to show
        self.note(0, "مال دیگری", user=self.other)
        response = self.client.get(reverse("journal:list"))
        self.assertEqual([n.text for n in response.context["page"]], ["تازه", "قدیمی"])
        self.assertEqual(response.context["total_notes"], 2)
        self.assertNotContains(response, "مال دیگری")

    def test_mood_only_entry_is_kept(self):
        self.note(1, "", mood=5)
        self.assertEqual(len(self.client.get(reverse("journal:list")).context["page"]), 1)

    def test_search_filters_by_text(self):
        self.note(1, "امروز کوه رفتم")
        self.note(2, "روز شلوغی بود")
        response = self.client.get(reverse("journal:list"), {"q": "کوه"})
        self.assertEqual([n.text for n in response.context["page"]], ["امروز کوه رفتم"])
        empty = self.client.get(reverse("journal:list"), {"q": "چیزی نیست"})
        self.assertContains(empty, "یادداشتی با این عبارت نیست")

    def test_pagination(self):
        for i in range(20):
            self.note(i, f"یادداشت {i}")
        first = self.client.get(reverse("journal:list")).context["page"]
        self.assertEqual(len(first), 15)
        second = self.client.get(reverse("journal:list"), {"page": 2}).context["page"]
        self.assertEqual(len(second), 5)

    def test_mood_strip_covers_30_days_and_averages(self):
        self.note(0, "الف", mood=5)
        self.note(1, "ب", mood=3)
        self.note(45, "قدیمی", mood=1)  # outside the strip
        ctx = self.client.get(reverse("journal:list")).context
        self.assertEqual(len(ctx["strip"]), 30)
        self.assertEqual(ctx["strip"][-1]["date"], self.today)
        self.assertEqual(ctx["mood_avg"], 4.0)
        self.assertEqual(ctx["mood_days"], 2)

    def test_empty_state(self):
        self.assertContains(self.client.get(reverse("journal:list")), "دفترت هنوز خالی است")


class BadgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("badge", password="pass12345")
        cls.today = timezone.localdate()

    def by_key(self, streak=0):
        return {b["key"]: b for b in compute_badges(self.user, streak)}

    def test_nothing_earned_for_a_new_account(self):
        badges = compute_badges(self.user, 0)
        self.assertEqual(len(badges), len(BADGES))
        self.assertFalse(any(b["earned"] for b in badges))
        self.assertTrue(all(b["percent"] == 0 for b in badges))

    def test_done_tasks_progress_and_cap(self):
        for i in range(10):
            Task.objects.create(user=self.user, title=f"t{i}", date=self.today, status=TaskStatus.DONE)
        Task.objects.create(user=self.user, title="باز", date=self.today)
        b = self.by_key()
        self.assertTrue(b["first-step"]["earned"] and b["ten-done"]["earned"])
        self.assertFalse(b["hundred-done"]["earned"])
        self.assertEqual((b["hundred-done"]["current"], b["hundred-done"]["percent"]), (10, 10))
        self.assertEqual(b["ten-done"]["current"], 10)  # capped at the target

    def test_streak_badges_use_the_given_streak(self):
        self.assertTrue(self.by_key(7)["week-streak"]["earned"])
        self.assertFalse(self.by_key(7)["month-streak"]["earned"])
        self.assertTrue(self.by_key(30)["month-streak"]["earned"])

    def test_goal_habit_and_note_badges(self):
        Goal.objects.create(user=self.user, title="الف", deadline=self.today)
        Goal.objects.create(user=self.user, title="ب", deadline=self.today, status=GoalStatus.COMPLETED)
        Habit.objects.create(user=self.user, title="ورزش")
        for i in range(3):
            DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=i), text="متن")
        DayNote.objects.create(user=self.user, date=self.today - dt.timedelta(days=9), text="", mood=3)  # no text → not counted
        b = self.by_key()
        self.assertTrue(b["goal-setter"]["earned"] and b["goal-reached"]["earned"] and b["habit-builder"]["earned"])
        self.assertEqual(b["writer"]["current"], 3)
        self.assertFalse(b["writer"]["earned"])

    def test_other_users_data_is_ignored(self):
        other = User.objects.create_user("other", password="pass12345")
        Task.objects.create(user=other, title="x", date=self.today, status=TaskStatus.DONE)
        self.assertFalse(self.by_key()["first-step"]["earned"])

    def test_stats_page_shows_achievements(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:stats"))
        self.assertContains(response, "دستاوردها")
        self.assertEqual(response.context["badges_earned"], 0)
        self.assertTrue(response.context["week_spark"])


class SparklineTests(SimpleTestCase):
    def test_points(self):
        self.assertEqual(_sparkline([0, 100]), "0.0,27.0 100.0,3.0")
        self.assertEqual(len(_sparkline([10] * 7).split()), 7)

    def test_too_few_values(self):
        self.assertEqual(_sparkline([]), "")
        self.assertEqual(_sparkline([50]), "")


class NextUpTests(SimpleTestCase):
    def task(self, title, start=None, status=TaskStatus.TODO):
        return Task(title=title, start_time=start, status=status)

    def test_picks_the_earliest_upcoming_timed_task(self):
        tasks = [self.task("دیر", dt.time(18)), self.task("زود", dt.time(14)), self.task("گذشته", dt.time(8))]
        self.assertEqual(_next_up(tasks, dt.time(12)).title, "زود")

    def test_falls_back_to_a_task_in_progress(self):
        tasks = [self.task("گذشته", dt.time(8)), self.task("در جریان", None, TaskStatus.IN_PROGRESS)]
        self.assertEqual(_next_up(tasks, dt.time(12)).title, "در جریان")

    def test_ignores_finished_tasks_and_returns_none_when_nothing_fits(self):
        tasks = [self.task("تمام", dt.time(15), TaskStatus.DONE), self.task("بی‌ساعت")]
        self.assertIsNone(_next_up(tasks, dt.time(12)))


class OnboardingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("new", password="pass12345")
        cls.today = timezone.localdate()

    def test_new_account_has_nothing_done(self):
        ob = _onboarding(self.user)
        self.assertEqual((ob["done"], ob["total"], ob["percent"], ob["complete"]), (0, 4, 0, False))

    def test_steps_tick_from_real_data_and_complete(self):
        Goal.objects.create(user=self.user, title="هدف", deadline=self.today)
        Habit.objects.create(user=self.user, title="عادت")
        Task.objects.create(user=self.user, title="تسک", date=self.today, status=TaskStatus.DONE)
        self.assertEqual(_onboarding(self.user)["done"], 3)
        DayNote.objects.create(user=self.user, date=self.today, text="سلام")
        ob = _onboarding(self.user)
        self.assertTrue(ob["complete"])
        self.assertEqual(ob["percent"], 100)

    def test_card_is_shown_until_complete(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("core:home")), "شروع سریع")
        Goal.objects.create(user=self.user, title="هدف", deadline=self.today)
        Habit.objects.create(user=self.user, title="عادت")
        Task.objects.create(user=self.user, title="تسک", date=self.today, status=TaskStatus.DONE)
        DayNote.objects.create(user=self.user, date=self.today, text="سلام")
        self.assertNotContains(self.client.get(reverse("core:home")), "شروع سریع")

    def test_home_shows_streak_chip_and_week_link(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("calendar_view:week"))
        self.assertEqual(response.context["streak"], 0)
        self.assertNotContains(response, "روز متوالی")


class FormMixinRegressionTests(TestCase):
    """The shared form mixin once validated forms inside __init__, before TaskForm had
    restricted its goal queryset, which turned every valid quick-add into a 422."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("form", password="pass12345")
        cls.today = timezone.localdate()

    def test_user_scoped_task_form_validates_with_the_users_own_goal(self):
        from apps.tasks.forms import TaskForm

        goal = Goal.objects.create(user=self.user, title="هدف", deadline=self.today)
        form = TaskForm({"title": "تسک", "goal": goal.pk, "priority": "medium", "date": self.today.isoformat()}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_goal_of_another_user_is_still_rejected(self):
        from apps.tasks.forms import TaskForm

        other = User.objects.create_user("someone", password="pass12345")
        goal = Goal.objects.create(user=other, title="مال دیگری", deadline=self.today)
        form = TaskForm({"title": "تسک", "goal": goal.pk, "priority": "medium", "date": self.today.isoformat()}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("goal", form.errors)

    def test_invalid_fields_are_flagged_for_screen_readers_after_validation(self):
        from apps.tasks.forms import TaskForm

        form = TaskForm({"title": "", "priority": "medium", "date": self.today.isoformat()}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.fields["title"].widget.attrs.get("aria-invalid"), "true")
        self.assertNotIn("aria-invalid", form.fields["priority"].widget.attrs)
        self.assertEqual(form.fields["title"].widget.attrs["class"], "field")

    def test_unbound_form_has_no_aria_invalid(self):
        from apps.tasks.forms import TaskForm

        form = TaskForm(user=self.user)
        self.assertTrue(all("aria-invalid" not in f.widget.attrs for f in form.fields.values()))


class NoteHeadingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("heading", password="pass12345")
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def test_heading_says_today_only_for_today(self):
        today = self.client.post(reverse("journal:save", args=[self.today.isoformat()]), {"mood": "", "text": "سلام"})
        self.assertContains(today, "یادداشت و حال‌وهوای امروز")
        past = (self.today - dt.timedelta(days=5)).isoformat()
        other = self.client.post(reverse("journal:save", args=[past]), {"mood": "", "text": "سلام"})
        self.assertContains(other, "یادداشت و حال‌وهوای این روز")
        self.assertNotContains(other, "حال‌وهوای امروز")

    def test_day_pages_use_the_right_heading(self):
        self.assertContains(self.client.get(reverse("tasks:list")), "یادداشت و حال‌وهوای امروز")
        past = (self.today - dt.timedelta(days=3)).isoformat()
        self.assertContains(self.client.get(reverse("tasks:list"), {"date": past}), "یادداشت و حال‌وهوای این روز")

    def test_home_heading_is_today(self):
        self.assertContains(self.client.get(reverse("core:home")), "یادداشت و حال‌وهوای امروز")


class TemplateLibraryLoadTests(TestCase):
    """Every signed-in page must render; this catches a missing {% load %} the moment it happens."""

    def test_every_main_page_renders_for_a_signed_in_user(self):
        user = User.objects.create_user("pages", password="pass12345")
        self.client.force_login(user)
        for name in ("core:home", "core:stats", "core:focus", "tasks:list", "tasks:search", "goals:list", "goals:create",
                     "habits:list", "habits:create", "calendar_view:month", "calendar_view:week",
                     "calendar_view:timeline", "journal:list", "accounts:settings", "accounts:password_change"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_empty_and_filled_habit_list_both_render(self):
        user = User.objects.create_user("habits", password="pass12345")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("habits:list")), "هنوز عادتی نساخته‌ای")
        Habit.objects.create(user=user, title="ورزش صبحگاهی")
        self.assertContains(self.client.get(reverse("habits:list")), "ورزش صبحگاهی")


class TaskPriorityOptionalTests(TestCase):
    """A post without `priority` used to be a 422 (the field became required when priority was
    added); it now falls back to "medium", while a bogus value is still rejected."""

    def setUp(self):
        self.user = User.objects.create_user("prio", password="pass12345")
        self.client.force_login(self.user)
        self.today = timezone.localdate().isoformat()

    def post(self, **extra):
        data = {"title": "تسک", "goal": "", "date": self.today, "start_time": "", "end_time": ""}
        data.update(extra)
        return self.client.post(reverse("tasks:create"), data)

    def test_missing_priority_defaults_to_medium(self):
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(Task.objects.get(user=self.user).priority, "medium")

    def test_blank_priority_defaults_to_medium(self):
        self.assertEqual(self.post(priority="").status_code, 200)
        self.assertEqual(Task.objects.get(user=self.user).priority, "medium")

    def test_explicit_priority_is_kept(self):
        self.assertEqual(self.post(priority="high").status_code, 200)
        self.assertEqual(Task.objects.get(user=self.user).priority, "high")

    def test_invalid_priority_is_still_rejected(self):
        response = self.post(priority="urgent")
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Task.objects.filter(user=self.user).exists())

    def test_time_range_error_is_a_real_422_not_a_side_effect_of_a_missing_field(self):
        response = self.post(start_time="10:00", end_time="09:00")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "field-error", status_code=422)
