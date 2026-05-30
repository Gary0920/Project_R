import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.rag as rag_api
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.notification import Notification
from models.user import User


class _FakeGBrainAdapter:
    def __init__(self, settings=None):
        self.settings = settings

    def sync_source(self, **kwargs):
        return {"status": "ok", "result": {"chunksCreated": 2}}

    def start_http_service(self):
        return {"ok": True, "status": "started"}

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
        return {"status": "ok", "result": {"id": job_id, "name": "sync", "status": "waiting"}}

    def get_job_progress(self, job_id):
        return {"status": "ok", "result": {"id": job_id, "progress": {"phase": "queued"}}}

    def submit_job(self, **kwargs):
        if kwargs.get("name") == "shell":
            return {"status": "invalid_job_name", "error": "unsupported"}
        return {"status": "ok", "result": {"id": 11, "name": kwargs.get("name"), "status": "waiting"}}

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
        self.original_query_regression = rag_api._run_query_regression_cases
        self.original_think_regression = rag_api._run_think_regression_cases
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "derived" / ".pending_review" / "standards").mkdir(parents=True)
        (self.root / "derived" / ".pending_review" / "standards" / "standard.md").write_text(
            "---\nreview_status: pending_review\n---\n\n# standard\n",
            encoding="utf-8",
        )

        class _Settings:
            derived_path = self.root / "derived"

        rag_api.load_gbrain_settings = lambda: _Settings()
        rag_api.GBrainAdapter = _FakeGBrainAdapter

    def tearDown(self):
        rag_api.get_gbrain_admin_status = self.original_status
        rag_api.compile_company_wiki_sources = self.original_compile
        rag_api.GBrainAdapter = self.original_adapter
        rag_api.load_gbrain_settings = self.original_load_settings
        rag_api._run_query_regression_cases = self.original_query_regression
        rag_api._run_think_regression_cases = self.original_think_regression
        self.temp_dir.cleanup()
        self.db.close()

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
        self.assertEqual(result["query"]["passed"], 6)
        self.assertEqual(result["think"]["passed"], 1)
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_regression").one()
        self.assertIn("include_think=True", audit.detail)

    def test_employee_cannot_run_gbrain_regression_report(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.knowledge_regression(False, self.employee, self.db)

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
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_gbrain_citation_fixer_submit").one()
        self.assertIn("review_id=7", audit.detail)
        notifications = self.db.query(Notification).filter(Notification.action_kind == "open_settings").all()
        self.assertEqual(len(notifications), 1)

    def test_employee_cannot_use_gbrain_jobs(self):
        with self.assertRaises(HTTPException) as exc:
            rag_api.submit_gbrain_job(rag_api.GBrainJobSubmitRequest(name="sync"), self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
