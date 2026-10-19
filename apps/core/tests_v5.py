"""Tests for the bilingual (fa/en) layer, colour palettes and the new onboarding pieces."""
import datetime as dt
import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.core.i18n import latin_digits, translate_chunk, translate_html, visible_persian
from apps.core.i18n_en import EN, JS_EN
from apps.core.ui import PALETTE_KEYS, PALETTES
from apps.habits.models import Habit
from apps.tasks.models import Task
from utils import dates

User = get_user_model()
PERSIAN_DIGIT = re.compile(r"[۰-۹]")


def make_user(name):
    return User.objects.create_user(name, password="pass12345")


def english(client):
    client.cookies["lang"] = "en"
    return client


def visible_text(html):
    html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


class DictionaryIntegrityTests(SimpleTestCase):
    def test_every_entry_is_non_empty_and_placeholders_line_up(self):
        for key, value in EN.items():
            with self.subTest(key=key[:40]):
                self.assertTrue(value.strip())
                self.assertEqual(len(re.findall(r"\{d\}|\{\}", key)), value.count("{}"), f"{key!r} -> {value!r}")

    def test_js_strings_are_a_subset_of_the_dictionary(self):
        for key in JS_EN:
            self.assertIn(key, EN)

    def test_no_english_value_contains_persian_letters(self):
        for key, value in EN.items():
            self.assertFalse(re.search(r"[\u0600-\u06FF]", value), value)

    def test_every_palette_has_light_and_dark_css(self):
        css = open("static/css/app.css", encoding="utf-8").read()
        for key in PALETTE_KEYS:
            if key == "tile":  # the default lives in :root
                continue
            self.assertIn(f'[data-palette="{key}"] {{', css)
            self.assertIn(f'.dark[data-palette="{key}"] {{', css)

    def test_every_palette_name_is_translated(self):
        for _, name in PALETTES:
            self.assertIn(name, EN)


class TranslatorTests(SimpleTestCase):
    def test_exact_and_pattern_chunks(self):
        self.assertEqual(translate_chunk("امروز"), "Today")
        self.assertEqual(translate_chunk("۱ از ۴"), "1 of 4")
        self.assertEqual(translate_chunk("۵ روز متوالی"), "5 day streak")
        self.assertEqual(translate_chunk("۶۲٪"), "62%")

    def test_unknown_user_text_is_untouched(self):
        self.assertEqual(translate_chunk("خرید از بازار"), "خرید از بازار")  # "{d} از {d}" must not fire
        self.assertEqual(translate_chunk("My own task"), "My own task")

    def test_digits_only_in_user_text(self):
        self.assertEqual(translate_chunk("تمرین ۳ ساعت"), "تمرین 3 ساعت")

    def test_title_suffix_and_comma_lists(self):
        self.assertEqual(translate_chunk("امروز · رشد شخصی"), "Today · Personal Growth")
        self.assertEqual(translate_chunk("شنبه، دوشنبه"), "Saturday, Monday")

    def test_html_attributes_icons_and_direction(self):
        html = ('<html lang="fa" dir="rtl"><body><button aria-label="بستن منو" title="حذف">x</button>'
                '<svg><use href="#i-chevron-right"/></svg><svg><use href="#i-chevron-left"/></svg>'
                '<svg><use href="#i-forward"/></svg></body></html>')
        out = translate_html(html)
        self.assertIn('<html lang="en" dir="ltr"', out)
        self.assertIn('aria-label="Close menu"', out)
        self.assertIn('title="Delete"', out)
        self.assertEqual(out.count('href="#i-chevron-left"'), 1)   # the old "right" became "left"
        self.assertEqual(out.count('href="#i-chevron-right"'), 1)  # and vice versa
        self.assertIn('href="#i-forward-r"', out)

    def test_scripts_styles_and_textareas_are_not_touched(self):
        html = "<script>var a='امروز';</script><style>.x{}</style><textarea>امروز ۱۲</textarea><p>امروز</p>"
        out = translate_html(html)
        self.assertIn("var a='امروز';", out)
        self.assertIn("<textarea>امروز ۱۲</textarea>", out)
        self.assertIn("<p>Today</p>", out)

    def test_whitespace_around_text_is_preserved(self):
        self.assertEqual(translate_html("<p>\n   امروز  \n</p>"), "<p>\n   Today  \n</p>")

    def test_json_ld_language_and_text(self):
        html = '<script type="application/ld+json">{"inLanguage":"fa","name":"رشد شخصی"}</script>'
        out = translate_html(html)
        self.assertIn('"inLanguage": "en"', out)
        self.assertIn("Personal Growth", out)

    def test_visible_persian_reports_leftovers(self):
        self.assertEqual(visible_persian("<p>امروز و سلام</p><p>Hello</p>"), ["امروز و سلام"])
        self.assertEqual(visible_persian('<a aria-label="کلمه‌ی ناشناخته">x</a>'), ["کلمه‌ی ناشناخته"])

    def test_latin_digits(self):
        self.assertEqual(latin_digits("۱۲۳٫۵"), "123.5")


