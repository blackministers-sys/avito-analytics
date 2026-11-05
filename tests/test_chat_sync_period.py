import unittest

from chat_analytics.sync_service import _in_period, _message_datetime, _parse_bound


class SyncPeriodTests(unittest.TestCase):
    def test_date_bounds_are_inclusive_by_calendar_day(self):
        start = _parse_bound("2026-10-01")
        end = _parse_bound("2026-10-02", end=True)
        self.assertTrue(_in_period({"created": 1790870400}, start, end))
        self.assertFalse(_in_period({"created": 1791043200}, start, end))

    def test_unix_seconds_and_milliseconds_are_supported(self):
        seconds = _message_datetime({"created": 1790841600})
        millis = _message_datetime({"created": 1790841600000})
        self.assertEqual(seconds, millis)

    def test_iso_timestamp_is_normalized_to_utc(self):
        parsed = _message_datetime({"created_at": "2026-10-01T12:30:00+03:00"})
        self.assertEqual(parsed.isoformat(), "2026-10-01T09:30:00+00:00")

    def test_unknown_timestamp_is_excluded_when_filtering(self):
        start = _parse_bound("2026-10-01")
        self.assertFalse(_in_period({"text": "no timestamp"}, start, None))

    def test_reversed_range_is_detectable(self):
        start = _parse_bound("2026-10-03")
        end = _parse_bound("2026-10-02", end=True)
        self.assertGreaterEqual(start, end)


if __name__ == "__main__":
    unittest.main()
