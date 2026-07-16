"""Safe, serializable timing reports for document processing."""

from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Iterator


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PipelineTimer:
    """Collect stage durations without recording exception or infrastructure details."""

    def __init__(self) -> None:
        self.started_at = _iso_now()
        self._started = perf_counter()
        self.stages: list[dict] = []

    @contextmanager
    def stage(self, key: str, label: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        except Exception:
            self._append(key, label, started, "failed")
            raise
        else:
            self._append(key, label, started, "success")

    def skip(self, key: str, label: str) -> None:
        self.stages.append(
            {"key": key, "label": label, "elapsed_ms": 0.0, "status": "skipped"}
        )

    def report(self, status: str) -> dict:
        return {
            "version": 1,
            "status": status,
            "started_at": self.started_at,
            "completed_at": _iso_now(),
            "total_ms": round(max(0.0, (perf_counter() - self._started) * 1000), 1),
            "stages": list(self.stages),
        }

    def _append(self, key: str, label: str, started: float, status: str) -> None:
        self.stages.append(
            {
                "key": key,
                "label": label,
                "elapsed_ms": round(max(0.0, (perf_counter() - started) * 1000), 1),
                "status": status,
            }
        )
