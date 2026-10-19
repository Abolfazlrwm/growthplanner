import datetime as dt

import jdatetime
from django.test import SimpleTestCase

from utils.jalali import (
    build_month_grid, format_jalali, jalali_month_bounds,
    next_month, prev_month, to_jalali,
)


class JalaliTests(SimpleTestCase):
    def test_nowruz_1405(self):
        # 21 March 2026 is 1 Farvardin 1405, a Saturday.
        self.assertEqual(to_jalali(dt.date(2026, 3, 21)), jdatetime.date(1405, 1, 1))
        self.assertEqual(format_jalali(dt.date(2026, 3, 21)), "شنبه ۱ فروردین ۱۴۰۵")

    def test_latin_digits_option(self):
        text = format_jalali(dt.date(2026, 3, 21), with_weekday=False, persian_digits=False)
        self.assertEqual(text, "1 فروردین 1405")

    def test_aware_datetime_uses_tehran_timezone(self):
        # 20:30 UTC on 20 March is already 21 March in Tehran (UTC+3:30).
        value = dt.datetime(2026, 3, 20, 20, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(to_jalali(value), jdatetime.date(1405, 1, 1))


class MonthGridTests(SimpleTestCase):
    def test_first_six_months_have_31_days(self):
        for month in range(1, 7):
            _, count = jalali_month_bounds(1405, month)
            self.assertEqual(count, 31, f"month {month} should have 31 days")

    def test_months_seven_to_eleven_have_30_days(self):
        for month in range(7, 12):
            _, count = jalali_month_bounds(1405, month)
            self.assertEqual(count, 30, f"month {month} should have 30 days")

    def test_month_bounds_first_day_matches_nowruz(self):
        first, _ = jalali_month_bounds(1405, 1)
        self.assertEqual(first, dt.date(2026, 3, 21))

    def test_grid_weeks_are_full_weeks_of_seven(self):
        grid = build_month_grid(1405, 1)
        for week in grid:
            self.assertEqual(len(week), 7)

    def test_grid_every_week_starts_saturday_ends_friday(self):
        grid = build_month_grid(1405, 7)
        for week in grid:
            self.assertEqual(to_jalali(week[0]["gregorian"]).weekday(), 0)
            self.assertEqual(to_jalali(week[-1]["gregorian"]).weekday(), 6)
            self.assertTrue(week[-1]["is_holiday"])
            self.assertFalse(week[0]["is_holiday"])

    def test_grid_covers_every_day_of_the_month_exactly_once(self):
        grid = build_month_grid(1405, 1)
        in_month_days = [day for week in grid for day in week if day["in_month"]]
        self.assertEqual(len(in_month_days), 31)
        self.assertEqual(in_month_days[0]["gregorian"], dt.date(2026, 3, 21))

    def test_grid_may_include_padding_days_from_adjacent_months(self):
        grid = build_month_grid(1405, 1)
        all_days = [day for week in grid for day in week]
        padding = [day for day in all_days if not day["in_month"]]
        # Padding is optional depending on which weekday the month starts/ends on,
        # but every padding day must be adjacent (previous or next jalali month).
        for day in padding:
            j = to_jalali(day["gregorian"])
            self.assertTrue((j.year, j.month) in {(1404, 12), (1405, 2)})

    def test_prev_and_next_month_wrap_the_year(self):
        self.assertEqual(prev_month(1405, 1), (1404, 12))
        self.assertEqual(next_month(1405, 12), (1406, 1))
        self.assertEqual(next_month(1405, 6), (1405, 7))
