import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class AdditiveMigrationCompatibilityTest(unittest.TestCase):
    def test_populated_previous_revision_keeps_project_script_facts_and_questions(self):
        root = Path(__file__).resolve().parents[2]
        backend = root / "backend"
        with tempfile.TemporaryDirectory(prefix="sorkins-migration-check-") as folder:
            env = os.environ.copy()
            env["SORKINS_DATA_DIR"] = folder
            env["SORKINS_DATABASE_URL"] = f"sqlite:///{(Path(folder) / 'legacy.db').as_posix()}"
            env["PYTHONPATH"] = str(backend)
            script = r'''
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
root = Path(os.environ["PROJECT_ROOT"])
config = Config(str(root / "backend" / "alembic.ini"))
config.set_main_option("script_location", str(root / "backend" / "migrations"))
config.set_main_option("sqlalchemy.url", os.environ["SORKINS_DATABASE_URL"].replace("%", "%%"))
command.upgrade(config, "c2712c048f9a")
engine = create_engine(os.environ["SORKINS_DATABASE_URL"])
with engine.begin() as connection:
    connection.execute(text("INSERT INTO projects (id,title,format,genre,runtime,language,premise,updated_at,setup_step,setup_answers) VALUES (1,'Legacy','Feature Film','','','English','Old premise',CURRENT_TIMESTAMP,'questions','{\"protagonist\":{\"status\":\"answered\",\"response\":\"Mara\"}}')"))
    connection.execute(text("INSERT INTO acts (id,project_id,title,order_index) VALUES (1,1,'ACT I',0)"))
    connection.execute(text("INSERT INTO scenes (id,act_id,title,description,writer_notes,completed,order_index) VALUES (1,1,'INT. ROOM - DAY','Old scene','Notes',1,0)"))
    connection.execute(text("INSERT INTO screenplay_blocks (id,scene_id,type,text,order_index) VALUES (1,1,'action','Preserve this screenplay text',0)"))
    connection.execute(text("INSERT INTO story_facts (id,project_id,category,label,value,status,source,original_value,evidence,writer_confirmed,intentionally_undecided,modified_at) VALUES (1,1,'General','Legacy fact','Keep me','confirmed','Writer','Keep me','Evidence',1,0,CURRENT_TIMESTAMP)"))
    connection.execute(text("INSERT INTO story_fact_revisions (id,project_id,fact_id,action,category,label,original_value,value,status,source,evidence,writer_confirmed,intentionally_undecided,changed_at) VALUES (1,1,1,'updated','General','Legacy fact','Old','Keep me','confirmed','Writer','Evidence',1,0,CURRENT_TIMESTAMP)"))
    connection.execute(text("INSERT INTO premise_questions (id,project_id,element_key,question,status,response,created_at,answered_at,premise_snapshot) VALUES (1,1,'goal','Old question','answered','Old answer',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'Old premise')"))
    connection.execute(text("INSERT INTO app_preferences (id,tutorial_state) VALUES (1,:state)"), {"state": '{"welcome_dismissed":true,"completed":{"walkthrough":true}}'})
command.upgrade(config, "d9c4e7a1b215")
with engine.begin() as connection:
    connection.execute(text("INSERT INTO story_characters (id,project_id,name,description,evidence) VALUES (1,1,'Mara','Keeper','Writer named Mara')"))
    connection.execute(text("INSERT INTO story_characters (id,project_id,name) VALUES (2,1,'Ivo')"))
    connection.execute(text("INSERT INTO story_relationships (id,project_id,character_a_id,character_b_id,relationship_type,description) VALUES (1,1,1,2,'siblings','They protect each other')"))
    connection.execute(text("INSERT INTO story_conflicts (id,project_id,description,conflict_type) VALUES (1,1,'Choose whether to leave','internal')"))
    connection.execute(text("INSERT INTO story_conflict_characters (conflict_id,character_id) VALUES (1,1)"))
    connection.execute(text("INSERT INTO story_locations (id,project_id,name,description) VALUES (1,1,'North Lighthouse','Remote coast')"))
    connection.execute(text("INSERT INTO story_events (id,project_id,description,location_id,timeline_position) VALUES (1,1,'The letter arrives',1,2)"))
    connection.execute(text("INSERT INTO story_event_characters (event_id,character_id) VALUES (1,1)"))
    connection.execute(text("INSERT INTO story_entity_revisions (id,project_id,entity_type,entity_id,action,snapshot) VALUES (1,1,'character',1,'updated','{\"name\":\"Mara\"}')"))
    connection.execute(text("INSERT INTO continuity_findings (id,project_id,fingerprint,finding_type,description,disposition,writer_explanation,resolution_status) VALUES (1,1,'legacy-fingerprint','character_status','A saved finding','explained','Intentional ghost story','resolved')"))
command.upgrade(config, "head")
with engine.connect() as connection:
    assert connection.execute(text("SELECT title FROM projects WHERE id=1")).scalar_one() == "Legacy"
    assert connection.execute(text("SELECT text FROM screenplay_blocks WHERE id=1")).scalar_one() == "Preserve this screenplay text"
    assert connection.execute(text("SELECT value FROM story_facts WHERE id=1")).scalar_one() == "Keep me"
    assert connection.execute(text("SELECT response FROM premise_questions WHERE id=1")).scalar_one() == "Old answer"
    assert connection.execute(text("SELECT value FROM story_fact_revisions WHERE id=1")).scalar_one() == "Keep me"
    assert connection.execute(text("SELECT setup_answers FROM projects WHERE id=1")).scalar_one() == '{"protagonist":{"status":"answered","response":"Mara"}}'
    assert connection.execute(text("SELECT setup_step FROM projects WHERE id=1")).scalar_one() == "questions"
    assert connection.execute(text("SELECT tutorial_state FROM app_preferences WHERE id=1")).scalar_one() == '{"welcome_dismissed":true,"completed":{"walkthrough":true}}'
    assert connection.execute(text("SELECT timeline_context FROM scenes WHERE id=1")).scalar_one() == "unspecified"
    assert connection.execute(text("SELECT description FROM story_relationships WHERE id=1")).scalar_one() == "They protect each other"
    assert connection.execute(text("SELECT character_id FROM story_conflict_characters WHERE conflict_id=1")).scalar_one() == 1
    assert connection.execute(text("SELECT name FROM story_locations WHERE id=1")).scalar_one() == "North Lighthouse"
    assert connection.execute(text("SELECT timeline_position FROM story_events WHERE id=1")).scalar_one() == 2
    assert connection.execute(text("SELECT character_id FROM story_event_characters WHERE event_id=1")).scalar_one() == 1
    assert connection.execute(text("SELECT snapshot FROM story_entity_revisions WHERE id=1")).scalar_one() == '{"name":"Mara"}'
    assert connection.execute(text("SELECT disposition FROM continuity_findings WHERE id=1")).scalar_one() == "explained"
    assert connection.execute(text("SELECT writer_explanation FROM continuity_findings WHERE id=1")).scalar_one() == "Intentional ghost story"
    assert connection.execute(text("SELECT status FROM story_conflicts WHERE id=1")).scalar_one() == "active"
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "b4e81d02c7a9"
engine.dispose()
'''
            env["PROJECT_ROOT"] = str(root)
            result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
