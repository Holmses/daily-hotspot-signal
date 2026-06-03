from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

from hotspot_signal.domain.models import SourceConfig


@dataclass(slots=True)
class RuntimeConfig:
    daily_run_time: str = "09:10"
    timezone: str = "Asia/Shanghai"
    verify_ssl: bool = True


@dataclass(slots=True)
class PathConfig:
    raw_data_dir: Path
    processed_data_dir: Path
    reports_dir: Path
    logs_dir: Path


@dataclass(slots=True)
class StrategyConfig:
    top_n: int = 10
    history_days: int = 14
    min_score: float = 45.0
    fresh_hours: int = 36
    max_items_per_source: int = 30
    title_similarity_threshold: float = 0.62
    authority_keywords: list[str] = field(default_factory=list)
    impact_keywords: list[str] = field(default_factory=list)
    risk_keywords: list[str] = field(default_factory=list)
    low_competition_clues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    runtime: RuntimeConfig
    paths: PathConfig
    strategy: StrategyConfig
    sources: list[SourceConfig]

    @property
    def enabled_sources(self) -> list[SourceConfig]:
        return [source for source in self.sources if source.enabled]


def load_env_file(env_path: str | Path) -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _list_value(data: dict, name: str, default: list[str] | None = None) -> list[str]:
    value = data.get(name, default or [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _source_from_dict(data: dict, default_max_items: int) -> SourceConfig:
    return SourceConfig(
        name=str(data["name"]),
        url=str(data["url"]),
        kind=str(data.get("kind", data.get("type", "rss"))).lower(),
        category=str(data.get("category", "general")),
        reliability=float(data.get("reliability", 0.60)),
        weight=float(data.get("weight", 1.0)),
        enabled=bool(data.get("enabled", True)),
        max_items=int(data.get("max_items", default_max_items)),
        items_path=data.get("items_path"),
        title_fields=_list_value(data, "title_fields", ["title"]),
        url_fields=_list_value(data, "url_fields", ["url", "link"]),
        summary_fields=_list_value(data, "summary_fields", ["summary", "description", "desc"]),
        published_fields=_list_value(data, "published_fields", ["published_at", "published", "pubDate", "date"]),
        heat_fields=_list_value(data, "heat_fields", ["hot", "heat", "score"]),
        html_title_selector=data.get("html_title_selector"),
        include_keywords=_list_value(data, "include_keywords"),
        exclude_keywords=_list_value(data, "exclude_keywords"),
    )


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    runtime_data = data.get("runtime", {})
    paths_data = data.get("paths", {})
    strategy_data = data.get("strategy", {})
    strategy = StrategyConfig(
        top_n=int(strategy_data.get("top_n", 10)),
        history_days=int(strategy_data.get("history_days", 14)),
        min_score=float(strategy_data.get("min_score", 45.0)),
        fresh_hours=int(strategy_data.get("fresh_hours", 36)),
        max_items_per_source=int(strategy_data.get("max_items_per_source", 30)),
        title_similarity_threshold=float(strategy_data.get("title_similarity_threshold", 0.62)),
        authority_keywords=_list_value(strategy_data, "authority_keywords"),
        impact_keywords=_list_value(strategy_data, "impact_keywords"),
        risk_keywords=_list_value(strategy_data, "risk_keywords"),
        low_competition_clues=_list_value(strategy_data, "low_competition_clues"),
    )
    extra_keywords = os.getenv("HOTSPOT_EXTRA_KEYWORDS", "").strip()
    if extra_keywords:
        strategy.impact_keywords.extend(
            keyword.strip() for keyword in extra_keywords.split(",") if keyword.strip()
        )

    default_max_items = strategy.max_items_per_source
    return AppConfig(
        runtime=RuntimeConfig(
            daily_run_time=str(runtime_data.get("daily_run_time", "09:10")),
            timezone=str(runtime_data.get("timezone", "Asia/Shanghai")),
            verify_ssl=_env_bool("HOTSPOT_VERIFY_SSL", runtime_data.get("verify_ssl", True)),
        ),
        paths=PathConfig(
            raw_data_dir=Path(paths_data.get("raw_data_dir", "data/raw")),
            processed_data_dir=Path(paths_data.get("processed_data_dir", "data/processed")),
            reports_dir=Path(paths_data.get("reports_dir", "reports/generated")),
            logs_dir=Path(paths_data.get("logs_dir", "logs")),
        ),
        strategy=strategy,
        sources=[_source_from_dict(item, default_max_items) for item in data.get("sources", [])],
    )


def _env_bool(name: str, default: object) -> bool:
    raw_value = os.getenv(name)
    value = default if raw_value is None else raw_value
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text not in {"0", "false", "no", "off"}
