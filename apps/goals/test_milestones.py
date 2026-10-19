import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Goal, Milestone

User = get_user_model()


class MilestoneFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.goal = Goal.objects.create(user=cls.user, title="هدف من", deadline=dt.date(2026, 12, 1))
        cls.other_goal = Goal.objects.create(user=cls.other, title="هدف سارا", deadline=dt.date(2026, 12, 1))

    def setUp(self):
        self.client.force_login(self.user)

    def test_add_toggle_and_delete_milestone_are_owner_scoped(self):
        response = self.client.post(
            reverse("goals:milestone_add", args=[self.goal.pk]),
            {"title": "نسخهٔ اول", "due_date": "2026-06-01"},
        )
        self.assertEqual(response.status_code, 302)
        milestone = Milestone.objects.get(goal=self.goal)
        self.assertEqual(milestone.user, self.user)
        self.assertFalse(milestone.is_completed)
        self.client.post(reverse("goals:milestone_toggle", args=[self.goal.pk, milestone.pk]))
        milestone.refresh_from_db()
        self.assertTrue(milestone.is_completed)
        self.assertIsNotNone(milestone.completed_at)
        self.client.post(reverse("goals:milestone_delete", args=[self.goal.pk, milestone.pk]))
        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())

    def test_other_users_goal_or_milestone_is_not_addressable(self):
        private = Milestone.objects.create(user=self.other, goal=self.other_goal, title="خصوصی")
        self.assertEqual(
            self.client.post(reverse("goals:milestone_add", args=[self.other_goal.pk]), {"title": "x"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("goals:milestone_toggle", args=[self.other_goal.pk, private.pk])).status_code,
            404,
        )

    def test_model_rejects_cross_owner_goal(self):
        invalid = Milestone(user=self.user, goal=self.other_goal, title="x")
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_goal_api_includes_goal_owner_and_milestone_owner(self):
        Milestone.objects.create(user=self.user, goal=self.goal, title="نقطه")
        response = self.client.get(f"/api/goals/{self.goal.pk}/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"], self.user.pk)
        self.assertEqual(payload["milestones"][0]["user"], self.user.pk)
