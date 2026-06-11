import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.rag as rag_api
import app.features.knowledge.gbrain.maintenance.citation_fixer_jobs as citation_fixer_jobs
import app.features.knowledge.gbrain.maintenance.contradiction_probe as contradiction_probe
import app.features.knowledge.gbrain.maintenance.dream_cycle as dream_cycle
import app.features.knowledge.gbrain.maintenance.worker as maintenance_worker
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.notification import Notification
from models.user import User


class _FakeGBrainAdapter:
    submitted_jobs = []
    job_status_by_id = {}

    def __init__(self, settings=None):
        self.settings = settings

    def sync_source(self, **kwargs):
        return {"status": "ok", "result": {"chunksCreated": 2}}

    def start_http_service(self):
        return {"ok": True, "status": "started"}

    def stop_http_service(self):
        return {"ok": True, "status": "stopped"}

    def service_process_status(self):
        return {"running": False, "discovered_pids": []}

    def restart_http_service(self):
        return {"ok": True, "status": "restarted"}

    def doctor(self):
        return {"status": "ok", "result": {"status": "healthy"}}

    def status_snapshot(self):
        return {"status": "ok", "result": {"sync": {"sources": []}}}

    def list_jobs(self, **kwargs):
        return {
            "status": "ok",
            "result": [
                {"id": 10, "name": "sync", "status": kwargs.get("status") or "waiting", "progress": {"phase": "queued"}}
            ],
        }

    def get_job(self, job_id):
        status = self.__class__.job_status_by_id.get(int(job_id), "waiting")
        return {"status": "ok", "result": {"id": int(job_id), "name": "subagent", "status": status}}

    def get_job_progress(self, job_id):
        return {"status": "ok", "result": {"id": job_id, "progress": {"phase": "queued"}}}

    def submit_job(self, **kwargs):
        if kwargs.get("name") == "shell":
            return {"status": "invalid_job_name", "error": "unsupported"}
        self.__class__.submitted_jobs.append(kwargs)
        job_id = 10 + len(self.__class__.submitted_jobs)
        return {"status": "ok", "result": {"id": job_id, "name": kwargs.get("name"), "status": "waiting"}}

    def cancel_job(self, job_id):
        return {"status": "ok", "result": {"id": job_id, "status": "cancelled"}}

    def retry_job(self, job_id):
        return {"status": "ok", "result": {"id": job_id, "status": "waiting"}}

    def find_contradictions(self, **kwargs):
        return {"status": "ok", "result": {"contradictions": [{"severity": "medium", "left": "a", "right": "b"}]}}

    def submit_citation_fixer(self, **kwargs):
        return {
            "status": "ok",
            "result": {
                "id": 12,
                "name": "subagent",
                "status": "waiting",
                "page_slug": kwargs.get("page_slug"),
                "review_id": kwargs.get("review_id"),
            },
        }

    def maintenance_check(self, **kwargs):
        return {"status": "ok", "result": {"mode": "check", "brain_score": kwargs.get("target_score")}}

    def maintenance_status(self):
        return {
            "ok": True,
            "doctor": self.doctor(),
            "doctor_summary": {"status": "healthy", "health_score": 95},
            "status_snapshot": self.status_snapshot(),
            "jobs": self.list_jobs(limit=20),
            "contradictions": self.find_contradictions(limit=20),
            "onboard_check": self.maintenance_check(target_score=90),
            "agent": {"status": "ready", "enabled": True, "oauth_configured": True},
            "allowed_job_names": ["sync", "embed", "lint"],
        }


class RagApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.admin = User(username="admin", password_hash="hash", role="admin", nickname="Admin")
        self.employee = User(username="employee", password_hash="hash", role="employee", nickname="Employee")
        self.db.add_all([self.admin, self.employee])
        self.db.commit()
        self.original_status = rag_api.get_gbrain_admin_status
        self.original_compile = rag_api.compile_company_wiki_sources
        self.original_adapter = rag_api.GBrainAdapter
        self.original_load_settings = rag_api.load_gbrain_settings
        self.original_citation_load_settings = citation_fixer_jobs.load_gbrain_settings
        self.original_citation_adapter = citation_fixer_jobs.GBrainAdapter
        self.original_contradiction_load_settings = contradiction_probe.load_gbrain_settings
        self.original_contradiction_adapter = contradiction_probe.GBrainAdapter
        self.original_contradiction_run_cli = contradiction_probe._run_cli_command
        self.original_dream_load_settings = dream_cycle.load_gbrain_settings
        self.original_dream_adapter = dream_cycle.GBrainAdapter
        self.original_worker_dream_tick = maintenance_worker.run_dream_cycle_tick
        self.original_worker_poll_jobs = maintenance_worker.poll_dream_cycle_jobs
        self.original_query_regression = rag_api._run_query_regression_cases
        self.original_think_regression = rag_api._run_think_regression_cases
        self.env_backup = {
            key: os.environ.get(key)
            for key in ("GBRAIN_COMPANY_GBRAIN_READY_PATH", "GBRAIN_DOTENV_AUTOLOAD")
        }
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        os.environ["GBRAIN_COMPANY_GBRAIN_READY_PATH"] = str(self.root / "derived")
        os.environ["GBRAIN_DOTENV_AUTOLOAD"] = "false"
        (self.root / "derived" / ".pending_review" / "standards").mkdir(parents=True)
        (self.root / "derived" / ".pending_review" / "standards" / "standard.md").write_text(
            "---\nreview_status: pending_review\n---\n\n# standard\n",
            encoding="utf-8",
        )

        class _Settings:
            company_source_id = "company-wiki"
            raw_path = self.root / "raw"
            derived_path = self.root / "derived"
            gbrain_ready_path = self.root / "derived"
            manifests_path = self.root / "manifests"
            home_path = self.root
            cli_workdir = self.root / "gbrain-cli"
            bun_executable = "bun"

        rag_api.load_gbrain_settings = lambda: _Settings()
        citation_fixer_jobs.load_gbrain_settings = lambda: _Settings()
        contradiction_probe.load_gbrain_settings = lambda: _Settings()
        dream_cycle.load_gbrain_settings = lambda: _Settings()
        rag_api.GBrainAdapter = _FakeGBrainAdapter
        citation_fixer_jobs.GBrainAdapter = _FakeGBrainAdapter
        contradiction_probe.GBrainAdapter = _FakeGBrainAdapter
        dream_cycle.GBrainAdapter = _FakeGBrainAdapter
        contradiction_probe._run_cli_command = self._fake_contradiction_probe_cli
        _FakeGBrainAdapter.submitted_jobs = []
        _FakeGBrainAdapter.job_status_by_id = {}
        (self.root / "manifests").mkdir(parents=True, exist_ok=True)
        (self.root / "gbrain-cli" / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "gbrain-cli" / "src" / "cli.ts").write_text("// fake cli\n", encoding="utf-8")

        (self.root / "derived" / "people").mkdir(parents=True, exist_ok=True)
        (self.root / "derived" / "companies").mkdir(parents=True, exist_ok=True)
        (self.root / "derived" / "people" / "Jane.md").write_text(
            "---\n"
            "title: Jane Doe\n"
            "content_kind: customer_contact_profile\n"
            "linked_companies:\n"
            "  - \"[[companies/Acme Ltd]]\"\n"
            "---\n\n"
            "# Jane Doe\n",
            encoding="utf-8",
        )

    def tearDown(self):
        rag_api.get_gbrain_admin_status = self.original_status
        rag_api.compile_company_wiki_sources = self.original_compile
        rag_api.GBrainAdapter = self.original_adapter
        rag_api.load_gbrain_settings = self.original_load_settings
        citation_fixer_jobs.load_gbrain_settings = self.original_citation_load_settings
        citation_fixer_jobs.GBrainAdapter = self.original_citation_adapter
        contradiction_probe.load_gbrain_settings = self.original_contradiction_load_settings
        contradiction_probe.GBrainAdapter = self.original_contradiction_adapter
        contradiction_probe._run_cli_command = self.original_contradiction_run_cli
        dream_cycle.load_gbrain_settings = self.original_dream_load_settings
        dream_cycle.GBrainAdapter = self.original_dream_adapter
        maintenance_worker.run_dream_cycle_tick = self.original_worker_dream_tick
        maintenance_worker.poll_dream_cycle_jobs = self.original_worker_poll_jobs
        rag_api._run_query_regression_cases = self.original_query_regression
        rag_api._run_think_regression_cases = self.original_think_regression
        for key, value in self.env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()
        self.db.close()

    def _fake_contradiction_probe_cli(self, command, *, cwd, env, timeout_seconds):
        report = {
            "schema_version": 1,
            "queries_evaluated": 1,
            "queries_with_contradiction": 1,
            "total_contradictions_flagged": 1,
            "per_query": [
                {
                    "query": "书面化原则是什么",
                    "contradictions": [
                        {"severity": "high", "a": {"slug": "rules/a"}, "b": {"slug": "rules/b"}},
                    ],
                }
            ],
        }
        return {"returncode": 0, "stdout": json.dumps(report), "stderr": "ok"}

    def test_admin_can_refresh_and_read_gbrain_status(self):
        rag_api.get_gbrain_admin_status = lambda: {
            "ok": True,
            "indexed_files": 1,
            "indexed_chunks": 2,
            "embedding_model": "ollama:mxbai-embed-large",
            "service": {"status": "ok"},
        }
        rag_api.compile_company_wiki_sources = lambda settings, enable_pdf_structured_extraction=None: {
            "summary": {"total": 1, "compiled": 1, "skipped": 0, "failed": 0},
            "items": [
                {
                    "status": "compiled",
                    "target_file": ".pending_review/standards/standard.md",
                    "review_status": "pending_review",
                }
            ],
        }

        refresh = rag_api.refresh_knowledge(None, self.admin, self.db)
        status = rag_api.knowledge_status(self.admin, self.db)

        self.assertTrue(refresh["ok"])
        self.assertEqual(refresh["indexed"], 1)
        self.assertEqual(refresh["chunks"], 2)
        self.assertEqual(refresh["pending_reviews_created"], 1)
        self.assertEqual(status["indexed_chunks"], 2)
        self.assertEqual(self.db.query(KnowledgeReview).count(), 1)

    def test_employee_cannot_use_admin_knowledge_endpoints(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.refresh_knowledge(None, self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)
        self.assertEqual(exc.exception.detail, "仅管理员可操作")

    def test_admin_can_run_gbrain_regression_report(self):
        rag_api._run_query_regression_cases = lambda: {
            "ok": True,
            "total": 6,
            "passed": 6,
            "failed": 0,
            "preflight_failures": [],
            "cases": [{"id": "written_principle", "ok": True}],
        }
        rag_api._run_think_regression_cases = lambda: {
            "ok": True,
            "total": 1,
            "passed": 1,
            "failed": 0,
            "preflight_failures": [],
            "cases": [{"id": "written_principle_think", "ok": True}],
        }

        result = rag_api.knowledge_regression(True, self.admin, self.db)

        self.assertTrue(result["ok"])
        self.assertTrue(result["id"].startswith("gbrain-quality-"))
        self.assertEqual(result["query"]["passed"], 6)
        self.assertEqual(result["think"]["passed"], 1)
        self.assertEqual(result["summary"]["query"]["failed"], 0)
        report_path = self.root / "manifests" / "gbrain-quality-reports.json"
        self.assertTrue(report_path.exists())
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report_payload["reports"][0]["id"], result["id"])
        status = rag_api.knowledge_status(self.admin, self.db)
        self.assertEqual(status["quality_reports"]["latest"]["id"], result["id"])
        self.assertEqual(status["quality_reports"]["trend"][0]["id"], result["id"])
        self.assertEqual(status["quality_reports"]["trend"][0]["query_pass_rate"], 1.0)
        exported = rag_api.get_quality_report(result["id"], self.admin, self.db)
        self.assertEqual(exported["id"], result["id"])
        latest_export = rag_api.get_quality_report("latest", self.admin, self.db)
        self.assertEqual(latest_export["id"], result["id"])
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_regression").one()
        self.assertIn("include_think=True", audit.detail)
        self.assertIn(f"report_id={result['id']}", audit.detail)

    def test_employee_cannot_run_gbrain_regression_report(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.knowledge_regression(False, self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_employee_cannot_export_gbrain_quality_report(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.get_quality_report("latest", self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_admin_can_view_gbrain_maintenance_snapshot(self):
        result = rag_api.gbrain_maintenance(self.admin, self.db)

        self.assertTrue(result["ok"])
        self.assertEqual(result["doctor_summary"]["health_score"], 95)
        self.assertEqual(result["jobs"]["result"][0]["name"], "sync")
        self.assertEqual(result["contradictions"]["result"]["contradictions"][0]["severity"], "medium")
        self.assertEqual(result["agent"]["status"], "ready")

    def test_admin_can_submit_cancel_and_retry_gbrain_job(self):
        submit = rag_api.submit_gbrain_job(
            rag_api.GBrainJobSubmitRequest(name="sync", data={"sourceId": "company-wiki"}),
            self.admin,
            self.db,
        )
        cancel = rag_api.cancel_gbrain_job(11, self.admin, self.db)
        retry = rag_api.retry_gbrain_job(11, self.admin, self.db)

        self.assertEqual(submit["status"], "ok")
        self.assertEqual(cancel["result"]["status"], "cancelled")
        self.assertEqual(retry["result"]["status"], "waiting")
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_job_submit").count(), 1)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_job_cancel").count(), 1)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_job_retry").count(), 1)
        notifications = self.db.query(Notification).filter(Notification.action_kind == "open_settings").all()
        self.assertEqual(len(notifications), 3)
        self.assertTrue(all('"tab":"gbrain"' in item.action_payload_json for item in notifications))

    def test_admin_can_run_gbrain_maintenance_check(self):
        result = rag_api.gbrain_maintenance_check(90, self.admin, self.db)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["result"]["mode"], "check")
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_maintenance_check").one()
        self.assertIn("ok=True", audit.detail)

    def test_admin_can_configure_and_run_gbrain_dream_cycle(self):
        config = rag_api.update_gbrain_dream_cycle(
            rag_api.GBrainDreamCycleConfigRequest(
                enabled=True,
                interval_hours=24,
                target_score=88,
                source_id="company-wiki",
                job_names=["autopilot-cycle"],
            ),
            self.admin,
            self.db,
        )
        result = rag_api.run_gbrain_dream_cycle(True, self.admin, self.db)

        self.assertTrue(config["ok"])
        self.assertTrue(config["config"]["enabled"])
        self.assertEqual(config["config"]["interval_hours"], 24)
        self.assertTrue((self.root / "manifests" / "gbrain-dream-cycle.json").exists())
        self.assertTrue(result["ran"])
        self.assertEqual(result["jobs"][0]["name"], "autopilot-cycle")
        self.assertEqual(result["jobs"][0]["result"]["status"], "ok")
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_dream_cycle_update").count(), 1)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_dream_cycle_run").count(), 1)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain Dream Cycle 已执行").one()
        self.assertEqual(notification.action_kind, "open_settings")

    def test_admin_can_tick_and_poll_gbrain_dream_cycle_jobs(self):
        rag_api.update_gbrain_dream_cycle(
            rag_api.GBrainDreamCycleConfigRequest(
                enabled=True,
                interval_hours=24,
                target_score=88,
                source_id="company-wiki",
                job_names=["autopilot-cycle"],
            ),
            self.admin,
            self.db,
        )

        tick = rag_api.tick_gbrain_dream_cycle(self.admin, self.db)
        job_id = tick["config"]["tracked_jobs"][0]["job_id"]
        _FakeGBrainAdapter.job_status_by_id[job_id] = "completed"
        first_poll = rag_api.poll_gbrain_dream_cycle_jobs(self.admin, self.db)
        second_poll = rag_api.poll_gbrain_dream_cycle_jobs(self.admin, self.db)

        self.assertTrue(tick["ran"])
        self.assertEqual(tick["config"]["tracked_jobs"][0]["name"], "autopilot-cycle")
        self.assertEqual(first_poll["checked"], 1)
        self.assertEqual(first_poll["transitions"][0]["status"], "completed")
        self.assertEqual(second_poll["transitions"], [])
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_dream_cycle_tick").count(), 1)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_dream_cycle_poll_jobs").count(), 2)
        completion = self.db.query(Notification).filter(Notification.title == "GBrain Dream Cycle 任务完成").one()
        self.assertIn(f"job_id={job_id}", completion.content)

    def test_gbrain_maintenance_worker_runs_tick_and_poll_once(self):
        rag_api.update_gbrain_dream_cycle(
            rag_api.GBrainDreamCycleConfigRequest(
                enabled=True,
                interval_hours=24,
                target_score=88,
                source_id="company-wiki",
                job_names=["autopilot-cycle"],
            ),
            self.admin,
            self.db,
        )

        first = maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)
        job_id = first["tick"]["config"]["tracked_jobs"][0]["job_id"]
        _FakeGBrainAdapter.job_status_by_id[job_id] = "completed"
        second = maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)
        third = maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)

        self.assertTrue(first["ok"])
        self.assertTrue(first["tick"]["ran"])
        self.assertEqual(second["poll"]["transitions"][0]["status"], "completed")
        self.assertEqual(third["poll"]["transitions"], [])
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "gbrain_dream_cycle_worker_tick").count(), 3)
        submitted = self.db.query(Notification).filter(Notification.title == "GBrain Dream Cycle 定时任务已提交").one()
        self.assertIn("worker", submitted.content)
        completed = self.db.query(Notification).filter(Notification.title == "GBrain Dream Cycle 任务完成").one()
        self.assertIn(f"job_id={job_id}", completed.content)

    def test_gbrain_maintenance_worker_notifies_admin_on_error(self):
        def _raise_tick(*, actor="system"):
            raise RuntimeError("dream worker failed")

        maintenance_worker.run_dream_cycle_tick = _raise_tick

        with self.assertRaises(RuntimeError):
            maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)

        status = maintenance_worker.get_gbrain_maintenance_worker_status()
        self.assertIn("dream worker failed", status["last_error"])
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 维护 Worker 异常").one()
        self.assertEqual(notification.severity, "critical")
        self.assertIn("dream worker failed", notification.content)
        audit = self.db.query(AuditLog).filter(AuditLog.action == "gbrain_dream_cycle_worker_error").one()
        self.assertFalse(audit.success)

    def test_admin_can_configure_and_run_contradiction_probe(self):
        config = rag_api.update_gbrain_contradiction_probe(
            rag_api.GBrainContradictionProbeConfigRequest(
                enabled=True,
                interval_hours=24,
                source_id="company-wiki",
                queries=["书面化原则是什么"],
                top_k=3,
                budget_usd=0.25,
            ),
            self.admin,
            self.db,
        )

        result = rag_api.run_gbrain_contradiction_probe(True, self.admin, self.db)

        self.assertTrue(config["ok"])
        self.assertTrue((self.root / "manifests" / "gbrain-contradiction-probe.json").exists())
        self.assertTrue((self.root / "manifests" / "gbrain-contradiction-probe-queries.jsonl").exists())
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["total_contradictions_flagged"], 1)
        self.assertEqual(result["summary"]["severity_counts"]["high"], 1)
        self.assertEqual(result["latest_contradictions"]["status"], "ok")
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_contradiction_probe_run").one()
        self.assertIn("flagged=1", audit.detail)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 冲突探针已运行").one()
        self.assertIn("flagged=1", notification.content)

    def test_gbrain_maintenance_worker_runs_contradiction_probe_when_due(self):
        rag_api.update_gbrain_contradiction_probe(
            rag_api.GBrainContradictionProbeConfigRequest(
                enabled=True,
                interval_hours=24,
                source_id="company-wiki",
                queries=["书面化原则是什么"],
                top_k=3,
                budget_usd=0.25,
            ),
            self.admin,
            self.db,
        )

        result = maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)

        self.assertTrue(result["ok"])
        self.assertTrue(result["contradiction_probe"]["ran"])
        self.assertEqual(result["contradiction_probe"]["summary"]["total_contradictions_flagged"], 1)
        audit = self.db.query(AuditLog).filter(AuditLog.action == "gbrain_dream_cycle_worker_tick").one()
        self.assertIn("contradiction_probe_ran=True", audit.detail)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 冲突探针已运行").one()
        self.assertIn("worker", notification.content)

    def test_admin_can_submit_gbrain_citation_fixer_agent_task(self):
        result = rag_api.submit_gbrain_citation_fixer(
            rag_api.GBrainCitationFixerRequest(
                page_slug="rules/written-principle",
                review_id=7,
                notes="Fix citation format only.",
                allowed_slug_prefixes=["rules/"],
            ),
            self.admin,
            self.db,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["name"], "subagent")
        self.assertTrue(result["tracking"]["tracked"])
        state_path = self.root / "manifests" / "gbrain-citation-fixer-jobs.json"
        self.assertTrue(state_path.exists())
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_citation_fixer_submit").one()
        self.assertIn("review_id=7", audit.detail)
        notifications = self.db.query(Notification).filter(Notification.action_kind == "open_settings").all()
        self.assertEqual(len(notifications), 1)

    def test_admin_can_poll_completed_citation_fixer_and_reconcile_sidecar(self):
        derived = self.root / "derived"
        canonical = derived / "reviews" / "citation-fixer-smoke.md"
        sidecar = derived / ".sources" / "company-wiki" / "reviews" / "citation-fixer-smoke.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("old citation\n", encoding="utf-8")
        sidecar.write_text("fixed citation\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(derived), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.name", "Project R Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "commit", "-m", "Initial"], check=True, capture_output=True, text=True)

        submit = rag_api.submit_gbrain_citation_fixer(
            rag_api.GBrainCitationFixerRequest(
                page_slug="reviews/citation-fixer-smoke",
                allowed_slug_prefixes=["reviews/*"],
            ),
            self.admin,
            self.db,
        )
        job_id = submit["result"]["id"]
        _FakeGBrainAdapter.job_status_by_id[job_id] = "completed"

        poll = rag_api.poll_gbrain_citation_fixer_jobs(self.admin, self.db)

        self.assertEqual(poll["transitions"][0]["status"], "completed")
        self.assertEqual(poll["transitions"][0]["reconcile"]["status"], "synced_to_gbrain_ready")
        self.assertEqual(canonical.read_text(encoding="utf-8"), "fixed citation\n")
        self.assertFalse(sidecar.exists())
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_citation_fixer_poll_jobs").one()
        self.assertIn("transitions=1", audit.detail)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 引用修复任务完成").one()
        self.assertIn(f"job_id={job_id}", notification.content)

    def test_admin_can_rollback_completed_citation_fixer_result(self):
        derived = self.root / "derived"
        canonical = derived / "reviews" / "citation-fixer-rollback.md"
        sidecar = derived / ".sources" / "company-wiki" / "reviews" / "citation-fixer-rollback.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("old rollback citation\n", encoding="utf-8")
        sidecar.write_text("fixed rollback citation\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(derived), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.name", "Project R Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "commit", "-m", "Initial"], check=True, capture_output=True, text=True)

        submit = rag_api.submit_gbrain_citation_fixer(
            rag_api.GBrainCitationFixerRequest(
                page_slug="reviews/citation-fixer-rollback",
                allowed_slug_prefixes=["reviews/*"],
            ),
            self.admin,
            self.db,
        )
        job_id = submit["result"]["id"]
        _FakeGBrainAdapter.job_status_by_id[job_id] = "completed"
        poll = rag_api.poll_gbrain_citation_fixer_jobs(self.admin, self.db)
        self.assertEqual(canonical.read_text(encoding="utf-8"), "fixed rollback citation\n")
        self.assertTrue(poll["transitions"][0]["reconcile"]["git"]["commit_hash"])

        rollback = rag_api.rollback_gbrain_citation_fixer_job(job_id, self.admin, self.db)

        self.assertTrue(rollback["ok"])
        self.assertEqual(rollback["status"], "rolled_back")
        self.assertEqual(canonical.read_text(encoding="utf-8"), "old rollback citation\n")
        self.assertFalse(sidecar.exists())
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_citation_fixer_rollback").one()
        self.assertIn(f"job_id={job_id}", audit.detail)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 引用修复已回滚").one()
        self.assertIn(f"job_id={job_id}", notification.content)

    def test_gbrain_maintenance_worker_polls_citation_fixer_jobs(self):
        derived = self.root / "derived"
        canonical = derived / "reviews" / "citation-fixer-worker-smoke.md"
        sidecar = derived / ".sources" / "company-wiki" / "reviews" / "citation-fixer-worker-smoke.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("old worker citation\n", encoding="utf-8")
        sidecar.write_text("fixed worker citation\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(derived), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "config", "user.name", "Project R Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(derived), "commit", "-m", "Initial"], check=True, capture_output=True, text=True)

        submit = rag_api.submit_gbrain_citation_fixer(
            rag_api.GBrainCitationFixerRequest(
                page_slug="reviews/citation-fixer-worker-smoke",
                allowed_slug_prefixes=["reviews/*"],
            ),
            self.admin,
            self.db,
        )
        job_id = submit["result"]["id"]
        _FakeGBrainAdapter.job_status_by_id[job_id] = "completed"

        result = maintenance_worker.run_gbrain_maintenance_worker_once(session_factory=SessionLocal)

        self.assertTrue(result["ok"])
        self.assertEqual(result["citation_fixer_poll"]["transitions"][0]["status"], "completed")
        self.assertEqual(canonical.read_text(encoding="utf-8"), "fixed worker citation\n")
        self.assertFalse(sidecar.exists())
        audit = self.db.query(AuditLog).filter(AuditLog.action == "gbrain_dream_cycle_worker_tick").one()
        self.assertIn("citation_fixer_transitions=1", audit.detail)
        notification = self.db.query(Notification).filter(Notification.title == "GBrain 引用修复任务完成").one()
        self.assertIn(f"job_id={job_id}", notification.content)

    def test_admin_can_view_gbrain_entity_merge_candidates(self):
        result = rag_api.gbrain_entity_merge_candidates("company-wiki", "Jane Doe", 20, self.admin, self.db)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_id"], "company-wiki")
        self.assertTrue(any(item["title"] == "Acme Ltd" for item in result["candidates"]))
        candidate = next(item for item in result["candidates"] if item["title"] == "Acme Ltd")
        self.assertEqual(candidate["candidate_type"], "unresolved_entity")
        self.assertEqual(candidate["suggested_action"], "create_entity_page")
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_entity_merge_candidates_view").one()
        self.assertIn("source_id=company-wiki", audit.detail)

    def test_admin_can_create_entity_page_from_merge_candidate(self):
        candidates = rag_api.gbrain_entity_merge_candidates("company-wiki", "Jane Doe", 20, self.admin, self.db)["candidates"]
        candidate = next(item for item in candidates if item["title"] == "Acme Ltd")

        result = rag_api.gbrain_entity_merge_candidate_action(
            rag_api.GBrainEntityMergeActionRequest(
                source_id="company-wiki",
                candidate_id=candidate["id"],
                action="create_entity_page",
            ),
            self.admin,
            self.db,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "created")
        created = self.root / "derived" / "companies" / "Acme Ltd.md"
        self.assertTrue(created.exists())
        text = created.read_text(encoding="utf-8")
        self.assertIn("graph_status: pending_enrichment", text)
        self.assertEqual(result["sync"]["status"], "ok")
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_entity_merge_candidate_action").one()
        self.assertIn("action=create_entity_page", audit.detail)

    def test_admin_can_record_alias_review_from_duplicate_candidate(self):
        (self.root / "derived" / "companies" / "Acme Ltd.md").write_text(
            "---\n"
            "title: Acme Ltd\n"
            "content_kind: customer_company_profile\n"
            "---\n\n"
            "# Acme Ltd\n",
            encoding="utf-8",
        )
        (self.root / "derived" / "companies" / "Acme Ltd duplicate.md").write_text(
            "---\n"
            "title: Acme Ltd\n"
            "content_kind: customer_company_profile\n"
            "---\n\n"
            "# Acme Ltd duplicate\n",
            encoding="utf-8",
        )
        (self.root / "derived" / "people" / "Bob.md").write_text(
            "---\n"
            "title: Bob Buyer\n"
            "content_kind: customer_contact_profile\n"
            "linked_companies:\n"
            "  - companies/Acme Ltd duplicate.md\n"
            "---\n\n"
            "# Bob Buyer\n",
            encoding="utf-8",
        )
        candidates = rag_api.gbrain_entity_merge_candidates("company-wiki", "Acme Ltd", 20, self.admin, self.db)["candidates"]
        candidate = next(item for item in candidates if item["candidate_type"] == "duplicate_entity_pages")

        preview = rag_api.gbrain_entity_merge_candidate_preview("company-wiki", candidate["id"], self.admin, self.db)

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["status"], "preview_ready")
        self.assertEqual(preview["stats"]["planned_relink_changes"], 1)
        self.assertEqual(preview["planned_relink_changes"][0]["page_title"], "Bob Buyer")
        self.assertIn("linked_companies", preview["planned_relink_changes"][0]["diff_preview"])

        relink = rag_api.gbrain_entity_merge_candidate_action(
            rag_api.GBrainEntityMergeActionRequest(
                source_id="company-wiki",
                candidate_id=candidate["id"],
                action="apply_relink_changes",
            ),
            self.admin,
            self.db,
        )

        self.assertTrue(relink["ok"])
        self.assertEqual(relink["status"], "relink_applied")
        self.assertEqual(relink["sync"]["status"], "ok")
        bob_text = (self.root / "derived" / "people" / "Bob.md").read_text(encoding="utf-8")
        self.assertIn("- companies/Acme Ltd.md", bob_text)
        self.assertNotIn("- companies/Acme Ltd duplicate.md", bob_text)
        self.assertIn("project_r_entity_relink_last_candidate_id", bob_text)

        result = rag_api.gbrain_entity_merge_candidate_action(
            rag_api.GBrainEntityMergeActionRequest(
                source_id="company-wiki",
                candidate_id=candidate["id"],
                action="record_alias",
            ),
            self.admin,
            self.db,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "alias_recorded")
        self.assertEqual(result["sync"]["status"], "ok")
        created = self.root / "derived" / result["created_file"]
        self.assertTrue(created.exists())
        text = created.read_text(encoding="utf-8")
        self.assertIn("content_kind: entity_alias_override", text)
        self.assertIn("canonical_entity: Acme Ltd", text)
        self.assertIn("管理员已确认", text)
        audit = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "admin_gbrain_entity_merge_candidate_action")
            .filter(AuditLog.detail.contains("action=record_alias"))
            .one()
        )
        self.assertIn("action=record_alias", audit.detail)

    def test_employee_cannot_use_gbrain_jobs(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.submit_gbrain_job(rag_api.GBrainJobSubmitRequest(name="sync"), self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
