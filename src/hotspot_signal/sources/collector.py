from __future__ import annotations

from datetime import datetime

from hotspot_signal.config import AppConfig
from hotspot_signal.domain.models import FetchBatch, FetchError, HotspotItem
from hotspot_signal.sources.http import HttpClient
from hotspot_signal.sources.parsers import parse_source_text
from hotspot_signal.utils.dates import now_in_timezone


def fetch_all_sources(
    config: AppConfig,
    now: datetime | None = None,
    client: HttpClient | None = None,
) -> FetchBatch:
    fetched_at = now or now_in_timezone(config.runtime.timezone)
    http_client = client or HttpClient(verify_ssl=config.runtime.verify_ssl)
    items: list[HotspotItem] = []
    errors: list[FetchError] = []

    for source in config.enabled_sources:
        try:
            response = http_client.get_text(source.url)
            source_items = parse_source_text(source, response.text, fetched_at)
            items.extend(source_items)
        except Exception as error:  # pragma: no cover - network failures are environment-specific
            errors.append(FetchError(source_name=source.name, message=str(error)))

    return FetchBatch(items=items, errors=errors, fetched_at=fetched_at)
