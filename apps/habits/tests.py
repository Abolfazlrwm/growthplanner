import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.goals.models import Goal
from apps.tasks.models import Task, TaskStatus
from utils.jalali import to_jalali

from .models import Habit
from .services import habit_best_streak, habit_streak, sync_habits_for_date, sync_habits_for_range

User = get_user_model()


class HabitModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")

    def test_empty_weekdays_means_every_day(self):
        habit = Habit.objects.create(user=self.user, title="مدیتیشن")
        self.assertTrue(habit.occurs_on(0))
        self.assertTrue(habit.occurs_on(6))

    def test_specific_weekdays_are_respected(self):
        habit = Habit.objects.create(user=self.user, title="باشگاه", weekdays="0,2,4")
        self.assertTrue(habit.occurs_on(0))
        self.assertFalse(habit.occurs_on(1))
        self.assertEqual(habit.weekday_list, [0, 2, 4])

    def test_goal_must_belong_to_same_user(self):
        other = User.objects.create_user("sara", password="pass12345")
        goal = Goal.objects.create(user=other, title="هدف سارا", deadline=dt.date(2026, 12, 1))
        habit = Habit(user=self.user, goal=goal, title="ورزش")
        with self.assertRaises(ValidationError):
            habit.full_clean()


class SyncHabitsForDateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.day = dt.date(2026, 9, 27)
        cls.weekday = to_jalali(cls.day).weekday()

    def test_daily_habit_creates_a_task(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        created = sync_habits_for_date(self.user, self.day)
        self.assertEqual(len(created), 1)
        self.assertTrue(Task.objects.filter(user=self.user, date=self.day, habit=habit).exists())

    def test_inactive_habit_is_skipped(self):
        Habit.objects.create(user=self.user, title="آب خوردن", active=False)
        created = sync_habits_for_date(self.user, self.day)
        self.assertEqual(created, [])

    def test_habit_scheduled_on_other_weekdays_is_skipped(self):
        other_weekday = (self.weekday + 1) % 7
        Habit.objects.create(user=self.user, title="باشگاه", weekdays=str(other_weekday))
        created = sync_habits_for_date(self.user, self.day)
        self.assertEqual(created, [])

    def test_running_twice_does_not_duplicate_the_task(self):
        Habit.objects.create(user=self.user, title="آب خوردن")
        sync_habits_for_date(self.user, self.day)
        sync_habits_for_date(self.user, self.day)
        self.assertEqual(Task.objects.filter(user=self.user, date=self.day).count(), 1)

    def test_only_generates_for_the_requested_user(self):
        Habit.objects.create(user=self.other, title="آب خوردن")
        sync_habits_for_date(self.user, self.day)
        self.assertFalse(Task.objects.filter(user=self.user).exists())

    def test_deleting_a_generated_task_lets_it_regenerate_next_sync(self):
        Habit.objects.create(user=self.user, title="آب خوردن")
        sync_habits_for_date(self.user, self.day)
        Task.objects.filter(user=self.user, date=self.day).delete()
        sync_habits_for_date(self.user, self.day)
        self.assertEqual(Task.objects.filter(user=self.user, date=self.day).count(), 1)


class HabitViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")

    def setUp(self):
        self.client.login(username="ali", password="pass12345")

    def test_anonymous_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("habits:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_only_shows_own_habits(self):
        Habit.objects.create(user=self.user, title="مال من")
        Habit.objects.create(user=self.other, title="مال دیگری")
        response = self.client.get(reverse("habits:list"))
        self.assertEqual(len(response.context["habits"]), 1)

    def test_create_sets_current_user(self):
        response = self.client.post(
            reverse("habits:create"),
            {"title": "دویدن", "weekdays": [], "active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Habit.objects.get().user, self.user)

    def test_toggle_flips_active_state(self):
        habit = Habit.objects.create(user=self.user, title="دویدن", active=True)
        self.client.post(reverse("habits:toggle", args=[habit.pk]))
        habit.refresh_from_db()
        self.assertFalse(habit.active)

    def test_cannot_toggle_other_users_habit(self):
        habit = Habit.objects.create(user=self.other, title="مال دیگری", active=True)
        response = self.client.post(reverse("habits:toggle", args=[habit.pk]))
        self.assertEqual(response.status_code, 404)
        habit.refresh_from_db()
        self.assertTrue(habit.active)

    def test_delete_own_habit(self):
        habit = Habit.objects.create(user=self.user, title="دویدن")
        self.client.post(reverse("habits:delete", args=[habit.pk]))
        self.assertFalse(Habit.objects.filter(pk=habit.pk).exists())

    def test_list_annotates_each_habit_with_its_streak(self):
        from django.utils import timezone
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        today = timezone.localdate()
        Task.objects.create(user=self.user, habit=habit, date=today, status=TaskStatus.DONE, title="x")
        Task.objects.create(
            user=self.user, habit=habit, date=today - dt.timedelta(days=1),
            status=TaskStatus.DONE, title="x",
        )
        response = self.client.get(reverse("habits:list"))
        [shown] = response.context["habits"]
        self.assertEqual(shown.streak, 2)


class SyncHabitsForRangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.start = dt.date(2026, 9, 20)
        cls.end = dt.date(2026, 9, 30)

    def test_creates_tasks_on_every_scheduled_day_in_the_range(self):
        Habit.objects.create(user=self.user, title="آب خوردن")  # every day
        sync_habits_for_range(self.user, self.start, self.end)
        expected_days = (self.end - self.start).days + 1
        self.assertEqual(Task.objects.filter(user=self.user).count(), expected_days)

    def test_respects_specific_weekdays_across_the_range(self):
        target_weekday = to_jalali(self.start).weekday()
        Habit.objects.create(user=self.user, title="باشگاه", weekdays=str(target_weekday))
        sync_habits_for_range(self.user, self.start, self.end)
        for task in Task.objects.filter(user=self.user):
            self.assertEqual(to_jalali(task.date).weekday(), target_weekday)

    def test_does_not_duplicate_tasks_already_created_individually(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        sync_habits_for_date(self.user, self.start)  # one day already synced the normal way
        sync_habits_for_range(self.user, self.start, self.end)
        self.assertEqual(Task.objects.filter(user=self.user, date=self.start, habit=habit).count(), 1)

    def test_no_active_habits_means_no_queries_needed_and_nothing_created(self):
        created = sync_habits_for_range(self.user, self.start, self.end)
        self.assertEqual(created, [])
        self.assertFalse(Task.objects.exists())


class HabitStreakTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.today = dt.date(2026, 9, 27)

    def make_done(self, habit, date):
        Task.objects.create(user=self.user, habit=habit, date=date, status=TaskStatus.DONE, title="x")

    def test_no_completed_days_is_zero(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        self.assertEqual(habit_streak(habit, self.today), 0)

    def test_counts_consecutive_done_days_ending_today(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        for offset in range(3):
            self.make_done(habit, self.today - dt.timedelta(days=offset))
        self.assertEqual(habit_streak(habit, self.today), 3)

    def test_today_not_done_yet_still_counts_yesterday_onward(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        self.make_done(habit, self.today - dt.timedelta(days=1))
        self.make_done(habit, self.today - dt.timedelta(days=2))
        self.assertEqual(habit_streak(habit, self.today), 2)

    def test_a_gap_breaks_the_streak(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        self.make_done(habit, self.today)
        self.make_done(habit, self.today - dt.timedelta(days=2))  # yesterday missing
        self.assertEqual(habit_streak(habit, self.today), 1)

    def test_other_habits_tasks_do_not_count(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        other_habit = Habit.objects.create(user=self.user, title="باشگاه")
        self.make_done(other_habit, self.today)
        self.assertEqual(habit_streak(habit, self.today), 0)


class HabitApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        Habit.objects.create(user=cls.user, title="مال من", weekdays="0,2")
        Habit.objects.create(user=cls.other, title="مال دیگری")

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get("/api/habits/").status_code, 403)

    def test_list_only_returns_own_habits(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/habits/")
        titles = [h["title"] for h in response.json()["results"]]
        self.assertEqual(titles, ["مال من"])

    def test_weekdays_are_exposed_as_a_list_of_ints(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/habits/")
        self.assertEqual(response.json()["results"][0]["weekdays"], [0, 2])

    def test_create_via_api_sets_user_and_accepts_a_weekdays_list(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/habits/", {"title": "جدید", "weekdays": [1, 3]}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        habit = Habit.objects.get(title="جدید")
        self.assertEqual(habit.user, self.user)
        self.assertEqual(habit.weekday_list, [1, 3])

    def test_cannot_attach_another_users_goal_via_api(self):
        other_goal = Goal.objects.create(user=self.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/habits/", {"title": "x", "goal": other_goal.pk}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class HabitBestStreakTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")

    def make_done(self, habit, date):
        Task.objects.create(user=self.user, habit=habit, date=date, status=TaskStatus.DONE, title="x")

    def test_no_done_days_is_zero(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        self.assertEqual(habit_best_streak(habit), 0)

    def test_best_streak_is_the_longest_run_not_the_most_recent(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        base = dt.date(2026, 9, 1)
        # A 4-day run early on...
        for offset in range(4):
            self.make_done(habit, base + dt.timedelta(days=offset))
        # ...then a gap, then only a 2-day run more recently.
        self.make_done(habit, base + dt.timedelta(days=20))
        self.make_done(habit, base + dt.timedelta(days=21))
        self.assertEqual(habit_best_streak(habit), 4)

    def test_single_day_gives_streak_of_one(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        self.make_done(habit, dt.date(2026, 9, 1))
        self.assertEqual(habit_best_streak(habit), 1)

    def test_other_habits_are_not_mixed_in(self):
        habit = Habit.objects.create(user=self.user, title="آب خوردن")
        other = Habit.objects.create(user=self.user, title="باشگاه")
        base = dt.date(2026, 9, 1)
        for offset in range(5):
            self.make_done(other, base + dt.timedelta(days=offset))
        self.assertEqual(habit_best_streak(habit), 0)


class HabitApiPriorityFieldTests(TestCase):
    """Sanity check that the Task API's new `priority` field doesn't break habit-generated tasks."""

    def test_sync_created_task_defaults_to_medium_priority(self):
        user = User.objects.create_user("ali", password="pass12345")
        habit = Habit.objects.create(user=user, title="آب خوردن")
        [task] = sync_habits_for_date(user, dt.date(2026, 9, 24))
        self.assertEqual(task.priority, "medium")
