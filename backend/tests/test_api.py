import os
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx

test_data = tempfile.TemporaryDirectory(prefix="sorkins-tests-")
os.environ["SORKINS_DATA_DIR"] = test_data.name
os.environ["SORKINS_DATABASE_URL"] = f"sqlite:///{test_data.name.replace(os.sep, '/')}/test.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import (
    OllamaInvalidResponse,
    _ollama_error,
    _ollama_json,
    _raise_ollama_transport_error,
    app,
)
from app.narrative.parser import parse_premise
from app.database import SessionLocal
from app.models import PremiseAnalysis, Project
from app.database import engine

NARRATIVE_KEYS = [
    "protagonist",
    "antagonist",
    "central_conflict",
    "external_conflict",
    "internal_conflict",
    "character_motivations",
    "character_goals",
    "stakes",
    "genre",
    "setting",
    "theme",
    "central_dramatic_question",
    "important_relationships",
    "potential_structure",
]


def premise_result(premise: str, overrides: dict[str, dict[str, str | None]]) -> dict[str, object]:
    elements: dict[str, dict[str, str | None]] = {
        key: {
            "value": None,
            "status": "UNDECIDED",
            "evidence": "This element is not established by the premise.",
            "source": "premise",
        }
        for key in NARRATIVE_KEYS
    }
    elements.update(overrides)
    return {
        "premise": premise,
        "narrative_elements": elements,
        "antagonist_classification": "undecided",
    }


class ProjectApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        response = self.client.post("/api/projects", json={
            "title": "Test screenplay",
            "format": "Short Film",
            "premise": "A test premise.",
        })
        self.assertEqual(response.status_code, 201)
        self.project = response.json()
        self.assertEqual(self.project["setup_step"], "complete")
        self.project_id = self.project["id"]
        self.scene_id = self.project["acts"][0]["scenes"][0]["id"]

    def tearDown(self) -> None:
        self.client.close()

    def test_story_setup_and_tutorial_progress_persist(self) -> None:
        created = self.client.post("/api/projects", json={
            "title": "Guided story",
            "premise": "A loose opening idea.",
            "setup_flow": True,
        })
        self.assertEqual(created.status_code, 201, created.text)
        project_id = created.json()["id"]
        self.assertEqual(created.json()["setup_step"], "questions")

        updated = self.client.put(
            f"/api/projects/{project_id}/setup",
            json={
                "step": "questions",
                "answers": {
                    "protagonist": {"status": "answered", "response": "A young doctor."},
                    "opposition": {"status": "skipped", "response": ""},
                    "goal": {"status": "answered", "response": "I haven't decided yet."},
                },
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["answers"]["protagonist"]["response"], "A young doctor.")
        self.assertEqual(updated.json()["answers"]["goal"]["status"], "undecided")
        self.assertEqual(
            self.client.get(f"/api/projects/{project_id}/setup").json()["answers"]["opposition"]["status"],
            "skipped",
        )

        completed = self.client.put(
            "/api/preferences/tutorials",
            json={"welcome_dismissed": True, "completed": {"walkthrough": True}},
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(
            self.client.get("/api/preferences/tutorials").json(),
            {"welcome_dismissed": True, "completed": {"walkthrough": True}},
        )

    def test_adaptive_question_uses_setup_answers_without_repeating_covered_element(self) -> None:
        premise = "A young woman searches for her missing brother."
        project_id = self.create_project_with_premise(premise)
        with patch(
            "app.main._ollama_json",
            return_value=premise_result(premise, {}),
        ) as model:
            analyzed = self.client.post(f"/api/projects/{project_id}/development/analyze")
            self.assertEqual(analyzed.status_code, 200, analyzed.text)
            saved = self.client.put(
                f"/api/projects/{project_id}/setup",
                json={
                    "step": "review",
                    "answers": {
                        "protagonist": {"status": "answered", "response": "A young doctor."},
                        "goal": {"status": "answered", "response": "Find her missing brother."},
                    },
                },
            )
            self.assertEqual(saved.status_code, 200, saved.text)
            response = self.client.post(f"/api/projects/{project_id}/development/next-question")

        self.assertEqual(response.status_code, 200, response.text)
        question = response.json()["current_question"]
        self.assertEqual(question["element_key"], "central_conflict")
        self.assertNotEqual(question["element_key"], "protagonist")
        self.assertEqual(model.call_count, 1, "question generation must not call the LLM")

    def test_project_scene_blocks_and_facts_persist(self) -> None:
        saved = self.client.put(
            f"/api/projects/{self.project_id}/scenes/{self.scene_id}",
            json={
                "title": "INT. STATION - NIGHT",
                "blocks": [
                    {"type": "action", "text": "Rain streaks the glass."},
                    {"type": "dialogue", "text": "PRIVATE TEXT"},
                ],
            },
        )
        self.assertEqual(saved.status_code, 200)
        scene = saved.json()["acts"][0]["scenes"][0]
        self.assertEqual(scene["title"], "INT. STATION - NIGHT")
        self.assertEqual(scene["blocks"][1]["text"], "PRIVATE TEXT")

        fact = self.client.post(
            f"/api/projects/{self.project_id}/facts",
            json={"label": "Setting", "value": "A train station."},
        )
        self.assertEqual(fact.status_code, 201)
        self.assertEqual(fact.json()["status"], "confirmed")
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project_id}/facts").json()[0]["label"],
            "Setting",
        )

    def test_scene_reorder_persists_and_renumbers(self) -> None:
        created = self.client.post(
            f"/api/projects/{self.project_id}/acts/{self.project['acts'][0]['id']}/scenes",
            json={},
        )
        self.assertEqual(created.status_code, 201, created.text)
        scenes = created.json()["acts"][0]["scenes"]
        self.assertEqual(len(scenes), 2)
        first_id, second_id = scenes[0]["id"], scenes[1]["id"]
        reordered = self.client.post(
            f"/api/projects/{self.project_id}/scenes/{second_id}/reorder",
            json={"direction": "up"},
        )
        reordered_scenes = reordered.json()["acts"][0]["scenes"]
        self.assertEqual([scene["id"] for scene in reordered_scenes], [second_id, first_id])
        self.assertEqual([scene["number"] for scene in reordered_scenes], [1, 2])

    def test_scene_can_move_between_acts(self) -> None:
        second_act = self.client.post(f"/api/projects/{self.project_id}/acts", json={})
        self.assertEqual(second_act.status_code, 201)
        project = second_act.json()
        target_act = project["acts"][1]
        target_scene_id = target_act["scenes"][0]["id"]
        moved = self.client.post(
            f"/api/projects/{self.project_id}/scenes/{self.scene_id}/reorder",
            json={"target_scene_id": target_scene_id},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        result = moved.json()
        self.assertEqual(result["acts"][0]["scenes"], [])
        self.assertEqual([scene["id"] for scene in result["acts"][1]["scenes"]], [self.scene_id, target_scene_id])
        self.assertEqual([scene["number"] for scene in result["acts"][1]["scenes"]], [1, 2])

    def test_deleting_scene_preserves_order_for_next_scene(self) -> None:
        act_id = self.project["acts"][0]["id"]
        added = self.client.post(f"/api/projects/{self.project_id}/acts/{act_id}/scenes", json={})
        second_scene_id = added.json()["acts"][0]["scenes"][1]["id"]
        deleted = self.client.delete(f"/api/projects/{self.project_id}/scenes/{self.scene_id}")
        remaining = deleted.json()["acts"][0]["scenes"]
        self.assertEqual([(scene["id"], scene["number"]) for scene in remaining], [(second_scene_id, 1)])

        appended = self.client.post(f"/api/projects/{self.project_id}/acts/{act_id}/scenes", json={})
        scenes = appended.json()["acts"][0]["scenes"]
        self.assertEqual([scene["number"] for scene in scenes], [1, 2])

    def test_dialogue_requests_are_refused_and_dialogue_is_not_sent(self) -> None:
        refusal = self.client.post(
            f"/api/projects/{self.project_id}/assistant",
            json={"scene_id": self.scene_id, "prompt": "Write dialogue for a confrontation."},
        )
        self.assertEqual(refusal.status_code, 200)
        self.assertIn("can't write", refusal.json()["response"])

        with patch("app.main.request_ollama", return_value="I can check the scene context.") as ollama:
            response = self.client.post(
                f"/api/projects/{self.project_id}/assistant",
                json={"scene_id": self.scene_id, "prompt": "Check the scene context."},
            )
        self.assertEqual(response.status_code, 200)
        messages = ollama.call_args.args[0]
        self.assertNotIn("PRIVATE TEXT", messages[1]["content"])

    def create_project_with_premise(self, premise: str) -> int:
        response = self.client.post("/api/projects", json={"title": "Premise test", "premise": premise})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_concurrent_same_premise_analysis_reuses_committed_result(self) -> None:
        premise = "A lighthouse keeper finds a sealed letter."
        project_id = self.create_project_with_premise(premise)
        barrier = threading.Barrier(2)

        def model_response(*_args, **_kwargs):
            barrier.wait(timeout=5)
            return premise_result(premise, {})

        def analyze():
            with TestClient(app) as client:
                return client.post(f"/api/projects/{project_id}/development/analyze")

        with patch("app.main._ollama_json", side_effect=model_response):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _index: analyze(), range(2)))

        self.assertEqual([response.status_code for response in responses], [200, 200])
        with SessionLocal() as session:
            records = session.query(PremiseAnalysis).filter_by(project_id=project_id).all()
        self.assertEqual(len(records), 1)

    def test_analysis_preserves_explicit_inferred_and_undecided_boundaries(self) -> None:
        cases = [
            (
                "A detective investigates a murder committed by a politician.",
                {
                    "protagonist": {"value": "A detective", "status": "INFERRED", "evidence": 'Interpretation only; premise excerpt: "A detective investigates a murder"; this does not confirm the protagonist role.', "source": "ai_inference"},
                    "antagonist": {"value": None, "status": "UNDECIDED", "evidence": "The politician is identified as the perpetrator, but their broader antagonistic role is not established.", "source": "premise"},
                    "central_conflict": {"value": "A detective investigates a murder", "status": "EXPLICIT", "evidence": "A detective investigates a murder", "source": "premise"},
                },
                {"antagonist": "UNDECIDED"},
            ),
            (
                "A woman struggles to rebuild her life after losing her job.",
                {
                    "protagonist": {"value": "A woman", "status": "EXPLICIT", "evidence": "A woman", "source": "premise"},
                    "central_conflict": {"value": "struggles to rebuild her life after losing her job", "status": "EXPLICIT", "evidence": "struggles to rebuild her life after losing her job", "source": "premise"},
                },
                {"antagonist": "UNDECIDED", "protagonist": "INFERRED"},
            ),
            (
                "A successful businessman struggles with guilt over abandoning his family.",
                {
                    "protagonist": {"value": "A successful businessman", "status": "EXPLICIT", "evidence": "A successful businessman", "source": "premise"},
                    "internal_conflict": {"value": "guilt over abandoning his family", "status": "EXPLICIT", "evidence": "guilt over abandoning his family", "source": "premise"},
                    "character_motivations": {"value": None, "status": "UNDECIDED", "evidence": "Why he abandoned his family is not stated.", "source": "premise"},
                },
                {"antagonist": "UNDECIDED", "protagonist": "INFERRED"},
            ),
            (
                "Two estranged brothers return to their hometown after their father's death.",
                {
                    "protagonist": {"value": "Two estranged brothers", "status": "INFERRED", "evidence": 'Interpretation only; premise excerpt: "Two estranged brothers return"; this does not confirm which brother the story follows.', "source": "ai_inference"},
                    "important_relationships": {"value": "Two estranged brothers", "status": "EXPLICIT", "evidence": "Two estranged brothers", "source": "premise"},
                },
                {"protagonist": "INFERRED"},
            ),
            (
                "A mysterious package arrives at a woman's doorstep.",
                {
                    "protagonist": {"value": "A woman", "status": "INFERRED", "evidence": 'Interpretation only; premise excerpt: "a woman\'s doorstep"; this does not confirm the protagonist role.', "source": "ai_inference"},
                    "central_conflict": {"value": None, "status": "UNDECIDED", "evidence": "The premise does not state what happens after the package arrives.", "source": "premise"},
                },
                {"antagonist": "UNDECIDED", "central_conflict": "UNDECIDED"},
            ),
        ]

        for premise, overrides, expected in cases:
            with self.subTest(premise=premise):
                project_id = self.create_project_with_premise(premise)
                with patch("app.main._ollama_json", return_value=premise_result(premise, overrides)):
                    response = self.client.post(f"/api/projects/{project_id}/development/analyze")
                self.assertEqual(response.status_code, 200, response.text)
                analysis = response.json()["analysis"]
                self.assertEqual(analysis["premise"], premise)
                self.assertEqual(set(analysis["narrative_elements"]), set(NARRATIVE_KEYS))
                for element in analysis["narrative_elements"].values():
                    self.assertEqual(
                        set(element),
                        {
                            "value", "status", "evidence", "source", "confidence", "explanation",
                            "writer_confirmed", "intentionally_undecided",
                        },
                    )
                    self.assertTrue(element["evidence"])
                    self.assertGreaterEqual(element["confidence"], 0)
                    self.assertLessEqual(element["confidence"], 1)
                    self.assertTrue(element["explanation"])
                    self.assertIn(element["source"], {"premise", "writer", "ai_inference"})
                for key, status in expected.items():
                    self.assertEqual(analysis["narrative_elements"][key]["status"], status)
                for element in analysis["narrative_elements"].values():
                    if element["status"] == "EXPLICIT":
                        self.assertIn(element["value"], premise)
                        self.assertIn(element["evidence"], premise)
                    if element["status"] == "INFERRED":
                        self.assertIn("interpretation only", element["evidence"].lower())
                if "package" in premise.lower():
                    elements = analysis["narrative_elements"]
                    self.assertNotIn("contents", json.dumps(elements).lower())
                    self.assertIsNone(elements["central_conflict"]["value"])

    def test_unsupported_claims_are_demoted_before_story_bible_persistence(self) -> None:
        premise = "A retired detective receives letters from a serial killer he supposedly arrested 15 years ago."
        project_id = self.create_project_with_premise(premise)
        unsupported = premise_result(premise, {
            "protagonist": {
                "value": "A retired detective",
                "status": "EXPLICIT",
                "evidence": "A retired detective",
                "source": "premise",
            },
            "antagonist": {
                "value": "serial killer",
                "status": "EXPLICIT",
                "evidence": "serial killer",
                "source": "premise",
            },
            "external_conflict": {
                "value": "The killer escaped prison",
                "status": "EXPLICIT",
                "evidence": "serial killer",
                "source": "premise",
            },
            "central_conflict": {
                "value": "The detective must investigate the letters",
                "status": "EXPLICIT",
                "evidence": "receives letters",
                "source": "premise",
            },
            "character_motivations": {
                "value": "The detective feels guilt and wants justice",
                "status": "INFERRED",
                "evidence": 'Interpretation only; premise excerpt: "a serial killer"; this is an interpretation.',
                "source": "ai_inference",
            },
        })
        unsupported["antagonist_classification"] = "explicit_antagonist"
        with patch("app.main._ollama_json", return_value=unsupported):
            analyzed = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(analyzed.status_code, 200, analyzed.text)
        elements = analyzed.json()["analysis"]["narrative_elements"]
        self.assertEqual(analyzed.json()["analysis"]["antagonist_classification"], "undecided")
        for key in ("antagonist", "external_conflict", "central_conflict", "character_motivations"):
            self.assertEqual(elements[key]["status"], "UNDECIDED")
            self.assertIsNone(elements[key]["value"])
        persisted = self.client.get(f"/api/projects/{project_id}/development").json()["analysis"]["narrative_elements"]
        self.assertEqual(persisted, elements)
        facts = self.client.get(f"/api/projects/{project_id}/facts").json()
        self.assertFalse(any("escaped" in fact["value"].lower() or "guilt" in fact["value"].lower() for fact in facts))

    def test_antagonist_roles_are_explicitly_distinguished(self) -> None:
        cases = [
            (
                "A detective faces a villain who sends letters.",
                {"value": "villain", "status": "EXPLICIT", "evidence": "villain", "source": "premise"},
                "explicit_antagonist",
            ),
            (
                "A detective receives threats from a stranger.",
                {
                    "value": "stranger",
                    "status": "INFERRED",
                    "evidence": 'Interpretation only; premise excerpt: "receives threats from a stranger"; not confirmed.',
                    "source": "ai_inference",
                },
                "potential_antagonist",
            ),
            (
                "A woman rebuilds her life with no villain.",
                {"value": None, "status": "NOT_APPLICABLE", "evidence": "no villain", "source": "premise"},
                "no_conventional_antagonist",
            ),
        ]
        for premise, antagonist, expected_classification in cases:
            with self.subTest(premise=premise):
                project_id = self.create_project_with_premise(premise)
                result = premise_result(premise, {"antagonist": antagonist})
                result["antagonist_classification"] = expected_classification
                with patch("app.main._ollama_json", return_value=result):
                    response = self.client.post(f"/api/projects/{project_id}/development/analyze")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json()["analysis"]["antagonist_classification"],
                    expected_classification,
                )

    def test_premise_edits_during_slow_analysis_are_not_overwritten(self) -> None:
        premise = "An old premise."
        project_id = self.create_project_with_premise(premise)
        changed_premise = "The writer's updated premise."

        def finish_after_edit(*args, **kwargs):
            with SessionLocal() as db:
                project = db.get(Project, project_id)
                project.premise = changed_premise
                db.commit()
            return premise_result(premise, {})

        with patch("app.main._ollama_json", side_effect=finish_after_edit):
            response = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(response.status_code, 409, response.text)
        saved = next(project for project in self.client.get("/api/projects").json() if project["id"] == project_id)
        self.assertEqual(saved["premise"], changed_premise)
        development = self.client.get(f"/api/projects/{project_id}/development").json()
        self.assertIsNone(development["analysis"])

    def test_question_skip_answer_resume_and_story_bible_persistence(self) -> None:
        premise = "A young woman discovers her brother is involved in a series of bank robberies."
        project_id = self.create_project_with_premise(premise)
        analysis_payload = premise_result(premise, {})
        with patch("app.main._ollama_json", return_value=analysis_payload) as model:
            analyzed = self.client.post(f"/api/projects/{project_id}/development/analyze")
            self.assertEqual(analyzed.status_code, 200, analyzed.text)
            first = self.client.post(f"/api/projects/{project_id}/development/next-question")
            self.assertEqual(first.status_code, 200, first.text)
            first_question = first.json()["current_question"]
            self.assertEqual(first_question["element_key"], "protagonist")
            self.assertEqual(first_question["question"], "Who, if anyone, is the story centered on?")
            self.assertEqual(model.call_count, 1)

            repeated = self.client.post(f"/api/projects/{project_id}/development/next-question")
            self.assertEqual(repeated.json()["current_question"]["id"], first_question["id"])
            self.assertEqual(model.call_count, 1)

            skipped = self.client.post(
                f"/api/projects/{project_id}/development/questions/{first_question['id']}",
                json={"status": "skipped"},
            )
            self.assertEqual(skipped.status_code, 200, skipped.text)
            second = self.client.post(f"/api/projects/{project_id}/development/next-question")
            second_question = second.json()["current_question"]
            self.assertEqual(second_question["element_key"], "character_goals")

            answered = self.client.post(
                f"/api/projects/{project_id}/development/questions/{second_question['id']}",
                json={"status": "answered", "response": "She wants to understand what happened."},
            )
            self.assertEqual(answered.status_code, 200, answered.text)
            facts = self.client.get(f"/api/projects/{project_id}/facts").json()
            self.assertTrue(any(
                fact["label"] == "Character goals"
                and fact["value"] == "She wants to understand what happened."
                and fact["status"] == "confirmed"
                for fact in facts
            ))

            restored = self.client.get(f"/api/projects/{project_id}/development").json()
            self.assertEqual(restored["analysis"]["narrative_elements"]["character_goals"]["source"], "writer")
            self.assertEqual([item["status"] for item in restored["conversation"]], ["skipped", "answered"])
            reopened = self.client.post(
                f"/api/projects/{project_id}/development/questions/{first_question['id']}/reopen"
            )
            self.assertEqual(reopened.status_code, 200, reopened.text)
            self.assertEqual(reopened.json()["current_question"]["element_key"], "protagonist")
            self.assertEqual(len(reopened.json()["conversation"]), 3)

            repeated_analysis = self.client.post(f"/api/projects/{project_id}/development/analyze")
            self.assertEqual(repeated_analysis.status_code, 200, repeated_analysis.text)
            self.assertEqual(model.call_count, 1)
            restored_after_restart = self.client.get(f"/api/projects/{project_id}/development").json()
            self.assertEqual(restored_after_restart["current_question"]["element_key"], "protagonist")

            edited = self.client.put(
                f"/api/projects/{project_id}/development/elements/antagonist",
                json={"status": "NOT_APPLICABLE", "value": None},
            )
            self.assertEqual(edited.status_code, 200, edited.text)
            antagonist = edited.json()["analysis"]["narrative_elements"]["antagonist"]
            self.assertEqual(antagonist["status"], "NOT_APPLICABLE")
            self.assertEqual(antagonist["source"], "writer")
            self.assertEqual(
                edited.json()["analysis"]["antagonist_classification"],
                "no_conventional_antagonist",
            )

            edited_conflict = self.client.put(
                f"/api/projects/{project_id}/development/elements/central_conflict",
                json={"status": "EXPLICIT", "value": "She is trying to learn why her brother joined the robberies."},
            )
            self.assertEqual(edited_conflict.status_code, 200, edited_conflict.text)
            self.assertEqual(
                edited_conflict.json()["analysis"]["narrative_elements"]["central_conflict"]["source"],
                "writer",
            )
            facts = self.client.get(f"/api/projects/{project_id}/facts").json()
            self.assertTrue(any(fact["label"] == "Central conflict" and fact["status"] == "confirmed" for fact in facts))

    def test_invalid_model_premise_response_is_rejected(self) -> None:
        project_id = self.create_project_with_premise("A mysterious package arrives.")
        with patch("app.main._ollama_json", return_value={"premise": "changed premise"}):
            response = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(response.status_code, 502)
        self.assertIn("incomplete premise analysis", response.json()["detail"])

    def test_invalid_json_from_ollama_is_reported_as_bad_gateway(self) -> None:
        project_id = self.create_project_with_premise("A woman enters a station.")
        with patch("app.main._ollama_json", side_effect=OllamaInvalidResponse("Ollama returned invalid JSON.")):
            response = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(response.status_code, 502)
        self.assertIn("invalid JSON", response.json()["detail"])

    def test_explicit_protagonist_and_motivation_claims_need_role_or_intent_evidence(self) -> None:
        premise = "A successful businessman struggles with guilt over abandoning his family."
        project_id = self.create_project_with_premise(premise)
        proposed = premise_result(premise, {
            "protagonist": {
                "value": "A successful businessman",
                "status": "EXPLICIT",
                "evidence": "A successful businessman",
                "source": "premise",
            },
            "character_motivations": {
                "value": "guilt",
                "status": "EXPLICIT",
                "evidence": "guilt over abandoning his family",
                "source": "writer",
            },
            "character_goals": {
                "value": "to repair the relationship",
                "status": "INFERRED",
                "evidence": 'Interpretation only; premise excerpt: "guilt over abandoning his family"; inferred goal.',
                "source": "ai_inference",
            },
        })
        with patch("app.main._ollama_json", return_value=proposed):
            response = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(response.status_code, 200, response.text)
        elements = response.json()["analysis"]["narrative_elements"]
        self.assertEqual(elements["protagonist"]["status"], "INFERRED")
        self.assertIn("interpretation only", elements["protagonist"]["evidence"].lower())
        self.assertEqual(elements["character_motivations"]["status"], "UNDECIDED")
        self.assertIsNone(elements["character_motivations"]["value"])
        self.assertEqual(elements["character_goals"]["status"], "UNDECIDED")
        self.assertIsNone(elements["character_goals"]["value"])
        self.assertFalse(elements["character_motivations"]["writer_confirmed"])
        self.assertEqual(elements["internal_conflict"]["source"], "premise")

    def test_question_generation_is_deterministic_even_when_ai_analysis_is_enabled(self) -> None:
        premise = "A retired detective receives letters from a serial killer he supposedly arrested."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", return_value=premise_result(premise, {})):
            self.assertEqual(self.client.post(f"/api/projects/{project_id}/development/analyze").status_code, 200)
        with patch("app.main._ollama_json", side_effect=AssertionError("question generation called Ollama")) as model:
            response = self.client.post(f"/api/projects/{project_id}/development/next-question")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.call_count, 0)
        self.assertIsNotNone(response.json()["current_question"])

    def test_literal_parser_covers_all_five_premise_patterns_without_story_inference(self) -> None:
        premises = [
            "A retired detective receives letters from a serial killer he supposedly arrested 15 years ago.",
            "A detective investigates a murder committed by a politician.",
            "A successful businessman struggles with guilt over abandoning his family.",
            "Two estranged brothers return to their hometown after their father's death.",
            "A mysterious package arrives at a woman's doorstep.",
        ]
        parsed = [parse_premise(premise) for premise in premises]
        values = [{mention.value.lower() for mention in mentions} for mentions in parsed]
        self.assertIn("a retired detective", values[0])
        self.assertIn("a serial killer", values[0])
        self.assertIn("letters", values[0])
        self.assertIn("15 years ago", values[0])
        self.assertIn(
            "character_description",
            {mention.category for mention in parsed[0]},
        )
        self.assertIn("action", {mention.category for mention in parsed[0]})
        self.assertIn("a politician", values[1])
        self.assertIn("a successful businessman", values[2])
        self.assertIn("two estranged brothers", values[3])
        self.assertIn("hometown", values[3])
        self.assertIn("a woman", values[4])
        self.assertIn("package", values[4])
        self.assertIn("doorstep", values[4])
        self.assertFalse(any("escaped" in mention.value.lower() for row in parsed for mention in row))
        self.assertFalse(any("guilt" in mention.value.lower() for row in parsed for mention in row
                             if mention.category == "motivation_or_goal"))
        organization_mentions = parse_premise("A detective calls the police department.")
        self.assertIn("organization", {mention.category for mention in organization_mentions})
        for premise, mentions in zip(premises, parsed):
            for mention in mentions:
                self.assertEqual(mention.status, "EXPLICIT")
                self.assertEqual(mention.source, "premise")
                self.assertIn(mention.value, premise)
                self.assertIn(mention.evidence, premise)

    def test_evaluation_premises_keep_literal_relationships_goals_and_context(self) -> None:
        cases = [
            (
                "A young woman discovers that her father has been secretly working for the organisation "
                "responsible for her mother's disappearance. She decides to investigate the organisation "
                "despite her father's warnings.",
                ("A young woman", "her father", "her mother", "organisation", "decides", "investigate"),
            ),
            (
                "A middle-aged woman struggles to rebuild her life after losing her job and separating "
                "from her husband. She moves to a small coastal town to start again.",
                ("A middle-aged woman", "losing", "separating from her husband", "small coastal town", "start"),
            ),
            (
                "Two estranged brothers return to their hometown after their father's death. One wants to "
                "sell the family house, while the other insists on preserving it.",
                ("Two estranged brothers", "hometown", "their father", "sell", "preserving", "family house"),
            ),
            (
                "A mysterious package arrives at a woman's doorstep.",
                ("A mysterious package", "a woman", "package", "doorstep"),
            ),
            (
                "A detective investigates a series of murders connected to an unidentified individual. "
                "The identity of the person responsible will only be revealed in the final act.",
                ("A detective", "an unidentified individual", "revealed", "final act"),
            ),
        ]
        for premise, expected_mentions in cases:
            with self.subTest(premise=premise):
                mentions = parse_premise(premise)
                extracted_text = " ".join(mention.value for mention in mentions)
                for expected in expected_mentions:
                    self.assertIn(expected.lower(), extracted_text.lower())
                for mention in mentions:
                    self.assertIn(mention.value, premise)
                    self.assertIn(mention.evidence, premise)
                    self.assertEqual(mention.source, "premise")
        for premise, _ in cases:
            text = " ".join(mention.value for mention in parse_premise(premise)).lower()
            self.assertNotIn("escaped prison", text)
            self.assertNotIn("feels guilty", text)
            self.assertNotIn("threatens the detective", text)

    def test_ollama_failure_keeps_analysis_and_questioning_available(self) -> None:
        premise = "A mysterious package arrives at a woman's doorstep."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", side_effect=RuntimeError("Cannot connect to Ollama.")):
            analyzed = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(analyzed.status_code, 200, analyzed.text)
        development = analyzed.json()
        self.assertEqual(development["analysis_mode"], "deterministic")
        self.assertIn("Cannot connect to Ollama", development["analysis_notice"])
        self.assertIn("does not provide semantic narrative analysis", development["analysis_notice"])
        self.assertTrue(development["extractions"])
        self.assertEqual(
            development["analysis"]["narrative_elements"]["antagonist"]["status"],
            "UNDECIDED",
        )

        question = self.client.post(f"/api/projects/{project_id}/development/next-question")
        self.assertEqual(question.status_code, 200, question.text)
        self.assertEqual(question.json()["current_question"]["question"], "Who, if anyone, is the story centered on?")
        project = next(
            item for item in self.client.get("/api/projects").json()
            if item["id"] == project_id
        )
        scene_id = project["acts"][0]["scenes"][0]["id"]
        saved_scene = self.client.put(
            f"/api/projects/{project_id}/scenes/{scene_id}",
            json={"blocks": [{"type": "action", "text": "Writer can continue editing."}]},
        )
        self.assertEqual(saved_scene.status_code, 200, saved_scene.text)

    def test_offline_analysis_maps_literal_facts_without_inventing_roles_or_motives(self) -> None:
        premise = "A young doctor named Maya returns to her hometown to investigate her father's mysterious disappearance."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", side_effect=RuntimeError("Ollama is stopped.")) as provider:
            response = self.client.post(f"/api/projects/{project_id}/development/analyze")
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            elements = result["analysis"]["narrative_elements"]
            self.assertEqual(elements["character_goals"]["status"], "EXPLICIT")
            self.assertEqual(elements["character_goals"]["value"], "investigate her father's mysterious disappearance")
            self.assertFalse(elements["character_goals"]["writer_confirmed"])
            self.assertEqual(elements["protagonist"]["status"], "UNDECIDED")
            self.assertEqual(elements["character_motivations"]["status"], "UNDECIDED")
            self.assertEqual(elements["antagonist"]["status"], "UNDECIDED")
            self.assertEqual(elements["setting"]["value"], "hometown")
            self.assertIn("Maya", [item["value"] for item in result["extractions"]])
            maya = next(item for item in result["extractions"] if item["value"] == "Maya")
            self.assertEqual(premise[maya["source_start"]:maya["source_end"]], "Maya")
            self.assertEqual(maya["confirmation_status"], "unconfirmed")
            self.assertEqual({item["key"]: item["status"] for item in result["foundation"]}["protagonist"], "partially_established")
            self.assertEqual({item["key"]: item["status"] for item in result["foundation"]}["character_goals"], "established")
            question = self.client.post(f"/api/projects/{project_id}/development/next-question")
            self.assertEqual(question.status_code, 200, question.text)
            self.assertEqual(provider.call_count, 1, "question generation must not call Ollama")

    def test_story_fact_edits_and_deletions_keep_revision_history(self) -> None:
        created = self.client.post(
            f"/api/projects/{self.project_id}/facts",
            json={"label": "Setting", "value": "A station."},
        )
        self.assertEqual(created.status_code, 201, created.text)
        fact = created.json()
        self.assertEqual(fact["original_value"], "A station.")
        self.assertTrue(fact["writer_confirmed"])
        updated = self.client.put(
            f"/api/projects/{self.project_id}/facts/{fact['id']}",
            json={
                "category": "World",
                "label": "Setting",
                "value": "A train station.",
                "status": "confirmed",
                "source": "Writer",
                "evidence": "Writer edited this fact.",
                "source_text": "Writer edited this fact.",
                "writer_confirmed": True,
                "intentionally_undecided": False,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["original_value"], "A station.")
        self.assertEqual(
            self.client.delete(f"/api/projects/{self.project_id}/facts/{fact['id']}").status_code,
            204,
        )
        history = self.client.get(f"/api/projects/{self.project_id}/facts/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([revision["action"] for revision in history.json()], ["deleted", "updated", "created"])
        self.assertEqual(
            [revision["value"] for revision in history.json()],
            ["A train station.", "A station.", "A station."],
        )
        self.assertIsNone(history.json()[0]["fact_id"])

    def test_intentionally_undecided_response_is_persisted_and_not_reasked(self) -> None:
        premise = "A mysterious package arrives at a woman's doorstep."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", return_value=premise_result(premise, {})):
            self.assertEqual(
                self.client.post(f"/api/projects/{project_id}/development/analyze").status_code,
                200,
            )
        with patch("app.main._ollama_json", side_effect=RuntimeError("Ollama is unavailable.")):
            question_response = self.client.post(
                f"/api/projects/{project_id}/development/next-question"
            )
        question = question_response.json()["current_question"]
        response = self.client.post(
            f"/api/projects/{project_id}/development/questions/{question['id']}",
            json={"status": "undecided"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        element = response.json()["analysis"]["narrative_elements"]["protagonist"]
        self.assertTrue(element["intentionally_undecided"])
        self.assertFalse(element["writer_confirmed"])
        self.assertNotIn(
            "protagonist",
            {gap["element_key"] for gap in response.json()["gaps"]},
        )
        self.assertIsNone(response.json()["current_question"])

    def test_free_text_meta_responses_do_not_become_confirmed_story_facts(self) -> None:
        cases = [
            ("I haven't decided.", "undecided"),
            ("Skip this for now.", "skipped"),
            ("I don't want to decide this until I've developed Act 2.", "undecided"),
        ]
        for response_text, expected_status in cases:
            with self.subTest(response=response_text):
                premise = "A woman receives a letter."
                project_id = self.create_project_with_premise(premise)
                with patch("app.main._ollama_json", side_effect=[
                    premise_result(premise, {}),
                    {"element_key": "protagonist", "question": "Who does the story primarily follow?"},
                ]):
                    self.assertEqual(
                        self.client.post(f"/api/projects/{project_id}/development/analyze").status_code,
                        200,
                    )
                    question_state = self.client.post(
                        f"/api/projects/{project_id}/development/next-question"
                    )
                question = question_state.json()["current_question"]
                resolved = self.client.post(
                    f"/api/projects/{project_id}/development/questions/{question['id']}",
                    json={"status": "answered", "response": response_text},
                )
                self.assertEqual(resolved.status_code, 200, resolved.text)
                state = resolved.json()
                self.assertEqual(state["conversation"][0]["status"], expected_status)
                facts = self.client.get(f"/api/projects/{project_id}/facts").json()
                protagonist_facts = [fact for fact in facts if fact["label"] == "Protagonist"]
                if expected_status == "undecided":
                    element = state["analysis"]["narrative_elements"]["protagonist"]
                    self.assertEqual(element["status"], "UNDECIDED")
                    self.assertTrue(element["intentionally_undecided"])
                    self.assertIn(response_text, element["evidence"])
                    self.assertEqual(len(protagonist_facts), 1)
                    self.assertEqual(protagonist_facts[0]["status"], "undecided")
                    self.assertTrue(protagonist_facts[0]["intentionally_undecided"])
                    self.assertFalse(protagonist_facts[0]["writer_confirmed"])
                else:
                    self.assertEqual(protagonist_facts, [])

    def test_writer_antagonist_answer_updates_role_classification(self) -> None:
        premise = "A young woman discovers her father works for an organisation."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", return_value=premise_result(premise, {})):
            self.assertEqual(
                self.client.post(f"/api/projects/{project_id}/development/analyze").status_code,
                200,
            )
        for key in (
            "protagonist", "central_conflict", "character_goals", "character_motivations",
            "stakes", "external_conflict", "internal_conflict",
        ):
            self.assertEqual(
                self.client.put(
                    f"/api/projects/{project_id}/development/elements/{key}",
                    json={"status": "NOT_APPLICABLE", "value": None},
                ).status_code,
                200,
            )
        state = self.client.post(f"/api/projects/{project_id}/development/next-question")
        question = state.json()["current_question"]
        response_text = "I want the father to be an antagonist, but not a villain."
        resolved = self.client.post(
            f"/api/projects/{project_id}/development/questions/{question['id']}",
            json={"status": "answered", "response": response_text},
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        analysis = resolved.json()["analysis"]
        antagonist = analysis["narrative_elements"]["antagonist"]
        self.assertEqual(antagonist["value"], response_text)
        self.assertEqual(antagonist["status"], "EXPLICIT")
        self.assertEqual(antagonist["source"], "writer")
        self.assertEqual(analysis["antagonist_classification"], "explicit_antagonist")
        fact = next(
            item for item in self.client.get(f"/api/projects/{project_id}/facts").json()
            if item["label"] == "Antagonistic force"
        )
        self.assertEqual(fact["value"], response_text)
        self.assertTrue(fact["writer_confirmed"])

    def test_writer_change_of_mind_updates_current_value_and_keeps_history(self) -> None:
        premise = "A young woman discovers her father works for an organisation."
        project_id = self.create_project_with_premise(premise)
        with patch("app.main._ollama_json", return_value=premise_result(premise, {})):
            self.assertEqual(
                self.client.post(f"/api/projects/{project_id}/development/analyze").status_code,
                200,
            )
        first_decision = self.client.put(
            f"/api/projects/{project_id}/development/elements/protagonist",
            json={"status": "EXPLICIT", "value": "The young woman is the protagonist."},
        )
        self.assertEqual(first_decision.status_code, 200, first_decision.text)
        revised_decision = "Actually, I changed my mind. Her father is the protagonist."
        changed = self.client.put(
            f"/api/projects/{project_id}/development/elements/protagonist",
            json={"status": "EXPLICIT", "value": revised_decision},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(
            changed.json()["analysis"]["narrative_elements"]["protagonist"]["value"],
            revised_decision,
        )
        history = self.client.get(f"/api/projects/{project_id}/facts/history").json()
        protagonist_history = [item for item in history if item["label"] == "Protagonist"]
        self.assertEqual([item["action"] for item in protagonist_history], ["updated", "created"])
        self.assertEqual(
            protagonist_history[0]["value"],
            "The young woman is the protagonist.",
        )
        current_fact = next(
            item for item in self.client.get(f"/api/projects/{project_id}/facts").json()
            if item["label"] == "Protagonist"
        )
        self.assertEqual(current_fact["value"], revised_decision)

    def test_writer_decisions_and_old_questions_survive_premise_changes(self) -> None:
        premise = "A retired detective receives letters from a serial killer he supposedly arrested."
        project_id = self.create_project_with_premise(premise)
        responses = [
            premise_result(premise, {}),
            {"element_key": "protagonist", "question": "Who does the story primarily follow?"},
            {"element_key": "central_conflict", "question": "What conflict has the writer established so far?"},
        ]
        with patch("app.main._ollama_json", side_effect=responses):
            self.assertEqual(
                self.client.post(f"/api/projects/{project_id}/development/analyze").status_code,
                200,
            )
            first = self.client.post(f"/api/projects/{project_id}/development/next-question")
            first_question = first.json()["current_question"]
            answered = self.client.post(
                f"/api/projects/{project_id}/development/questions/{first_question['id']}",
                json={"status": "answered", "response": "The detective is the protagonist."},
            )
            self.assertEqual(answered.status_code, 200, answered.text)
            second = self.client.post(f"/api/projects/{project_id}/development/next-question")
            self.assertEqual(
                second.json()["current_question"]["element_key"],
                "character_goals",
            )

        changed_premise = "The detective finds a note in an empty office."
        updated_project = self.client.patch(
            f"/api/projects/{project_id}",
            json={"premise": changed_premise},
        )
        self.assertEqual(updated_project.status_code, 200, updated_project.text)
        with patch("app.main._ollama_json", return_value=premise_result(changed_premise, {})):
            analyzed = self.client.post(f"/api/projects/{project_id}/development/analyze")
        self.assertEqual(analyzed.status_code, 200, analyzed.text)
        result = analyzed.json()
        protagonist = result["analysis"]["narrative_elements"]["protagonist"]
        self.assertEqual(protagonist["value"], "The detective is the protagonist.")
        self.assertEqual(protagonist["source"], "writer")
        self.assertEqual([item["status"] for item in result["conversation"]], ["answered", "superseded"])
        self.assertEqual(
            result["conversation"][0]["response"],
            "The detective is the protagonist.",
        )
        self.assertIn("changed the premise", result["conversation"][1]["response"])
        facts = self.client.get(f"/api/projects/{project_id}/facts").json()
        self.assertTrue(any(fact["value"] == "The detective is the protagonist." for fact in facts))

    def test_ollama_stream_uses_long_read_timeout_and_disables_thinking(self) -> None:
        content = json.dumps({"result": "structured"})
        stream_lines = [
            json.dumps({"message": {"content": content[:10]}, "done": False}),
            json.dumps({"message": {"content": content[10:]}, "done": True}),
        ]
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/ps":
                return httpx.Response(200, json={
                    "models": [{"name": "qwen3-vl:4b", "context_length": 6144}],
                })
            observed["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                content=("\n".join(stream_lines) + "\n").encode(),
                headers={"Content-Type": "application/x-ndjson"},
            )

        real_client = httpx.Client

        def client_factory(**kwargs):
            observed["timeout"] = kwargs["timeout"]
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        with patch.dict(os.environ, {
            "OLLAMA_READ_TIMEOUT_SECONDS": "1800",
            "OLLAMA_NUM_PREDICT": "4096",
            "OLLAMA_NUM_CTX": "6144",
            "OLLAMA_THINK_MODE": "low",
        }):
            with patch("app.main.httpx.Client", side_effect=client_factory):
                result = _ollama_json(
                    [{"role": "user", "content": "test"}],
                    {"type": "object"},
                )
        self.assertEqual(result, {"result": "structured"})
        payload = observed["payload"]
        self.assertIsInstance(payload, dict)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["think"], "low")
        self.assertEqual(payload["options"]["num_ctx"], 6144)
        self.assertEqual(payload["options"]["num_predict"], 4096)
        self.assertEqual(observed["timeout"].read, 1800)
        self.assertIn("not installed", str(_ollama_error(404, "model 'missing' not found", "missing")))

    def test_ollama_distinguishes_context_and_output_truncation(self) -> None:
        real_client = httpx.Client

        for counts, expected_message in (
            ({"prompt_eval_count": 3000, "eval_count": 3144}, "context window"),
            ({"prompt_eval_count": 1000, "eval_count": 1000}, "4096-token output limit"),
        ):
            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/api/ps":
                    return httpx.Response(200, json={
                        "models": [{"name": "qwen3-vl:4b", "context_length": 6144}],
                    })
                return httpx.Response(
                    200,
                    content=(json.dumps({
                        "message": {"content": ""},
                        "done": True,
                        "done_reason": "length",
                        **counts,
                    }) + "\n").encode(),
                    headers={"Content-Type": "application/x-ndjson"},
                )

            def client_factory(**kwargs):
                return real_client(transport=httpx.MockTransport(handler), **kwargs)

            with self.subTest(counts=counts):
                with patch.dict(os.environ, {
                    "OLLAMA_NUM_CTX": "6144",
                    "OLLAMA_NUM_PREDICT": "4096",
                }):
                    with patch("app.main.httpx.Client", side_effect=client_factory):
                        with self.assertRaises(OllamaInvalidResponse) as error:
                            _ollama_json([{"role": "user", "content": "test"}], {"type": "object"})
                self.assertIn(expected_message, str(error.exception))

    def test_ollama_timeout_errors_are_not_reported_as_connection_failures(self) -> None:
        self.assertIn(
            "Cannot connect",
            str(_raise_ollama_transport_error(httpx.ConnectError("refused"), "http://ollama", "model", False)),
        )
        self.assertIn(
            "may still be loading",
            str(_raise_ollama_transport_error(httpx.ReadTimeout("slow"), "http://ollama", "model", False)),
        )
        self.assertIn(
            "inference timeout",
            str(_raise_ollama_transport_error(httpx.ReadTimeout("slow"), "http://ollama", "model", False, True)),
        )

    def test_assistant_stream_delivers_incremental_text_and_completion(self) -> None:
        async def fake_stream(messages, model, num_gpu):
            yield {"type": "token", "content": "First "}
            yield {"type": "token", "content": "chunk"}

        with patch("app.main._ollama_assistant_stream", fake_stream):
            response = self.client.post(
                f"/api/projects/{self.project_id}/assistant/stream",
                json={"scene_id": self.scene_id, "prompt": "Summarize established scene facts."},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn('"content": "First "', response.text)
        self.assertIn('"content": "chunk"', response.text)
        self.assertIn('"type": "done"', response.text)


class StructuredStoryBibleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        response = self.client.post("/api/projects", json={"title": "Structured API story"})
        self.project_id = response.json()["id"]

    def tearDown(self) -> None:
        self.client.close()

    def entity_url(self, kind: str) -> str:
        return f"/api/projects/{self.project_id}/story-bible/entities/{kind}"

    def test_character_edit_provenance_revision_and_merge(self) -> None:
        response = self.client.post(self.entity_url("characters"), json={
            "name": "Mara", "role": "protagonist", "goals": "Find her brother",
            "evidence": "Writer notes", "confirmation_status": "writer_confirmed",
        })
        self.assertEqual(response.status_code, 201, response.text)
        mara = response.json()
        second = self.client.post(self.entity_url("characters"), json={"name": "M.", "confirmation_status": "undecided"}).json()
        edited = self.client.put(f"{self.entity_url('characters')}/{mara['id']}", json={**mara, "goals": "Rescue her brother"})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["evidence"], "Writer notes")
        self.assertEqual(edited.json()["confirmation_status"], "writer_confirmed")
        merged = self.client.post(f"{self.entity_url('characters')}/{second['id']}/merge", json={"target_id": mara["id"]})
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertIn("M.", merged.json()["aliases"])
        history = self.client.get(f"/api/projects/{self.project_id}/story-bible/history").json()
        self.assertGreaterEqual(len(history), 4)
        previous_edit = next(item for item in history if item["entity_id"] == mara["id"] and item["action"] == "updated")
        self.assertEqual(previous_edit["snapshot"]["goals"], "Find her brother")

    def test_conflict_status_is_editable_and_unconfirmed_provenance_is_preserved(self) -> None:
        character = self.client.post(self.entity_url("characters"), json={"name": "Rin"}).json()
        conflict = self.client.post(self.entity_url("conflicts"), json={
            "description": "Rin is unsure whether to leave.", "status": "paused",
            "character_ids": [character["id"]], "confirmation_status": "explicit_unconfirmed",
            "source_type": "premise", "evidence": "A directly quoted premise span.",
        })
        self.assertEqual(conflict.status_code, 201, conflict.text)
        created = conflict.json()
        self.assertEqual(created["status"], "paused")
        updated = self.client.put(f"{self.entity_url('conflicts')}/{created['id']}", json={
            **created, "description": "Rin postpones the decision.", "status": "resolved",
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "resolved")
        self.assertEqual(updated.json()["confirmation_status"], "explicit_unconfirmed")
        self.assertEqual(updated.json()["source_type"], "premise")
        self.assertEqual(updated.json()["character_ids"], [character["id"]])

    def test_relationship_location_event_and_project_isolation(self) -> None:
        first = self.client.post(self.entity_url("characters"), json={"name": "Ada"}).json()
        second = self.client.post(self.entity_url("characters"), json={"name": "Bea"}).json()
        relationship = self.client.post(self.entity_url("relationships"), json={
            "character_a_id": first["id"], "character_b_id": second["id"],
            "relationship_type": "siblings", "evidence": "They are sisters.",
        })
        self.assertEqual(relationship.status_code, 201, relationship.text)
        location = self.client.post(self.entity_url("locations"), json={"name": "Station", "aliases": ["Central"]})
        self.assertEqual(location.status_code, 201, location.text)
        event = self.client.post(self.entity_url("events"), json={
            "description": "They meet", "character_ids": [first["id"], second["id"]],
            "location_id": location.json()["id"], "timeline_position": 3,
        })
        self.assertEqual(event.status_code, 201, event.text)
        self.assertEqual(event.json()["character_names"], ["Ada", "Bea"])
        other = self.client.post("/api/projects", json={"title": "Other"}).json()["id"]
        self.assertEqual(self.client.get(f"/api/projects/{other}/story-bible/entities/characters").json(), [])
        cross_project = self.client.put(f"/api/projects/{other}/story-bible/entities/characters/{first['id']}", json=first)
        self.assertEqual(cross_project.status_code, 404)

    def test_deterministic_finding_evidence_and_disposition_persist(self) -> None:
        character = self.client.post(self.entity_url("characters"), json={
            "name": "Ivo", "aliases": ["Ivo"], "current_status": "dead",
            "status_effective_position": 2, "confirmation_status": "writer_confirmed",
            "evidence": "Ivo dies at position 2.",
        }).json()
        scene = self.client.post(f"/api/projects/{self.project_id}/acts", json={}).json()["acts"][-1]["scenes"][0]
        block = scene["blocks"][0]
        saved = self.client.put(f"/api/projects/{self.project_id}/scenes/{scene['id']}", json={
            "title": "INT. STATION - NIGHT", "completed": True, "timeline_position": 4,
            "timeline_context": "present", "blocks": [{"id": block["id"], "type": "character", "text": "IVO"}],
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        analysis = self.client.post(f"/api/projects/{self.project_id}/continuity/analyze", json={})
        self.assertEqual(analysis.status_code, 200, analysis.text)
        finding = next(item for item in analysis.json()["findings"] if item["finding_type"] == "character_status")
        self.assertEqual(finding["relevant_character_ids"], [character["id"]])
        self.assertTrue(finding["evidence_refs"])
        dismissed = self.client.put(f"/api/projects/{self.project_id}/continuity/findings/{finding['id']}", json={"disposition": "dismissed"})
        self.assertEqual(dismissed.json()["resolution_status"], "resolved")
        rerun = self.client.post(f"/api/projects/{self.project_id}/continuity/analyze", json={}).json()
        persisted = next(item for item in rerun["findings"] if item["id"] == finding["id"])
        self.assertEqual(persisted["disposition"], "dismissed")
        self.assertEqual(persisted["resolution_status"], "resolved")
        actions = [
            ("accepted_intentional", ""),
            ("explained", "The scene is a recorded memory."),
            ("dismissed", "The writer checked the cue."),
            ("needs_correction", "Revise this scene later."),
        ]
        for disposition, note in actions:
            response = self.client.put(f"/api/projects/{self.project_id}/continuity/findings/{finding['id']}", json={"disposition": disposition, "writer_explanation": note})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["disposition"], disposition)
            self.assertEqual(response.json()["writer_explanation"], note)
        refreshed = self.client.get(f"/api/projects/{self.project_id}/continuity/findings").json()
        self.assertEqual(next(item for item in refreshed if item["id"] == finding["id"])["disposition"], "needs_correction")


if __name__ == "__main__":
    unittest.main()


def tearDownModule() -> None:
    engine.dispose()
    test_data.cleanup()
