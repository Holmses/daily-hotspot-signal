from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from hotspot_signal.config import StrategyConfig
from hotspot_signal.domain.models import HotspotItem, TopicCandidate
from hotspot_signal.utils.text import compact_reason_list, contains_any, normalize_title, title_similarity


@dataclass(slots=True)
class _Cluster:
    items: list[HotspotItem]

    @property
    def representative(self) -> HotspotItem:
        return sorted(self.items, key=lambda item: (item.rank, -item.source_reliability))[0]


def score_topics(
    items: list[HotspotItem],
    strategy: StrategyConfig,
    recent_titles: list[str] | None = None,
    now: datetime | None = None,
) -> list[TopicCandidate]:
    if not items:
        return []

    resolved_now = now or max(item.fetched_at for item in items)
    clusters = _cluster_items(items, threshold=strategy.title_similarity_threshold)
    heat_max_by_source = _heat_max_by_source(items)
    recent = recent_titles or []

    candidates = [
        _score_cluster(cluster, strategy, recent, resolved_now, heat_max_by_source)
        for cluster in clusters
    ]
    candidates = [candidate for candidate in candidates if candidate.score >= strategy.min_score]
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[: strategy.top_n]


def _cluster_items(items: list[HotspotItem], threshold: float) -> list[_Cluster]:
    ordered = sorted(items, key=lambda item: (item.rank, -item.source_reliability))
    clusters: list[_Cluster] = []
    for item in ordered:
        title = normalize_title(item.title)
        if not title:
            continue
        best_cluster: _Cluster | None = None
        best_score = 0.0
        for cluster in clusters:
            score = title_similarity(title, cluster.representative.title)
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is not None and best_score >= threshold:
            best_cluster.items.append(item)
        else:
            clusters.append(_Cluster(items=[item]))
    return clusters


def _score_cluster(
    cluster: _Cluster,
    strategy: StrategyConfig,
    recent_titles: list[str],
    now: datetime,
    heat_max_by_source: dict[str, float],
) -> TopicCandidate:
    representative = cluster.representative
    source_names = sorted({item.source_name for item in cluster.items})
    source_count = len(source_names)
    combined_text = " ".join(
        [item.title for item in cluster.items] + [item.summary or "" for item in cluster.items]
    )
    impact_hits = contains_any(combined_text, strategy.impact_keywords)
    authority_hits = contains_any(combined_text, strategy.authority_keywords)
    low_competition_hits = contains_any(combined_text, strategy.low_competition_clues)
    risk_hits = contains_any(combined_text, strategy.risk_keywords)
    hook_hits = contains_any(combined_text, strategy.hook_keywords)
    audience_hits = contains_any(combined_text, strategy.audience_keywords)
    seasonal_hits = contains_any(combined_text, strategy.seasonal_keywords)
    life_advice_hits = contains_any(combined_text, strategy.life_advice_keywords)
    recent_hit = any(
        title_similarity(representative.title, recent_title) >= strategy.title_similarity_threshold
        for recent_title in recent_titles
    )

    heat_score = min(
        100.0,
        max(_item_heat_score(item, heat_max_by_source) for item in cluster.items)
        + min(20.0, (source_count - 1) * 4.0),
    )
    freshness_score = max(_freshness_score(item, now, strategy.fresh_hours) for item in cluster.items)
    scarcity_score = _scarcity_score(
        source_count=source_count,
        recent_hit=recent_hit,
        low_competition_hits=low_competition_hits,
        authority_hits=authority_hits,
        category=representative.source_category,
        heat_score=heat_score,
    )
    impact_score = _impact_score(
        impact_hits=impact_hits,
        authority_hits=authority_hits,
        low_competition_hits=low_competition_hits,
        source_count=source_count,
        category=representative.source_category,
    )
    reliability_score = min(100.0, max(item.source_reliability for item in cluster.items) * 100.0)
    risk_penalty = _risk_penalty(risk_hits, reliability_score, cluster.items)
    viewer_interest_bonus = _viewer_interest_bonus(
        hook_hits=hook_hits,
        audience_hits=audience_hits,
        seasonal_hits=seasonal_hits,
        life_advice_hits=life_advice_hits,
    )
    total_score = (
        heat_score * 0.25
        + freshness_score * 0.20
        + scarcity_score * 0.25
        + impact_score * 0.20
        + reliability_score * 0.10
        + viewer_interest_bonus
        - min(30.0, risk_penalty)
    )

    if scarcity_score >= 75:
        competition_level = "低"
    elif scarcity_score >= 50:
        competition_level = "中"
    else:
        competition_level = "高"

    links = [item.url for item in cluster.items if item.url]
    latest_seen_at = max(item.fetched_at for item in cluster.items)
    first_seen_at = min(item.published_at or item.fetched_at for item in cluster.items)
    return TopicCandidate(
        title=representative.title,
        score=round(total_score, 2),
        heat_score=round(heat_score, 2),
        freshness_score=round(freshness_score, 2),
        scarcity_score=round(scarcity_score, 2),
        impact_score=round(impact_score, 2),
        reliability_score=round(reliability_score, 2),
        risk_penalty=round(risk_penalty, 2),
        competition_level=competition_level,
        safety_note=_safety_note(risk_hits, reliability_score, links, life_advice_hits),
        suggested_angle=_suggest_angle(
            representative.title,
            competition_level,
            representative.source_category,
            impact_hits,
            low_competition_hits,
            authority_hits,
            hook_hits,
            audience_hits,
            seasonal_hits,
            life_advice_hits,
        ),
        verification_queries=_verification_queries(representative.title),
        reasons=_reasons(
            heat_score=heat_score,
            freshness_score=freshness_score,
            scarcity_score=scarcity_score,
            impact_hits=impact_hits,
            authority_hits=authority_hits,
            low_competition_hits=low_competition_hits,
            recent_hit=recent_hit,
            risk_hits=risk_hits,
            hook_hits=hook_hits,
            audience_hits=audience_hits,
            seasonal_hits=seasonal_hits,
            life_advice_hits=life_advice_hits,
        ),
        source_names=source_names,
        links=links[:5],
        item_count=len(cluster.items),
        first_seen_at=first_seen_at,
        latest_seen_at=latest_seen_at,
        representative_summary=representative.summary,
    )