class LanguageSwitchTests(TestCase):
    def test_default_is_persian_rtl(self):
        response = self.client.get("/")
        self.assertContains(response, 'lang="fa" dir="rtl"')
        self.assertEqual(response["Content-Language"], "fa")

    def test_english_cookie_switches_language_direction_and_text(self):
        response = english(self.client).get("/")
        self.assertContains(response, 'lang="en" dir="ltr"')
        self.assertEqual(response["Content-Language"], "en")
        self.assertContains(response, "Get started now")
        self.assertIn("Cookie", response["Vary"])

    def test_unknown_language_cookie_falls_back_to_persian(self):
        self.client.cookies["lang"] = "de"
        self.assertContains(self.client.get("/"), 'lang="fa"')

    def test_set_language_sets_cookie_and_redirects_back(self):
        response = self.client.get(reverse("core:set_language", args=["en"]), {"next": "/accounts/login/"})
        self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)
        self.assertEqual(response.cookies["lang"].value, "en")
        self.assertEqual(response.cookies["lang"]["samesite"], "Lax")

    def test_set_language_rejects_external_redirects_and_unknown_codes(self):
        response = self.client.get(reverse("core:set_language", args=["fa"]), {"next": "https://evil.example/"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("core:set_language", args=["de"])).status_code, 404)

    def test_switch_link_is_offered_to_visitors(self):
        self.assertContains(self.client.get("/"), reverse("core:set_language", args=["en"]))
        self.assertContains(english(self.client).get("/"), reverse("core:set_language", args=["fa"]))

    def test_js_dictionary_only_ships_in_english(self):
        self.assertNotContains(self.client.get("/"), "window.I18N")
        html = english(self.client).get("/").content.decode()
        self.assertIn("window.I18N", html)
        blob = html.split("window.I18N = ")[1].split(";</script>")[0]
        self.assertNotIn("</", blob)

    def test_error_pages_are_translated_too(self):
        response = english(self.client).get("/definitely-not-a-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, 'lang="en" dir="ltr"', status_code=404)

    def test_htmx_fragments_are_translated(self):
        user = make_user("frag")
        self.client.force_login(user)
        english(self.client)
        response = self.client.post(
            reverse("journal:save", args=[timezone.localdate().isoformat()]), {"mood": "", "text": "hello"}
        )
        self.assertContains(response, "Save note")
        self.assertContains(response, "Note and mood for today")
        self.assertEqual(visible_persian(response.content.decode()), [])


class PaletteTests(TestCase):
    def test_default_and_cookie_palette(self):
        self.assertContains(self.client.get("/"), 'data-palette="tile"')
        self.client.cookies["palette"] = "ocean"
        self.assertContains(self.client.get("/"), 'data-palette="ocean"')

    def test_unknown_palette_cookie_is_ignored(self):
        self.client.cookies["palette"] = "<script>"
        response = self.client.get("/")
        self.assertContains(response, 'data-palette="tile"')
        self.assertNotContains(response, "data-palette=\"<script>")

    def test_panel_lists_all_palettes_and_marks_the_current_one(self):
        self.client.cookies["palette"] = "forest"
        html = self.client.get("/").content.decode()
        self.assertEqual(len(re.findall(r'data-palette-set="', html)), 2 * len(PALETTES))  # popover + landing demo
        self.assertRegex(html, r'aria-checked="true" class="swatch" data-palette-set="forest"')
        self.assertIn("data-mode-set=\"dark\"", html)

    def test_signed_in_pages_have_the_appearance_button_and_tour(self):
        user = make_user("looks")
        self.client.force_login(user)
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("data-appearance-open", html)
        self.assertIn('id="tour-data" data-autostart="1"', html)
        other = self.client.get(reverse("tasks:list")).content.decode()
        self.assertIn('id="tour-data" data-autostart=""', other)

    def test_visitors_get_no_tour(self):
        self.assertNotContains(self.client.get("/"), "tour-data")

    def test_settings_page_has_the_appearance_section(self):
        user = make_user("sets")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("accounts:settings")), "data-palette-set")


