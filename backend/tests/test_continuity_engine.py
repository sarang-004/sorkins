import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.narrative.continuity import detect_continuity_candidates


def character(**changes):
    values = dict(id=1, name="Mara", aliases="[]", current_status="dead", status_effective_position=2,
                  confirmation_status="writer_confirmed", source_type="writer", evidence="Mara dies.")
    values.update(changes)
    return NS(**values)


def scene(position=3, context="present", title="INT. STATION - NIGHT", completed=True, cue="MARA"):
    blocks = [NS(type="character", text=cue)] if cue else []
    return NS(id=10, title=title, timeline_position=position, timeline_context=context,
              completed=completed, blocks=blocks)


def location(id=1, name="Station", confirmation_status="writer_confirmed"):
    return NS(id=id, name=name, aliases="[]", confirmation_status=confirmation_status)


class ContinuityRuleScenarios(unittest.TestCase):
    def death_case(self, **changes):
        return detect_continuity_candidates(1, [character()], [scene(**changes)], [], [])

    def test_twenty_two_conservative_scenarios(self):
        cases = [
            ("confirmed death then present cue", self.death_case(), True),
            ("flashback is exempt", self.death_case(context="flashback"), False),
            ("dream is exempt", self.death_case(context="dream"), False),
            ("alternate timeline is exempt", self.death_case(context="alternate"), False),
            ("unreliable narration is exempt", self.death_case(context="unreliable"), False),
            ("incomplete scene ignored", self.death_case(completed=False), False),
            ("missing scene position ignored", self.death_case(position=None), False),
            ("earlier scene ignored", self.death_case(position=1), False),
            ("unconfirmed death ignored", detect_continuity_candidates(1, [character(confirmation_status="explicit_unconfirmed")], [scene()], [], []), False),
            ("missing cue ignored", self.death_case(cue=""), False),
            ("two locations at same assigned position", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(5, title="EXT. PIER - DAY")], [location(), location(2, "Pier")], []), True),
            ("different positions are not overlap", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(6, title="EXT. PIER - DAY")], [location(), location(2, "Pier")], []), False),
            ("same confirmed location is not conflict", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(5)], [location()], []), False),
            ("non-present location scene exempt", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(5, context="flashback", title="EXT. PIER - DAY")], [location(), location(2, "Pier")], []), False),
            ("unconfirmed location ignored", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(5, title="EXT. PIER - DAY")], [location(), location(2, "Pier", "explicit_unconfirmed")], []), False),
            ("unknown location heading ignored", detect_continuity_candidates(1, [character(current_status="alive")], [scene(5), scene(5, title="EXT. PIER - DAY")], [location()], []), False),
            ("inverted confirmed dependency flagged", detect_continuity_candidates(1, [], [], [], [NS(id=1, project_id=1, confirmation_status="writer_confirmed", timeline_position=4, dependency_event_ids="[]", description="cause", evidence="cause evidence", characters=[]), NS(id=2, project_id=1, confirmation_status="writer_confirmed", timeline_position=2, dependency_event_ids="[1]", description="effect", evidence="effect evidence", characters=[])]), True),
            ("correct event dependency order accepted", detect_continuity_candidates(1, [], [], [], [NS(id=1, project_id=1, confirmation_status="writer_confirmed", timeline_position=2, dependency_event_ids="[]", description="cause", evidence="", characters=[]), NS(id=2, project_id=1, confirmation_status="writer_confirmed", timeline_position=4, dependency_event_ids="[1]", description="effect", evidence="", characters=[])]), False),
            ("missing event position ignored", detect_continuity_candidates(1, [], [], [], [NS(id=1, project_id=1, confirmation_status="writer_confirmed", timeline_position=None, dependency_event_ids="[]", description="cause", evidence="", characters=[]), NS(id=2, project_id=1, confirmation_status="writer_confirmed", timeline_position=2, dependency_event_ids="[1]", description="effect", evidence="", characters=[])]), False),
            ("unconfirmed event ignored", detect_continuity_candidates(1, [], [], [], [NS(id=1, project_id=1, confirmation_status="writer_confirmed", timeline_position=4, dependency_event_ids="[]", description="cause", evidence="", characters=[]), NS(id=2, project_id=1, confirmation_status="inferred_unconfirmed", timeline_position=2, dependency_event_ids="[1]", description="effect", evidence="", characters=[])]), False),
            ("event chronology can be nonlinear when unrelated", detect_continuity_candidates(1, [], [], [], [NS(id=1, project_id=1, confirmation_status="writer_confirmed", timeline_position=5, dependency_event_ids="[]", description="later", evidence="", characters=[]), NS(id=2, project_id=1, confirmation_status="writer_confirmed", timeline_position=1, dependency_event_ids="[]", description="earlier", evidence="", characters=[])]), False),
            ("story events do not infer object destruction", detect_continuity_candidates(1, [], [], [], []), False),
        ]
        for label, result, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(bool(result), expected)
                if result:
                    self.assertTrue(result[0]["evidence_refs"])
                    self.assertEqual(len(result[0]["fingerprint"]), 64)

    def test_fingerprints_are_stable_and_change_with_source(self):
        first = self.death_case()[0]["fingerprint"]
        again = self.death_case()[0]["fingerprint"]
        changed = detect_continuity_candidates(1, [character(evidence="Updated death evidence")], [scene()], [], [])[0]["fingerprint"]
        self.assertEqual(first, again)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
