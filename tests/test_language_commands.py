import unittest

from pet.skills import language_commands


class LanguageCommandsTests(unittest.TestCase):
    def test_detects_target_language_in_multiple_phrasings(self):
        cases = [
            ("parla in inglese", "en"),
            ("speak english please", "en"),
            ("parle en français", "fr"),
            ("habla español", "es"),
            ("sprich deutsch", "de"),
            ("fala português", "pt"),
            ("parla italiano", "it"),
        ]
        for text, expected_lang in cases:
            with self.subTest(text=text):
                matched, lang = language_commands.detect(text)
                self.assertTrue(matched)
                self.assertEqual(lang, expected_lang)

    def test_detects_auto_detect_reset_command(self):
        matched, lang = language_commands.detect("torna automatico")
        self.assertTrue(matched)
        self.assertIsNone(lang)

    def test_does_not_match_unrelated_text(self):
        matched, _ = language_commands.detect("che ore sono")
        self.assertFalse(matched)

    def test_confirmation_messages_exist_for_every_language(self):
        for lang in ["it", "en", "fr", "es", "de", "pt", None]:
            self.assertTrue(language_commands.confirmation_for(lang))


if __name__ == "__main__":
    unittest.main()
