import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import DayNote

User = get_user_model()


class DayNoteModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.day = dt.date(2026, 9, 24)

    def test_only_one_note_per_user_per_day(self):
        DayNote.objects.create(user=self.user, date=self.day, text="a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DayNote.objects.create(user=self.user, date=self.day, text="b")

    def test_different_users_can_have_note_on_same_day(self):
        DayNote.objects.create(user=self.user, date=self.day)
        DayNote.objects.create(user=self.other, date=self.day)
        self.assertEqual(DayNote.objects.filter(date=self.day).count(), 2)

    def test_mood_must_be_between_one_and_five(self):
        note = DayNote(user=self.user, date=self.day, mood=6)
        with self.assertRaises(ValidationError):
            note.full_clean()


class SaveNoteViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        cls.day = dt.date(2026, 9, 24)

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, day=None):
        return reverse("journal:save", args=[(day or self.day).isoformat()])

    def test_anonymous_is_redirected(self):
        self.client.logout()
        response = self.client.post(self.url(), {"mood": 4, "text": "خوب بود"})
        self.assertEqual(response.status_code, 302)

    def test_creates_note_on_first_save(self):
        response = self.client.post(self.url(), {"mood": 4, "text": "خوب بود"})
        self.assertEqual(response.status_code, 200)
        note = DayNote.objects.get(user=self.user, date=self.day)
        self.assertEqual(note.mood, 4)
        self.assertEqual(note.text, "خوب بود")

    def test_second_save_updates_the_same_note_not_a_new_one(self):
        self.client.post(self.url(), {"mood": 3, "text": "اول"})
        self.client.post(self.url(), {"mood": 5, "text": "دوم"})
        self.assertEqual(DayNote.objects.filter(user=self.user, date=self.day).count(), 1)
        note = DayNote.objects.get(user=self.user, date=self.day)
        self.assertEqual(note.text, "دوم")
        self.assertEqual(note.mood, 5)

    def test_invalid_mood_does_not_save_and_returns_form_with_errors(self):
        response = self.client.post(self.url(), {"mood": 9, "text": "بد"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["saved"])
        self.assertFalse(DayNote.objects.filter(user=self.user, date=self.day, text="بد").exists())

    def test_note_is_scoped_to_the_logged_in_user(self):
        self.client.post(self.url(), {"mood": 2, "text": "من"})
        self.assertFalse(DayNote.objects.filter(user=self.other, date=self.day).exists())

    def test_invalid_date_in_url_is_404(self):
        response = self.client.post("/journal/not-a-date/save/", {"mood": 3})
        self.assertEqual(response.status_code, 404)


class DayNoteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ali", password="pass12345")
        cls.other = User.objects.create_user("sara", password="pass12345")
        DayNote.objects.create(user=cls.user, date=dt.date(2026, 9, 24), text="من")
        DayNote.objects.create(user=cls.other, date=dt.date(2026, 9, 24), text="سارا")

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get("/api/notes/").status_code, 403)

    def test_list_only_returns_own_notes(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/notes/")
        texts = [n["text"] for n in response.json()["results"]]
        self.assertEqual(texts, ["من"])

    def test_create_via_api_sets_user(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/notes/", {"date": "2026-09-25", "text": "جدید", "mood": 4})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DayNote.objects.get(date=dt.date(2026, 9, 25)).user, self.user)

    def test_duplicate_date_via_api_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/notes/", {"date": "2026-09-24", "text": "دوباره"})
        self.assertEqual(response.status_code, 400)
