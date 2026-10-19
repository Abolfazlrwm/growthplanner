"""Viewing a day page must not silently create an empty DayNote row."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.journal.models import DayNote

User = get_user_model()


class DayPageDoesNotCreateEmptyNoteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali", password="pass12345")
        self.client.force_login(self.user)

    def test_viewing_day_page_does_not_create_a_note(self):
        day = dt.date(2026, 9, 24)
        self.client.get(reverse("tasks:list"), {"date": day.isoformat()})
        self.assertFalse(DayNote.objects.filter(user=self.user, date=day).exists())

    def test_note_form_still_renders_for_a_day_with_no_note(self):
        response = self.client.get(reverse("tasks:list"))
        self.assertContains(response, "یادداشت و حال‌وهوای امروز")
