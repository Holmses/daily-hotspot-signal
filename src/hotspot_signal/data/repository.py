from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from hotspot_signal.config import AppConfig
from hotspot_signal.domain.models import FetchBatch, TopicCandidate


class TopicRepository:
    def __init__(self, config: AppConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir

    def ensure_directories(self) -> None:
        for path in (
            self.raw_data_dir,
            self.processed_data_dir,
            self.reports_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def raw_data_dir(self) -> Path:
        return self.base_dir / self.config.paths.raw_data_dir

    @property
    def processed_data_dir(self) -> Path:
        return self.base_dir / self.config.paths.processed_data_dir

    @property
    def reports_dir(self) -> Path:
        return self.base_dir / self.config.paths.reports_dir

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / self.config.paths.logs_dir

    def write_raw_batch(self, batch: FetchBatch, run_date: date) -> Path:
        output_path = self.raw_data_dir / f"hotspots-raw-{run_date:%Y%m%d}-{batch.fetched_at:%H%M%S}.json"
        payload = {
            "fetched_at": batch.fetched_at.isoformat(),
            "items": [item.to_json_dict() for item in batch.items],
            "errors": [
                {"source_name": error.source_name, "message": error.message}
                for error in batch.errors
            ],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    def write_candidates(self, candidates: list[TopicCandidate], run_date: date) -> Path:
        output_path = self.processed_data_dir / f"topic-candidates-{run_date:%Y%m%d}.json"
        payload = {
            "run_date": run_date.isoformat(),
            "candidates": [candidate.to_json_dict() for candidate in candidates],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    def write_report(self, markdown: str, run_date: date) -> Path:
        output_path = self.reports_dir / f"hotspot-report-{run_date:%Y%m%d}.md"
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def load_recent_titles(self, run_date: date, days: int) -> list[str]:
        cutoff = run_date - timedelta(days=max(days, 0))
        titles: list[str] = []
        for path in sorted(self.processed_data_dir.glob("topic-candidates-*.json")):
            file_date = _date_from_candidate_filename(path)
            if file_date is None or file_date >= run_date or file_date < cutoff:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for candidate in payload.get("candidates", []):
                title = candidate.get("title")
                if title:
                    titles.append(str(title))
        return titles


def _date_from_candidate_filename(path: Path) -> date | None:
    stem = path.stem
    raw = stem.removeprefix("topic-candidates-")
    if len(raw) != 8 or not raw.isdigit():
        return None
    return datetime.strptime(raw, "%Y%m%d").date()
