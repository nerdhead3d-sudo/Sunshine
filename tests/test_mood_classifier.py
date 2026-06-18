import unittest

from pet.mood.classifier import get_classifier
from pet.mood.dataset import LABEL_VALENCE


class MoodClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = get_classifier()
        if cls.classifier is None:
            raise unittest.SkipTest("modello non addestrato: esegui 'python -m pet.mood.train' prima dei test")

    def test_classifies_training_examples_correctly(self):
        # The network is tiny and trained on ~140 examples on purpose (see
        # pet/mood/dataset.py): it should at least nail sentences that
        # closely match what it was trained on.
        cases = [
            ("sono felicissimo oggi", "felice"),
            ("ti voglio tanto bene", "affettuoso"),
            ("non sto più nella pelle", "eccitato"),
            ("ho fatto la spesa stamattina", "neutro"),
            ("che noia, non so cosa fare", "annoiato"),
            ("sono molto triste oggi", "triste"),
            ("sono furioso adesso", "arrabbiato"),
        ]
        for text, expected_label in cases:
            with self.subTest(text=text):
                label, valence = self.classifier.classify(text)
                self.assertEqual(label, expected_label)
                self.assertEqual(valence, LABEL_VALENCE[expected_label])

    def test_valence_matches_label_table(self):
        label, valence = self.classifier.classify("ti adoro tantissimo")
        self.assertEqual(valence, LABEL_VALENCE[label])

    def test_returns_a_known_label_for_unseen_phrasing(self):
        label, _ = self.classifier.classify("wow, fantastico, andiamo subito a vederlo")
        self.assertIn(label, LABEL_VALENCE)


if __name__ == "__main__":
    unittest.main()