class DateHelperTests(SimpleTestCase):
    day = dt.date(2026, 10, 5)  # a Monday

    def test_persian_mode(self):
        with translation.override("fa"):
            self.assertFalse(dates.is_english())
            self.assertEqual(dates.weekday_name(self.day), "دوشنبه")
            self.assertEqual(dates.week_offset(self.day), 2)       # Saturday-first
            self.assertEqual(dates.week_start(self.day), dt.date(2026, 10, 3))
            self.assertTrue(dates.is_weekend(dt.date(2026, 10, 9)))  # Friday
            self.assertFalse(dates.is_weekend(dt.date(2026, 10, 10)))

    def test_english_mode(self):
        with translation.override("en"):
            self.assertTrue(dates.is_english())
            self.assertEqual(dates.weekday_name(self.day), "Monday")
            self.assertEqual(dates.week_offset(self.day), 0)       # Monday-first
            self.assertEqual(dates.week_start(dt.date(2026, 10, 8)), self.day)
            self.assertTrue(dates.is_weekend(dt.date(2026, 10, 10)) and dates.is_weekend(dt.date(2026, 10, 11)))
            self.assertFalse(dates.is_weekend(dt.date(2026, 10, 9)))

    def test_formats(self):
        with translation.override("en"):
            self.assertEqual(dates.short_date(self.day), "Oct 5")
            self.assertEqual(dates.full_date(self.day), "Mon, Oct 5, 2026")
            self.assertEqual(dates.full_date(self.day, with_weekday=False), "Oct 5, 2026")
            self.assertEqual(dates.day_number(self.day), "5")
            self.assertEqual(dates.week_range_text(self.day, dt.date(2026, 10, 11)), "Oct 5 – Oct 11, 2026")
            self.assertEqual(dates.month_label(self.day), "Oct")
        with translation.override("fa"):
            self.assertEqual(dates.short_date(self.day), "۱۳ مهر")
            self.assertIn("۱۴۰۵", dates.full_date(self.day))
            self.assertEqual(dates.day_number(self.day), "۱۳")

    def test_jalali_filter_follows_the_language(self):
        from apps.core.templatetags.jalali_tags import jalali

        with translation.override("en"):
            self.assertEqual(jalali(self.day, "withweekday"), "Mon, Oct 5, 2026")
        with translation.override("fa"):
            self.assertIn("مهر", jalali(self.day))


