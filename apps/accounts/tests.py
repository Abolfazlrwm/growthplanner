from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

GOOD_PASSWORD = "S3cure-pass-987"


class RegistrationTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ali", "password1": GOOD_PASSWORD, "password2": GOOD_PASSWORD},
        )
        user = User.objects.get(username="ali")
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ali", "password1": GOOD_PASSWORD, "password2": "different-pass-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="ali").exists())

    def test_duplicate_username_is_rejected_case_insensitively(self):
        User.objects.create_user("ali", password=GOOD_PASSWORD)
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "Ali", "password1": GOOD_PASSWORD, "password2": GOOD_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)


class LoginLogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password=GOOD_PASSWORD)

    def test_login_with_valid_credentials(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ali", "password": GOOD_PASSWORD}
        )
        self.assertRedirects(response, reverse("core:home"))

    def test_login_redirects_to_next(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=/admin/",
            {"username": "ali", "password": GOOD_PASSWORD},
        )
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ali", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_ends_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_in_user_is_redirected_away_from_login_and_register(self):
        self.client.force_login(self.user)
        for name in ("accounts:login", "accounts:register"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("core:home"))


class AccountSettingsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password=GOOD_PASSWORD)

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertEqual(response.status_code, 302)

    def test_logged_in_user_can_view_settings(self):
        self.client.login(username="ali", password=GOOD_PASSWORD)
        response = self.client.get(reverse("accounts:settings"))
        self.assertEqual(response.status_code, 200)


class ExportDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password=GOOD_PASSWORD)

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse("accounts:export"))
        self.assertEqual(response.status_code, 302)

    def test_export_returns_json_with_expected_sections(self):
        from apps.goals.models import Goal
        from django.utils import timezone
        Goal.objects.create(user=self.user, title="یادگیری پیانو", deadline=timezone.localdate())
        self.client.login(username="ali", password=GOOD_PASSWORD)
        response = self.client.get(reverse("accounts:export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertEqual(len(data["goals"]), 1)
        self.assertIn("tasks", data)
        self.assertIn("habits", data)
        self.assertIn("notes", data)


class DeleteAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password=GOOD_PASSWORD)

    def setUp(self):
        self.client.login(username="ali", password=GOOD_PASSWORD)

    def test_get_shows_confirmation_without_deleting(self):
        response = self.client.get(reverse("accounts:delete"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_post_deletes_the_account_and_logs_out(self):
        response = self.client.post(reverse("accounts:delete"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
