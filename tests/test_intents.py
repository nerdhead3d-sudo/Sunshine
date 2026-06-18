import unittest
from unittest import mock

from pet.skills import intents


class IntentsTests(unittest.TestCase):
    def setUp(self):
        self.scheduled = []

    def _sched(self, seconds, text):
        self.scheduled.append((seconds, text))

    def test_unrecognized_falls_through(self):
        self.assertIsNone(intents.try_handle("raccontami una barzelletta", self._sched))

    def test_time_query(self):
        reply = intents.try_handle("che ore sono", self._sched)
        self.assertIsNotNone(reply)
        self.assertIn("Sono le", reply)

    def test_polite_phrasing_matches_same_as_direct(self):
        with mock.patch.object(intents.commands, "volume_up") as volume_up:
            direct = intents.try_handle("alza il volume", self._sched)
            polite = intents.try_handle("puoi alzare un po' il volume per favore?", self._sched)
        self.assertEqual(direct, polite)
        self.assertEqual(volume_up.call_count, 2)

    def test_reminder_schedules_and_confirms(self):
        reply = intents.try_handle("ricordami di comprare il latte", self._sched)
        self.assertEqual(len(self.scheduled), 1)
        seconds, message = self.scheduled[0]
        self.assertEqual(seconds, 5 * 60)
        self.assertIn("comprare il latte", message)
        self.assertIn("comprare il latte", reply)

    def test_timer_minutes_vs_seconds(self):
        intents.try_handle("metti un timer di 5 minuti", self._sched)
        intents.try_handle("metti un timer di 30 secondi", self._sched)
        self.assertEqual(self.scheduled[0][0], 5 * 60)
        self.assertEqual(self.scheduled[1][0], 30)

    def test_open_known_app_vs_unknown(self):
        with mock.patch.object(intents.commands, "open_app_or_site", side_effect=lambda name: name == "blocco note"):
            reply = intents.try_handle("apri il blocco note", self._sched)
            self.assertEqual(reply, "Apro blocco note.")
            self.assertIsNone(intents.try_handle("apri marziano", self._sched))


if __name__ == "__main__":
    unittest.main()
