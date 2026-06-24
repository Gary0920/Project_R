from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .settings import GBRAIN_CONTRADICTION_SEVERITIES, GBRAIN_JOB_STATUSES, GBRAIN_MAINTENANCE_JOB_NAMES


class GBrainMaintenanceClientMixin:
    def doctor(self) -> dict[str, Any]:
        return self._call_mcp_tool("run_doctor", {})

    def status_snapshot(self) -> dict[str, Any]:
        return self._call_mcp_tool("get_status_snapshot", {})

    def list_jobs(
        self,
        *,
        status: str | None = None,
        queue: str | None = None,
        name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
        if status:
            normalized_status = status.strip().lower()
            if normalized_status not in GBRAIN_JOB_STATUSES:
                return {
                    "status": "invalid_status",
                    "error": f"Unsupported GBrain job status: {status}",
                    "allowed_statuses": sorted(GBRAIN_JOB_STATUSES),
                }
            arguments["status"] = normalized_status
        if queue:
            arguments["queue"] = queue.strip()
        if name:
            arguments["name"] = name.strip()
        return self._call_mcp_tool("list_jobs", arguments)

    def get_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("get_job", {"id": int(job_id)})

    def get_job_progress(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("get_job_progress", {"id": int(job_id)})

    def submit_job(
        self,
        *,
        name: str,
        data: dict[str, Any] | None = None,
        queue: str | None = None,
        priority: int | float | None = None,
        max_attempts: int | None = None,
        delay: int | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        job_name = name.strip()
        if job_name not in GBRAIN_MAINTENANCE_JOB_NAMES:
            return {
                "status": "invalid_job_name",
                "error": f"Unsupported GBrain maintenance job: {name}",
                "allowed_names": sorted(GBRAIN_MAINTENANCE_JOB_NAMES),
            }
        if data is not None and not isinstance(data, dict):
            return {
                "status": "invalid_params",
                "error": "GBrain job data must be a JSON object",
            }
        arguments: dict[str, Any] = {
            "name": job_name,
            "data": data or {},
        }
        if queue:
            arguments["queue"] = queue.strip()
        if priority is not None:
            arguments["priority"] = priority
        if max_attempts is not None:
            arguments["max_attempts"] = max(1, int(max_attempts))
        if delay is not None:
            arguments["delay"] = max(0, int(delay))
        if timeout_ms is not None:
            arguments["timeout_ms"] = max(1000, int(timeout_ms))
        return self._call_mcp_tool("submit_job", arguments, timeout_seconds=max(self.settings.timeout_seconds, 15.0))

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("cancel_job", {"id": int(job_id)})

    def retry_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("retry_job", {"id": int(job_id)})

    def find_contradictions(
        self,
        *,
        slug: str | None = None,
        severity: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
        if slug:
            arguments["slug"] = slug.strip()
        if severity:
            normalized_severity = severity.strip().lower()
            if normalized_severity not in GBRAIN_CONTRADICTION_SEVERITIES:
                return {
                    "status": "invalid_severity",
                    "error": f"Unsupported contradiction severity: {severity}",
                    "allowed_severities": sorted(GBRAIN_CONTRADICTION_SEVERITIES),
                }
            arguments["severity"] = normalized_severity
        return self._call_mcp_tool("find_contradictions", arguments)

    def maintenance_check(self, *, target_score: int = 90) -> dict[str, Any]:
        return self._call_mcp_tool(
            "run_onboard",
            {
                "mode": "check",
                "target_score": max(1, min(int(target_score or 90), 100)),
            },
            timeout_seconds=max(self.settings.timeout_seconds, 30.0),
        )

    def maintenance_status(self) -> dict[str, Any]:
        doctor = self.doctor()
        status_snapshot = self.status_snapshot()
        jobs = self.list_jobs(limit=20)
        contradictions = self.find_contradictions(limit=20)
        onboard_check = self.maintenance_check(target_score=90)
        parts = [doctor, status_snapshot, jobs, contradictions, onboard_check]
        return {
            "ok": all(part.get("status") == "ok" for part in parts),
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "doctor": doctor,
            "doctor_summary": self._doctor_summary(doctor),
            "status_snapshot": status_snapshot,
            "jobs": jobs,
            "contradictions": contradictions,
            "onboard_check": onboard_check,
            "agent": self.agent_status(),
            "allowed_job_names": sorted(GBRAIN_MAINTENANCE_JOB_NAMES),
        }