def _heat_max_by_source(items: list[HotspotItem]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in items:
        if item.heat is None or item.heat <= 0:
            continue
        value = math.log1p(item.heat)
        result[item.source_name] = max(result.get(item.source_name, 0.0), value)
    return result


def _item_heat_score(item: HotspotItem, heat_max_by_source: dict[str, float]) -> float:
    max_heat = heat_max_by_source.get(item.source_name, 0.0)
    if item.heat is not None and item.heat > 0 and max_heat > 0:
        base = math.log1p(item.heat) / max_heat * 100.0
    else:
        base = max(20.0, 100.0 - (item.rank - 1) * 4.0)
    return min(100.0, base * item.source_weight)


def _freshness_score(item: HotspotItem, now: datetime, fresh_hours: int) -> float:
    timestamp = item.published_at or item.fetched_at
    if timestamp.tzinfo is None and now.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=now.tzinfo)
    if now.tzinfo is None and timestamp.tzinfo is not None:
        now = now.replace(tzinfo=timestamp.tzinfo)
    age_hours = max((now - timestamp).total_seconds() / 3600.0, 0.0)
    half_life = max(float(fresh_hours), 1.0)
    return max(5.0, 100.0 * (0.5 ** (age_hours / half_life)))


def _scarcity_score(
    source_count: int,
    recent_hit: bool,
    low_competition_hits: list[str],
    authority_hits: list[str],
    category: str,
    heat_score: float,
) -> float:
    score = 60.0
    if source_count == 1:
        score += 22.0
    elif source_count == 2:
        score += 12.0
    elif source_count >= 5:
        score -= 25.0
    else:
        score -= 8.0
    if recent_hit:
        score -= 35.0
    if low_competition_hits:
        score += 16.0
    if authority_hits or category == "official":
        score += 10.0
    if heat_score >= 80 and source_count <= 2:
        score += 6.0
    if category == "trend":
        score -= 22.0
        if heat_score >= 80:
            score -= 8.0
    return max(0.0, min(100.0, score))


def _impact_score(
    impact_hits: list[str],
    authority_hits: list[str],
    low_competition_hits: list[str],
    source_count: int,
    category: str,
) -> float:
    score = 35.0 + min(35.0, len(impact_hits) * 10.0)
    score += min(18.0, len(authority_hits) * 6.0)
    score += min(14.0, len(low_competition_hits) * 7.0)
    score += min(10.0, source_count * 2.0)
    if category in {"official", "policy", "finance"}:
        score += 8.0
    return max(0.0, min(100.0, score))


