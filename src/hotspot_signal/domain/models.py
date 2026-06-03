from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourceConfig:
    name: str
    url: str
    kind: str
    category: str = "general"
    reliability: float = 0.60
    weight: float = 1.0
    enabled: bool = True
    max_items: int | None = None
    items_path: str | None = None
    title_fields: list[str] = field(default_factory=lambda: ["title"])
    url_fields: list[str] = field(default_factory=lambda: ["url", "link"])
    summary_fields: list[str] = field(default_factory=lambda: ["summary", "description", "desc"])
    published_fields: list[str] = field(default_factory=lambda: ["published_at", "published", "pubDate", "date"])
    heat_fields: list[str] = field(default_factory=lambda: ["hot", "heat", "score"])
    html_title_selector: str | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HotspotItem:
    title: str
    source_name: str
    source_kind: str
    source_category: str
    source_reliability: float
    source_weight: float
    rank: int
    fetched_at: datetime
    url: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    heat: float | None = None

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fetched_at"] = self.fetched_at.isoformat()
        data["published_at"] = self.published_at.isoformat() if self.published_at else None
        return data


@dataclass(slots=True)
class TopicCandidate:
    title: str
    score: float
    heat_score: float
    freshness_score: float
    scarcity_score: float
    impact_score: float
    reliability_score: float
    risk_penalty: float
    competition_level: str
    safety_note: str
    suggested_angle: str
    verification_queries: list[str]
    reasons: list[str]
    source_names: list[str]
    links: list[str]
    item_count: int
    first_seen_at: datetime
    latest_seen_at: datetime
    representative_summary: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["first_seen_at"] = self.first_seen_at.isoformat()
        data["latest_seen_at"] = self.latest_seen_at.isoformat()
        return data


@dataclass(slots=True)
class FetchError:
    source_name: str
    message: str


@dataclass(slots=True)
class FetchBatch:
    items: list[HotspotItem]
    errors: list[FetchError]
    fetched_at: datetime
