from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
import html
import json
import re
import xml.etree.ElementTree as ET

from hotspot_signal.domain.models import HotspotItem, SourceConfig
from hotspot_signal.utils.dates import parse_datetime
from hotspot_signal.utils.text import contains_any


def parse_source_text(source: SourceConfig, text: str, fetched_at: datetime) -> list[HotspotItem]:
    if source.kind == "rss":
        return parse_rss_source(source, text, fetched_at)
    if source.kind == "json":
        return parse_json_source(source, text, fetched_at)
    if source.kind == "html":
        return parse_html_source(source, text, fetched_at)
    raise ValueError(f"Unsupported source kind: {source.kind}")


def parse_json_source(source: SourceConfig, text: str, fetched_at: datetime) -> list[HotspotItem]:
    payload = _loads_json_or_jsonp(text)
    raw_items = _extract_items(payload, source.items_path)
    items: list[HotspotItem] = []
    for index, raw_item in enumerate(raw_items, start=1):
        title = _first_text(raw_item, source.title_fields)
        if not title:
            continue
        url = _first_text(raw_item, source.url_fields)
        summary = _first_text(raw_item, source.summary_fields)
        published_at = parse_datetime(_first_value(raw_item, source.published_fields))
        heat = _to_float(_first_value(raw_item, source.heat_fields))
        item = HotspotItem(
            title=title,
            url=url,
            summary=summary,
            published_at=published_at,
            heat=heat,
            source_name=source.name,
            source_kind=source.kind,
            source_category=source.category,
            source_reliability=source.reliability,
            source_weight=source.weight,
            rank=index,
            fetched_at=fetched_at,
        )
        if _item_allowed(item, source):
            items.append(item)
        if len(items) >= (source.max_items or 30):
            break
    return items


def parse_rss_source(source: SourceConfig, text: str, fetched_at: datetime) -> list[HotspotItem]:
    root = ET.fromstring(text.strip())
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))

    items: list[HotspotItem] = []
    for index, node in enumerate(nodes, start=1):
        title = _node_text(node, "title")
        link = _node_text(node, "link")
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href") if atom_link is not None else None
        summary = _node_text(node, "description") or _node_text(node, "summary")
        published = _node_text(node, "pubDate") or _node_text(node, "published") or _node_text(node, "updated")
        if not title:
            continue
        item = HotspotItem(
            title=html.unescape(title.strip()),
            url=link.strip() if link else None,
            summary=html.unescape(summary.strip()) if summary else None,
            published_at=parse_datetime(published),
            source_name=source.name,
            source_kind=source.kind,
            source_category=source.category,
            source_reliability=source.reliability,
            source_weight=source.weight,
            rank=index,
            fetched_at=fetched_at,
        )
        if _item_allowed(item, source):
            items.append(item)
        if len(items) >= (source.max_items or 30):
            break
    return items


def parse_html_source(source: SourceConfig, text: str, fetched_at: datetime) -> list[HotspotItem]:
    parser = _AnchorParser(source.html_title_selector)
    parser.feed(text)
    parser.close()

    seen_titles: set[str] = set()
    items: list[HotspotItem] = []
    for index, anchor in enumerate(parser.anchors, start=1):
        title = re.sub(r"\s+", " ", anchor.text).strip()
        if len(title) < 6 or title in seen_titles:
            continue
        seen_titles.add(title)
        item = HotspotItem(
            title=html.unescape(title),
            url=urljoin(source.url, anchor.href) if anchor.href else None,
            source_name=source.name,
            source_kind=source.kind,
            source_category=source.category,
            source_reliability=source.reliability,
            source_weight=source.weight,
            rank=index,
            fetched_at=fetched_at,
        )
        if _item_allowed(item, source):
            items.append(item)
        if len(items) >= (source.max_items or 30):
            break
    return items


