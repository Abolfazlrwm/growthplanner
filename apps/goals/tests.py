import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tasks.models import Task, TaskStatus

from .models import Goal, GoalStatus

User = get_user_model()


class GoalProgressTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.goal = Goal.objects.create(
            user=cls.user, title="یادگیری Django", deadline=dt.date(2026, 12, 1)
        )

    def add_task(self, status, goal=None):
        return Task.objects.create(
            user=self.user, goal=goal or self.goal, title="t",
            date=dt.date(2026, 9, 24), status=status,
        )

    def test_no_tasks_means_zero_percent(self):
        self.assertEqual(self.goal.progress_percent, 0)

    def test_progress_is_done_divided_by_all_tasks(self):
        self.add_task(TaskStatus.DONE)
        self.add_task(TaskStatus.TODO)
        self.add_task(TaskStatus.FAILED)
        self.add_task(TaskStatus.MOVED)
        self.assertEqual(self.goal.progress_percent, 25)

    def test_all_done_is_hundred_percent(self):
        self.add_task(TaskStatus.DONE)
        self.add_task(TaskStatus.DONE)
        self.assertEqual(self.goal.progress_percent, 100)

    def test_tasks_of_other_goals_are_ignored(self):
        other = Goal.objects.create(user=self.user, title="هدف دیگر", deadline=dt.date(2026, 12, 1))
        self.add_task(TaskStatus.DONE, goal=other)
        self.add_task(TaskStatus.TODO)
        self.assertEqual(self.goal.progress_percent, 0)


class GoalViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.goal = Goal.objects.create(user=cls.user, title="هدف من", deadline=dt.date(2026, 12, 1))
        cls.other_goal = Goal.objects.create(user=cls.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))

    def test_anonymous_is_redirected(self):
        self.assertEqual(self.client.get(reverse("goals:list")).status_code, 302)

    def test_list_only_shows_own_goals(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("goals:list"))
        goals = list(response.context["goals"])
        self.assertIn(self.goal, goals)
        self.assertNotIn(self.other_goal, goals)

    def test_create_sets_current_user(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("goals:create"),
            {"title": "هدف جدید", "description": "", "deadline": "2026-12-31", "status": "active"},
        )
        self.assertTrue(Goal.objects.filter(user=self.user, title="هدف جدید").exists())

    def test_cannot_edit_other_users_goal(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("goals:edit", args=[self.other_goal.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_other_users_goal(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("goals:delete", args=[self.other_goal.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Goal.objects.filter(pk=self.other_goal.pk).exists())

    def test_delete_own_goal(self):
        self.client.force_login(self.user)
        self.client.post(reverse("goals:delete", args=[self.goal.pk]))
        self.assertFalse(Goal.objects.filter(pk=self.goal.pk).exists())


class GoalApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.goal = Goal.objects.create(user=cls.user, title="هدف من", deadline=dt.date(2026, 12, 1))
        Goal.objects.create(user=cls.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get("/api/goals/").status_code, 403)

    def test_list_only_returns_own_goals(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/goals/")
        titles = [g["title"] for g in response.json()["results"]]
        self.assertEqual(titles, ["هدف من"])

    def test_create_via_api_sets_user(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/goals/",
            {"title": "از API", "deadline": "2026-12-31", "status": "active"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Goal.objects.get(title="از API").user, self.user)

    def test_progress_percent_is_read_only(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/api/goals/{self.goal.pk}/")
        self.assertIn("progress_percent", response.json())


class GoalFilterAndSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.active = Goal.objects.create(
            user=cls.user, title="یادگیری Django", deadline=dt.date(2026, 12, 1),
        )
        cls.completed = Goal.objects.create(
            user=cls.user, title="یادگیری Git", deadline=dt.date(2026, 6, 1),
            status=GoalStatus.COMPLETED,
        )
        cls.abandoned = Goal.objects.create(
            user=cls.user, title="یادگیری Rust", deadline=dt.date(2026, 3, 1),
            status=GoalStatus.ABANDONED,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_default_tab_shows_only_active(self):
        response = self.client.get(reverse("goals:list"))
        self.assertEqual(list(response.context["goals"]), [self.active])
        self.assertEqual(response.context["current_status"], "active")

    def test_archive_tab_shows_completed_and_abandoned_only(self):
        response = self.client.get(reverse("goals:list"), {"status": "archive"})
        goals = list(response.context["goals"])
        self.assertIn(self.completed, goals)
        self.assertIn(self.abandoned, goals)
        self.assertNotIn(self.active, goals)

    def test_all_tab_shows_every_status(self):
        response = self.client.get(reverse("goals:list"), {"status": "all"})
        self.assertEqual(
            set(response.context["goals"]), {self.active, self.completed, self.abandoned}
        )

    def test_explicit_single_status_filter(self):
        response = self.client.get(reverse("goals:list"), {"status": "abandoned"})
        self.assertEqual(list(response.context["goals"]), [self.abandoned])

    def test_search_matches_title_case_insensitively(self):
        response = self.client.get(reverse("goals:list"), {"status": "all", "q": "django"})
        self.assertEqual(list(response.context["goals"]), [self.active])

    def test_search_with_no_matches_is_empty(self):
        response = self.client.get(reverse("goals:list"), {"status": "all", "q": "nothing-matches-this"})
        self.assertEqual(list(response.context["goals"]), [])

    def test_search_is_scoped_within_the_current_tab(self):
        response = self.client.get(reverse("goals:list"), {"status": "active", "q": "یادگیری"})
        self.assertEqual(list(response.context["goals"]), [self.active])
