import unittest
from datetime import datetime, timedelta
from eup_administration.rules import money, reading, recurrence_dates

class TestV2Rules(unittest.TestCase):
    def test_positive_costs(self):
        for value in (None, '', -1, 0, True, 'NaN', 'Infinity', '1e400'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)
        self.assertEqual(money('125.25'), 125.25)
        self.assertEqual(money(0, False), 0)
    def test_float_overflow_is_rejected(self):
        with self.assertRaises(ValueError):
            reading('1e400')
    def test_daily_and_weekly_include_exact_count(self):
        t = datetime(2026, 10, 13, 9)
        for frequency, days in (('Daily', 1), ('Weekly', 7)):
            dates = recurrence_dates(t, t+timedelta(hours=1), frequency, '3')
            self.assertEqual(len(dates), 2)
            self.assertEqual(dates[-1][0], t+timedelta(days=2*days))
    def test_invalid_recurrence_is_rejected(self):
        t = datetime(2026, 10, 13)
        for count in (True, None, 0, 1, 53, 2.5, '2.5', 'abc'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                recurrence_dates(t, t+timedelta(hours=1), 'Daily', count)
        with self.assertRaises(ValueError):
            recurrence_dates(t, t+timedelta(hours=25), 'Daily', 2)
        with self.assertRaises(ValueError):
            recurrence_dates(t, t+timedelta(hours=1), 'Monthly', 2)
    def test_cairo_wall_clock_recurrence_crosses_month(self):
        t = datetime(2026, 10, 29, 10)
        dates = recurrence_dates(t, t+timedelta(hours=1), 'Weekly', 3)
        self.assertEqual(dates[0][0], datetime(2026, 11, 5, 10))
