"""Run Sorkins browser regression checks against disposable local services."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_ready(url: str, process: subprocess.Popen, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}: {last_error}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as error:  # service is still starting
            last_error = str(error)
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {url}: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="show Chromium while tests run")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is missing. Install backend requirements, then run: python -m playwright install chromium", file=sys.stderr)
        return 2

    results_root = ROOT / "test-results"
    results_root.mkdir(exist_ok=True)
    run_dir = results_root / datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_dir.mkdir()
    temporary = tempfile.TemporaryDirectory(prefix="sorkins-e2e-")
    temp_dir = Path(temporary.name)
    backend_port, frontend_port = free_port(), free_port()
    while frontend_port == backend_port:
        frontend_port = free_port()
    env = os.environ.copy()
    env.update({
        "SORKINS_DATA_DIR": str(temp_dir),
        "SORKINS_DATABASE_URL": f"sqlite:///{(temp_dir / 'e2e.db').as_posix()}",
        "OLLAMA_HOST": "http://127.0.0.1:9",
        "OLLAMA_MODEL": "sorkins-e2e-unavailable",
        "SORKINS_API_URL": f"http://127.0.0.1:{backend_port}",
        "PYTHONPATH": str(ROOT / "backend") + os.pathsep + env.get("PYTHONPATH", ""),
        "SORKINS_E2E_URL": f"http://127.0.0.1:{frontend_port}",
        "SORKINS_E2E_API": f"http://127.0.0.1:{backend_port}",
        "SORKINS_E2E_ARTIFACTS": str(run_dir),
        "SORKINS_E2E_HEADED": "1" if args.headed else "0",
    })
    backend_log = (run_dir / "backend.log").open("w", encoding="utf-8")
    frontend_log = (run_dir / "frontend.log").open("w", encoding="utf-8")
    processes: list[subprocess.Popen] = []
    started = time.monotonic()
    suite_result: unittest.result.TestResult | None = None
    startup_error = ""
    browser_errors: list[str] = []
    failed_requests: list[str] = []
    try:
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port), "--log-level", "warning"],
            cwd=ROOT / "backend", env=env, stdout=backend_log, stderr=subprocess.STDOUT,
        )
        processes.append(backend)
        wait_ready(f"http://127.0.0.1:{backend_port}/api/health", backend)
        frontend = subprocess.Popen(
            ["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
            cwd=ROOT, env=env, stdout=frontend_log, stderr=subprocess.STDOUT,
        )
        processes.append(frontend)
        wait_ready(f"http://127.0.0.1:{frontend_port}/", frontend)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            os.environ.update(env)
            os.environ["SORKINS_E2E_HEADED"] = "1" if args.headed else "0"
            from test_workflows import BrowserWorkflowTests
            BrowserWorkflowTests.browser = browser
            BrowserWorkflowTests.playwright = playwright
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(BrowserWorkflowTests)
            runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
            suite_result = runner.run(suite)
            browser.close()
    except Exception as error:
        startup_error = f"{type(error).__name__}: {error}"
        print(startup_error, file=sys.stderr)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                    )
                try:
                    process.terminate()
                except OSError:
                    pass
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        backend_log.close()
        frontend_log.close()
        temporary.cleanup()

    if suite_result:
        browser_errors = getattr(BrowserWorkflowTests, "browser_errors", [])
        failed_requests = getattr(BrowserWorkflowTests, "failed_requests", [])
    categories = {
        "Characters": ("test_story_bible_workflows", "test_story_bible_entity_forms_and_selectors", "test_full_writer_workflow"),
        "Relationships": ("test_story_bible_entity_forms_and_selectors", "test_project_ui_isolation", "test_full_writer_workflow"),
        "Conflicts": ("test_story_bible_entity_forms_and_selectors", "test_full_writer_workflow"),
        "Locations": ("test_story_bible_entity_forms_and_selectors", "test_project_ui_isolation", "test_full_writer_workflow"),
        "Events and Timeline": ("test_story_bible_entity_forms_and_selectors", "test_project_ui_isolation", "test_full_writer_workflow"),
        "General Story Facts": ("test_general_story_facts_ui", "test_project_ui_isolation", "test_full_writer_workflow"),
        "Linked-Entity Selectors": ("test_story_bible_entity_forms_and_selectors", "test_project_ui_isolation"),
        "Provenance and History": ("test_story_bible_workflows", "test_general_story_facts_ui", "test_migration_compatibility"),
        "Tutorial Welcome": ("test_tutorial_welcome_guided_replay_and_contextual_persistence",),
        "Guided Tour": ("test_tutorial_welcome_guided_replay_and_contextual_persistence",),
        "Tutorial Replay": ("test_tutorial_welcome_guided_replay_and_contextual_persistence", "test_full_writer_workflow"),
        "Tutorial Persistence": ("test_tutorial_welcome_guided_replay_and_contextual_persistence", "test_project_ui_isolation"),
        "Cross-Project Isolation": ("test_project_ui_isolation", "test_project_isolation"),
        "Full Writer Workflow": ("test_full_writer_workflow",),
        "Project Setup": ("test_project_setup",),
        "Foundation Review": ("test_foundation_review",),
        "Screenplay Editor": ("test_screenplay_editor",),
        "Continuity Review": ("test_continuity_and_dispositions",),
        "Writer Dispositions": ("test_continuity_and_dispositions",),
        "Offline Functionality": ("test_offline_workflows",),
        "Database Isolation": ("test_project_isolation",),
        "Migration Compatibility": ("test_migration_compatibility",),
    }
    failures = suite_result.failures + suite_result.errors if suite_result else []
    failed_names = [test.id().split(".")[-1] for test, _ in failures]
    skipped_names = [test.id().split(".")[-1] for test, _ in suite_result.skipped] if suite_result else []
    rows = []
    for category, methods in categories.items():
        relevant = [name for name in methods if suite_result and any(test.id().endswith(name) for test in suite_result.successes)]
        bad = [name for name in methods if any(item == name for item in failed_names)]
        rows.append((category, "FAIL" if bad or startup_error else "PASS" if relevant else "NOT RUN"))
    summary = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started, 2),
        "total": suite_result.testsRun if suite_result else 0,
        "passed": suite_result.testsRun - len(failures) - len(skipped_names) if suite_result else 0,
        "failed": len(failures), "skipped": len(skipped_names),
        "failures": [{"test": test.id(), "details": detail} for test, detail in failures],
        "skipped_tests": skipped_names, "browser_errors": browser_errors,
        "failed_network_requests": failed_requests,
        "backend_errors": (run_dir / "backend.log").read_text(encoding="utf-8", errors="replace").splitlines(),
        "startup_error": startup_error,
        "categories": dict(rows),
    }
    (run_dir / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    table = "\n".join(f"| {name} | {result} |" for name, result in rows)
    report = (
        "# Sorkins browser regression report\n\n"
        f"- Tests: {summary['total']} total, {summary['passed']} passed, {summary['failed']} failed, {summary['skipped']} skipped\n"
        f"- Duration: {summary['duration_seconds']} seconds\n"
        f"- Startup: {startup_error or 'passed'}\n"
        f"- Browser errors: {len(browser_errors)}; failed requests: {len(failed_requests)}\n\n"
        "| Category | Result |\n|---|---|\n" + table + "\n\n"
        "See `report.json`, `backend.log`, and `frontend.log` for details. Failure screenshots are saved beside this report.\n"
    )
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"Report: {run_dir / 'report.md'}")
    return 0 if suite_result and suite_result.wasSuccessful() and not startup_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
