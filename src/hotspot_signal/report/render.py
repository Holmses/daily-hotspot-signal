from __future__ import annotations

from datetime import date

from hotspot_signal.domain.models import FetchError, TopicCandidate


def render_markdown_report(
    run_date: date,
    candidates: list[TopicCandidate],
    source_count: int,
    raw_item_count: int,
    errors: list[FetchError],
) -> str:
    lines: list[str] = [
        f"# 每日低竞争热点选题雷达 - {run_date.isoformat()}",
        "",
        f"- 采集源：{source_count}",
        f"- 原始条目：{raw_item_count}",
        f"- 入选选题：{len(candidates)}",
        "",
        "## 今日优先选题",
        "",
    ]
    if not candidates:
        lines.extend(
            [
                "今天没有达到最低分的候选题。可以降低 `min_score`，或增加更贴近账号方向的数据源。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| 排名 | 分数 | 竞争 | 题目 | 推荐角度 | 核验提示 | 来源 |",
                "| --- | ---: | --- | --- | --- | --- | --- |",
            ]
        )
        for rank, candidate in enumerate(candidates, start=1):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rank),
                        f"{candidate.score:.2f}",
                        candidate.competition_level,
                        _escape(candidate.title),
                        _escape(candidate.suggested_angle),
                        _escape(candidate.safety_note),
                        _escape(", ".join(candidate.source_names)),
                    ]
                )
                + " |"
            )
        lines.append("")

    for rank, candidate in enumerate(candidates, start=1):
        lines.extend(_render_candidate_detail(rank, candidate))

    if errors:
        lines.extend(["## 采集错误", ""])
        for error in errors:
            lines.append(f"- {error.source_name}: {error.message}")
        lines.append("")

    lines.extend(
        [
            "## 发布前复核清单",
            "",
            "1. 打开原文链接，确认发布时间、原文上下文和是否为转述。",
            "2. 用报告给出的搜索词查抖音、B站、小红书、YouTube 最近 24 小时同角度数量。",
            "3. 如果包含“网传、爆料、疑似、传闻”等词，只讲已证实事实和待核实部分，不下结论。",
            "4. 时政、监管、司法、公司负面内容至少补一个官方或主流媒体来源。",
            "",
        ]
    )
    return "\n".join(lines)


def _render_candidate_detail(rank: int, candidate: TopicCandidate) -> list[str]:
    lines = [
        f"## {rank}. {candidate.title}",
        "",
        f"- 综合分：{candidate.score:.2f}",
        f"- 分项：热度 {candidate.heat_score:.1f} / 新鲜度 {candidate.freshness_score:.1f} / 稀缺度 {candidate.scarcity_score:.1f} / 冲击力 {candidate.impact_score:.1f} / 可信度 {candidate.reliability_score:.1f}",
        f"- 推荐角度：{candidate.suggested_angle}",
        f"- 安全提示：{candidate.safety_note}",
        f"- 入选理由：{'; '.join(candidate.reasons) if candidate.reasons else '暂无'}",
        "- 二创标题模板：",
    ]
    for title in _creator_titles(candidate.title):
        lines.append(f"  - {title}")
    if candidate.representative_summary:
        lines.append(f"- 摘要：{candidate.representative_summary}")
    if candidate.links:
        lines.append("- 原文链接：")
        for link in candidate.links:
            lines.append(f"  - {link}")
    lines.append("- 竞争度复核搜索词：")
    for query in candidate.verification_queries:
        lines.append(f"  - {query}")
    lines.append("")
    return lines


def _creator_titles(title: str) -> list[str]:
    compact = title.strip()
    return [
        f"看到“{compact}”，先别急着转发，真正该注意的是这几点",
        f"如果你身边有人正遇到这类情况，今天先把“{compact}”讲清楚",
        f"“{compact}”为什么会上热搜？普通人该怎么判断",
    ]


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