class EnglishCalendarTests(TestCase):
    def setUp(self):
        self.user = make_user("cal")
        self.client.force_login(self.user)
        english(self.client)
        self.today = timezone.localdate()

    def test_month_is_gregorian_and_monday_first(self):
        response = self.client.get(reverse("calendar_view:month"))
        ctx = response.context
        self.assertEqual(ctx["year"], self.today.year)
        self.assertEqual(ctx["month"], self.today.month)
        self.assertEqual(ctx["weekdays"][0], ("Monday", "M", False))
        self.assertEqual(ctx["weekdays"][6], ("Sunday", "S", True))
        self.assertEqual(ctx["grid"][0][0]["gregorian"].weekday(), 0)
        self.assertTrue(ctx["is_current_month"])
        self.assertContains(response, ctx["month_name"])

    def test_month_navigation_wraps_the_year(self):
        ctx = self.client.get(reverse("calendar_view:month", args=[2026, 1])).context
        self.assertEqual((ctx["prev_year"], ctx["prev_month"]), (2025, 12))
        ctx = self.client.get(reverse("calendar_view:month", args=[2026, 12])).context
        self.assertEqual((ctx["next_year"], ctx["next_month"]), (2027, 1))

    def test_jalali_looking_year_falls_back_to_this_month(self):
        ctx = self.client.get(reverse("calendar_view:month", args=[1405, 7])).context
        self.assertEqual((ctx["year"], ctx["month"]), (self.today.year, self.today.month))

    def test_gregorian_looking_year_in_persian_falls_back_too(self):
        self.client.cookies["lang"] = "fa"
        ctx = self.client.get(reverse("calendar_view:month", args=[2026, 10])).context
        self.assertLess(ctx["year"], 1900)

    def test_tasks_show_as_dots_in_the_gregorian_grid(self):
        Task.objects.create(user=self.user, title="x", date=self.today)
        grid = self.client.get(reverse("calendar_view:month")).context["grid"]
        cell = next(c for week in grid for c in week if c["gregorian"] == self.today)
        self.assertEqual(cell["dots"], ["dot-todo"])

    def test_week_board_starts_on_monday_with_a_weekend(self):
        ctx = self.client.get(reverse("calendar_view:week")).context
        self.assertEqual(ctx["days"][0]["date"].weekday(), 0)
        self.assertEqual([d["is_friday"] for d in ctx["days"]], [False] * 5 + [True, True])
        self.assertEqual(ctx["days"][0]["weekday"], "Monday")
        self.assertRegex(ctx["week_range"], r"^[A-Z][a-z]{2} \d+ – [A-Z][a-z]{2} \d+, \d{4}$")

    def test_heatmap_and_habit_history_start_on_monday(self):
        from apps.core.views import build_heatmap
        from apps.habits.services import habit_history

        with translation.override("en"):
            heat = build_heatmap(self.user, self.today)
            self.assertEqual(heat["columns"][0]["cells"][0]["date"].weekday(), 0)
            habit = Habit.objects.create(user=self.user, title="h")
            history = habit_history(habit, self.today)
            self.assertEqual(history["columns"][0]["cells"][0]["date"].weekday(), 0)
            self.assertEqual(history["weekdays"][0]["label"], "Monday")


class EnglishPagesHaveNoPersianTests(TestCase):
    """A fresh account has no user content, so any Persian left on a page is a missing translation."""

    def check(self, url, user=None):
        client = english(self.client)
        if user:
            client.force_login(user)
        response = client.get(url)
        self.assertEqual(response.status_code, 200, url)
        html = response.content.decode()
        self.assertEqual(visible_persian(html), [], url)
        self.assertIsNone(PERSIAN_DIGIT.search(visible_text(html)), f"Persian digits left on {url}")

    def test_public_pages(self):
        for url in ("/", reverse("accounts:login"), reverse("accounts:register"), reverse("accounts:password_reset")):
            with self.subTest(url=url):
                self.check(url)

    def test_signed_in_pages(self):
        user = make_user("en-pages")
        for url in (reverse("core:home"), reverse("tasks:list"), reverse("tasks:search"), reverse("core:stats"),
                    reverse("core:focus"), reverse("goals:list"), reverse("goals:create"), reverse("habits:list"),
                    reverse("habits:create"), reverse("calendar_view:month"), reverse("calendar_view:week"),
                    reverse("calendar_view:timeline"), reverse("journal:list"), reverse("accounts:settings"),
                    reverse("accounts:password_change")):
            with self.subTest(url=url):
                self.check(url, user)

    def test_pages_with_data(self):
        from apps.goals.models import Goal

        user = make_user("en-data")
        today = timezone.localdate()
        goal = Goal.objects.create(user=user, title="Goal", deadline=today + dt.timedelta(days=9))
        habit = Habit.objects.create(user=user, title="Habit")
        Task.objects.create(user=user, title="Task", date=today, goal=goal)
        for url in (reverse("goals:detail", args=[goal.pk]), reverse("habits:detail", args=[habit.pk]),
                    reverse("core:home"), reverse("calendar_view:week"), reverse("goals:list"), reverse("habits:list")):
            with self.subTest(url=url):
                self.check(url, user)

    def test_user_text_is_never_rewritten(self):
        user = make_user("en-user")
        Task.objects.create(user=user, title="خرید از بازار", date=timezone.localdate())
        english(self.client).force_login(user)
        self.assertContains(self.client.get(reverse("tasks:list")), "خرید از بازار")

    def test_persian_mode_is_unchanged(self):
        user = make_user("fa-page")
        self.client.force_login(user)
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("تسک‌های امروز", html)
        self.assertNotIn("Today’s tasks", html)
