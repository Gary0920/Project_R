from __future__ import annotations

from typing import Any


class GBrainRuntimeMixin:
    def _probe_service_health(self) -> dict[str, Any]:
        return self._runtime.probe_service_health()

    def service_process_status(self) -> dict[str, Any]:
        return self._runtime.service_process_status()

    def start_http_service(self) -> dict[str, Any]:
        return self._runtime.start_http_service()

    def stop_http_service(self) -> dict[str, Any]:
        return self._runtime.stop_http_service()

    def restart_http_service(self) -> dict[str, Any]:
        return self._runtime.restart_http_service()

    def _read_service_record(self) -> dict[str, Any]:
        return self._runtime.read_service_record()

    def _write_service_record(self, record: dict[str, Any]) -> None:
        self._runtime.write_service_record(record)

    def _delete_service_record(self) -> None:
        self._runtime.delete_service_record()

    def _clear_stale_pglite_state(self) -> None:
        self._runtime.clear_stale_pglite_state()
