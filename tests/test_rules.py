import unittest
from datetime import datetime, timedelta
from eup_administration.rules import reading, start_reading, trip_distance, overlaps

class TestRules(unittest.TestCase):
    def test_mandatory_and_invalid_readings(self):
        for value in (None, '', -1, 'abc', float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reading(value)
    def test_zero_is_valid(self):
        self.assertEqual(reading(0), 0)
    def test_start_cannot_go_backwards(self):
        with self.assertRaises(ValueError):
            start_reading(100, 101)
    def test_gap_needs_reason(self):
        with self.assertRaises(ValueError):
            start_reading(102, 100, '  ')
        self.assertEqual(start_reading(102, 100, 'Garage transfer'), 102)
    def test_equal_start_reading(self):
        self.assertEqual(start_reading(100, 100), 100)
    def test_distance(self):
        self.assertEqual(trip_distance(125400, 125475), 75)
    def test_negative_distance_rejected(self):
        with self.assertRaises(ValueError):
            trip_distance(100, 99)
    def test_zero_distance_allowed(self):
        self.assertEqual(trip_distance(100, 100), 0)
    def test_conflict_and_boundary(self):
        t=datetime(2026, 10, 8, 10)
        self.assertTrue(overlaps(t, t+timedelta(hours=1), t+timedelta(minutes=30), t+timedelta(hours=2)))
        self.assertFalse(overlaps(t, t+timedelta(hours=1), t+timedelta(hours=1), t+timedelta(hours=2)))
    def test_room_buffer(self):
        t=datetime(2026, 10, 8, 10)
        self.assertTrue(overlaps(t, t+timedelta(hours=1), t+timedelta(minutes=70), t+timedelta(hours=2), 15))
        self.assertFalse(overlaps(t, t+timedelta(hours=1), t+timedelta(minutes=75), t+timedelta(hours=2), 15))
    def test_overnight(self):
        t=datetime(2026, 10, 8, 23)
        self.assertTrue(overlaps(t, t+timedelta(hours=3), t+timedelta(hours=2), t+timedelta(hours=4)))
    def test_invalid_time_range(self):
        t=datetime(2026, 10, 8)
        with self.assertRaises(ValueError):
            overlaps(t, t, t, t+timedelta(hours=1))

if __name__ == '__main__':
    unittest.main()
