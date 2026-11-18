import unittest
from types import SimpleNamespace

from app.narrative.analysis import deterministic_analysis
from app.narrative.foundation import assess_foundation
from app.narrative.gaps import next_gap
from app.narrative.parser import parse_premise
from app.narrative.questions import offline_question


PREMISES = [
    "A young doctor named Maya returns to her hometown to investigate her father's mysterious disappearance.",
    "A detective investigates a murder in a coastal town.",
    "The story follows Lena, a pilot, as she searches for her missing sister.",
    "Two estranged brothers disagree over whether to sell their family house.",
    "A woman decides to rebuild her life after losing her job.",
    "A child receives a package on the doorstep.",
    "A scientist struggles against a corporation seeking control of her research.",
    "A teacher is torn between protecting a student and telling the truth.",
    "A retired soldier returns home twenty years later.",
    "In 1998, a journalist uncovers letters from a forgotten town.",
    "A detective and a doctor investigate separate disappearances.",
    "A family travels across the country after their father dies.",
    "A woman wants to find her brother, but the premise does not say why he left.",
    "A protagonist named Imani wants to expose a city council's corruption.",
    "A nameless traveler arrives in a remote village.",
    "A student hopes to save the local library before it closes.",
    "A musician dreams of leaving home, while her partner wants to stay.",
    "A man receives an unopened letter and chooses not to reveal its contents.",
    "A child remembers a summer that may have happened differently.",
    "Someone wants something, but the premise gives no other details.",
    "A city wakes to find every clock stopped.",
    "A woman must choose between two promises.",
]


class DeterministicFoundationTests(unittest.TestCase):
    def test_twenty_diverse_premises_have_literal_only_extractions(self) -> None:
        self.assertGreaterEqual(len(PREMISES), 20)
        for premise in PREMISES:
            with self.subTest(premise=premise):
                mentions = parse_premise(premise)
                for mention in mentions:
                    self.assertIn(mention.value, premise)
                    self.assertEqual(premise[mention.source_start:mention.source_end], mention.value)
                    self.assertEqual(mention.extraction_method, "regex")
                    self.assertEqual(mention.confirmation_status, "unconfirmed")

    def test_example_maps_only_supported_fields_to_explicit(self) -> None:
        premise = PREMISES[0]
        mentions = parse_premise(premise)
        analysis = deterministic_analysis(premise, mentions)
        values = analysis.narrative_elements
        self.assertIn("Maya", [item.value for item in mentions if item.category == "character_name"])
        self.assertIn("doctor", [item.value.lower() for item in mentions if item.category == "character_role"])
        self.assertEqual(values.character_goals.status, "EXPLICIT")
        self.assertEqual(values.character_goals.value, "investigate her father's mysterious disappearance")
        self.assertEqual(values.character_motivations.status, "UNDECIDED")
        self.assertEqual(values.protagonist.status, "UNDECIDED")
        self.assertEqual(values.setting.status, "EXPLICIT")
        self.assertEqual(values.important_relationships.status, "EXPLICIT")
        self.assertEqual(values.central_conflict.status, "UNDECIDED")
        self.assertEqual(values.antagonist.status, "UNDECIDED")
        self.assertFalse(values.character_goals.writer_confirmed)

    def test_explicit_protagonist_phrase_is_distinguished_from_a_named_character(self) -> None:
        explicit = deterministic_analysis("The story follows Maya as she returns home.", parse_premise("The story follows Maya as she returns home."))
        implicit = deterministic_analysis("Maya returns home.", parse_premise("Maya returns home."))
        self.assertEqual(explicit.narrative_elements.protagonist.status, "EXPLICIT")
        self.assertEqual(implicit.narrative_elements.protagonist.status, "UNDECIDED")

    def test_no_antagonist_is_marked_only_when_writer_says_so(self) -> None:
        premise = "A quiet story of recovery with no conventional antagonist."
        result = deterministic_analysis(premise, parse_premise(premise))
        self.assertEqual(result.antagonist_classification, "no_conventional_antagonist")
        unclear = deterministic_analysis("A woman rebuilds her life.", parse_premise("A woman rebuilds her life."))
        self.assertEqual(unclear.antagonist_classification, "undecided")

    def test_assessment_uses_partial_and_established_without_a_score(self) -> None:
        premise = PREMISES[0]
        assessment = assess_foundation(
            deterministic_analysis(premise, parse_premise(premise)).narrative_elements,
            parse_premise(premise),
        )
        by_key = {item.key: item for item in assessment}
        self.assertEqual(by_key["protagonist"].status, "partially_established")
        self.assertEqual(by_key["character_goals"].status, "established")
        self.assertEqual(by_key["character_motivations"].status, "undecided")
        self.assertEqual(by_key["central_conflict"].status, "undecided")
        self.assertEqual(by_key["supporting_characters"].status, "undecided")
        self.assertIsNone(by_key["character_goals"].next_consideration)
        self.assertIsNotNone(by_key["character_motivations"].next_consideration)

    def test_assessment_respects_story_bible_confirmation_and_deferral(self) -> None:
        facts = [
            SimpleNamespace(
                id=1, label="Protagonist goal", status="confirmed", writer_confirmed=True,
                intentionally_undecided=False, value="Find her sister", evidence="Writer decision",
            ),
            SimpleNamespace(
                id=2, label="Motivation", status="undecided", writer_confirmed=False,
                intentionally_undecided=True, value="Not sure yet", evidence="Writer deferred",
            ),
        ]
        result = assess_foundation(
            deterministic_analysis("A woman searches.", parse_premise("A woman searches.")).narrative_elements,
            [],
            facts,
        )
        by_key = {item.key: item for item in result}
        self.assertEqual(by_key["character_goals"].status, "established")
        self.assertEqual(by_key["character_motivations"].status, "intentionally_deferred")

    def test_question_selection_is_prioritized_and_does_not_repeat(self) -> None:
        premise = PREMISES[0]
        analysis = deterministic_analysis(premise, parse_premise(premise))
        key = next_gap(analysis.narrative_elements, set())
        self.assertEqual(key, "protagonist")
        self.assertEqual(offline_question(key).question, "Who, if anyone, is the story centered on?")
        skipped = {"protagonist"}
        self.assertEqual(next_gap(analysis.narrative_elements, skipped), "central_conflict")
        self.assertNotEqual(next_gap(analysis.narrative_elements, skipped), key)


if __name__ == "__main__":
    unittest.main()