def values_at_path(data: Any, path: str | None) -> list[Any]:
    if path is None or path == "":
        return [data]
    values = [data]
    for raw_part in path.split("."):
        expand = raw_part.endswith("[]")
        part = raw_part[:-2] if expand else raw_part
        next_values: list[Any] = []
        for value in values:
            current = _descend(value, part) if part else value
            if current is None:
                continue
            if expand and isinstance(current, list):
                next_values.extend(current)
            elif expand:
                next_values.append(current)
            else:
                next_values.append(current)
        values = next_values
    return values


def _loads_json_or_jsonp(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    starts = [index for index in (stripped.find("{"), stripped.find("[")) if index >= 0]
    ends = [index for index in (stripped.rfind("}"), stripped.rfind("]")) if index >= 0]
    if not starts or not ends:
        raise ValueError("Response is neither JSON nor JSONP")
    return json.loads(stripped[min(starts) : max(ends) + 1])


def _extract_items(payload: Any, items_path: str | None) -> list[Any]:
    if items_path:
        values = values_at_path(payload, items_path)
        return list(_flatten(values))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "list", "results", "news"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _extract_items(value, None)
                if nested:
                    return nested
    return []


def _flatten(values: Iterable[Any]) -> Iterable[Any]:
    for value in values:
        if isinstance(value, list):
            yield from value
        else:
            yield value


def _descend(value: Any, part: str) -> Any:
    if isinstance(value, dict):
        return value.get(part)
    if isinstance(value, list) and part.isdigit():
        index = int(part)
        return value[index] if 0 <= index < len(value) else None
    return None


def _first_value(data: Any, fields: list[str]) -> Any:
    if not isinstance(data, (dict, list)):
        return None
    for field in fields:
        values = values_at_path(data, field)
        for value in values:
            if value not in (None, ""):
                return value
    return None


def _first_text(data: Any, fields: list[str]) -> str | None:
    value = _first_value(data, fields)
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _node_text(node: ET.Element, tag: str) -> str | None:
    direct = node.find(tag)
    if direct is not None and direct.text:
        return direct.text
    namespaced = node.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    if namespaced is not None and namespaced.text:
        return namespaced.text
    return None


def _item_allowed(item: HotspotItem, source: SourceConfig) -> bool:
    text = f"{item.title} {item.summary or ''}"
    if source.include_keywords and not contains_any(text, source.include_keywords):
        return False
    if source.exclude_keywords and contains_any(text, source.exclude_keywords):
        return False
    return True


@dataclass(slots=True)
class _Anchor:
    href: str | None
    text: str


class _AnchorParser(HTMLParser):
    def __init__(self, selector: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.selector = selector or "a"
        self.anchors: list[_Anchor] = []
        self._stack: list[tuple[str, dict[str, str]]] = []
        self._capture_href: str | None = None
        self._capture_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        self._stack.append((tag, attr_map))
        if tag == "a" and self._matches_selector(attr_map):
            self._capture_href = attr_map.get("href")
            self._capture_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_href is not None:
            text = "".join(self._capture_text).strip()
            if text:
                self.anchors.append(_Anchor(href=self._capture_href, text=text))
            self._capture_href = None
            self._capture_text = []
        while self._stack:
            popped_tag, _ = self._stack.pop()
            if popped_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._capture_href is not None:
            self._capture_text.append(data)

    def _matches_selector(self, anchor_attrs: dict[str, str]) -> bool:
        selector = self.selector.strip()
        if selector in {"", "a"}:
            return True
        if selector.startswith("a."):
            expected = selector[2:]
            return expected in anchor_attrs.get("class", "").split()
        if selector == "span.titleline > a":
            if len(self._stack) < 2:
                return False
            parent_tag, parent_attrs = self._stack[-2]
            return parent_tag == "span" and "titleline" in parent_attrs.get("class", "").split()
        if ".titleline" in selector:
            return any(
                tag == "span" and "titleline" in attrs.get("class", "").split()
                for tag, attrs in self._stack
            )
        return True