def _risk_penalty(risk_hits: list[str], reliability_score: float, items: list[HotspotItem]) -> float:
    penalty = len(risk_hits) * 12.0
    if reliability_score < 55:
        penalty += 10.0
    if not any(item.url for item in items):
        penalty += 10.0
    return penalty


def _viewer_interest_bonus(
    hook_hits: list[str],
    audience_hits: list[str],
    seasonal_hits: list[str],
    life_advice_hits: list[str],
) -> float:
    score = 0.0
    if hook_hits:
        score += 6.0
    if audience_hits:
        score += 5.0
    if seasonal_hits:
        score += 4.0
    if life_advice_hits:
        score += 4.0
    if hook_hits and audience_hits and life_advice_hits:
        score += 5.0
    return min(20.0, score)


def _safety_note(
    risk_hits: list[str],
    reliability_score: float,
    links: list[str],
    life_advice_hits: list[str],
) -> str:
    if risk_hits:
        return f"含传闻风险词：{', '.join(risk_hits[:3])}；只讲已确认事实，不做定性结论。"
    if life_advice_hits:
        return "涉及饮食/健康/安全建议，需补营养师、医生、官方科普或原采访来源，不夸大结论。"
    if reliability_score < 55:
        return "来源可信度一般，发布前至少补一个主流媒体或官方来源。"
    if not links:
        return "缺少原文链接，需要先找到可引用来源。"
    return "可进入选题池；发布前仍需打开原文核对时间、上下文和引用。"


def _suggest_angle(
    title: str,
    competition_level: str,
    category: str,
    impact_hits: list[str],
    low_competition_hits: list[str],
    authority_hits: list[str],
    hook_hits: list[str],
    audience_hits: list[str],
    seasonal_hits: list[str],
    life_advice_hits: list[str],
) -> str:
    if hook_hits and (audience_hits or seasonal_hits) and life_advice_hits:
        return f"做成“谁在什么时间千万别做什么”：先讲结论，再讲原因和替代方案：{title}"
    if low_competition_hits or category == "official" or authority_hits:
        return f"别只看标题，文件/公告里最容易被忽略的一点：{title}"
    if competition_level == "低":
        return f"这个刚冒头的新信号，可能会影响谁：{title}"
    if impact_hits:
        return f"这件事的二阶影响是什么：{title}"
    return f"用 3 个问题讲清楚：{title}"


def _verification_queries(title: str) -> list[str]:
    compact = title.strip()
    return [
        compact,
        f"{compact} 影响",
        f"{compact} 官方 通报",
        f"{compact} 抖音 B站 最近24小时",
    ]


def _reasons(
    heat_score: float,
    freshness_score: float,
    scarcity_score: float,
    impact_hits: list[str],
    authority_hits: list[str],
    low_competition_hits: list[str],
    recent_hit: bool,
    risk_hits: list[str],
    hook_hits: list[str],
    audience_hits: list[str],
    seasonal_hits: list[str],
    life_advice_hits: list[str],
) -> list[str]:
    reasons: list[str] = []
    if heat_score >= 75:
        reasons.append("热度靠前")
    if freshness_score >= 75:
        reasons.append("新鲜度高")
    if scarcity_score >= 75:
        reasons.append("采集源重复度低")
    if impact_hits:
        reasons.append(f"冲击词：{', '.join(impact_hits[:3])}")
    if authority_hits:
        reasons.append(f"权威源线索：{', '.join(authority_hits[:2])}")
    if low_competition_hits:
        reasons.append(f"低竞争线索：{', '.join(low_competition_hits[:2])}")
    if hook_hits:
        reasons.append(f"强标题钩子：{', '.join(hook_hits[:2])}")
    if audience_hits or seasonal_hits:
        matched = ", ".join((audience_hits + seasonal_hits)[:3])
        reasons.append(f"明确人群/节点：{matched}")
    if life_advice_hits:
        reasons.append(f"生活建议线索：{', '.join(life_advice_hits[:2])}")
    if recent_hit:
        reasons.append("历史报告已出现，降低优先级")
    if risk_hits:
        reasons.append(f"需核验：{', '.join(risk_hits[:2])}")
    return compact_reason_list(reasons, limit=6)
