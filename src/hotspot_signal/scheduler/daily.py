from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
import os
from pathlib import Path
import time as time_module
from zoneinfo import ZoneInfo

from hotspot_signal.config import AppConfig
from hotspot_signal.data.repository import TopicRepository
from hotspot_signal.domain.models import FetchBatch
from hotspot_signal.domain.models import TopicCandidate
from hotspot_signal.notify.feishu import FeishuSendResult, FeishuWebhookNotifier
from hotspot_signal.report.render import render_markdown_report
from hotspot_signal.sources.collector import fetch_all_sources
from hotspot_signal.sources.http import HttpClient
from hotspot_signal.strategy.scoring import score_topics
from hotspot_signal.utils.dates import now_in_timezone, report_date


@dataclass(slots=True)
class DailyRunResult:
    raw_path: Path
    candidates_path: Path
    report_path: Path
    source_count: int
    raw_item_count: int
    candidate_count: int
    error_count: int
    notification_result: FeishuSendResult | None = None


def run_fetch_workflow(
    config: AppConfig,
    base_dir: Path,
    as_of: str | None = None,
    client: HttpClient | None = None,
) -> tuple[FetchBatch, Path]:
    run_date = report_date(as_of, config.runtime.timezone)
    repository = TopicRepository(config=config, base_dir=base_dir)
    repository.ensure_directories()
    batch = fetch_all_sources(config=config, client=client)
    raw_path = repository.write_raw_batch(batch, run_date)
    return batch, raw_path


def run_daily_workflow(
    config: AppConfig,
    base_dir: Path,
    as_of: str | None = None,
    client: HttpClient | None = None,
    notify: bool = True,
) -> DailyRunResult:
    run_date = report_date(as_of, config.runtime.timezone)
    repository = TopicRepository(config=config, base_dir=base_dir)
    repository.ensure_directories()

    batch = fetch_all_sources(config=config, client=client)
    raw_path = repository.write_raw_batch(batch, run_date)
    recent_titles = repository.load_recent_titles(run_date, config.strategy.history_days)
    candidates = score_topics(
        items=batch.items,
        strategy=config.strategy,
        recent_titles=recent_titles,
        now=now_in_timezone(config.runtime.timezone),
    )
    candidates_path = repository.write_candidates(candidates, run_date)
    markdown = render_markdown_report(
        run_date=run_date,
        candidates=candidates,
        source_count=len(config.enabled_sources),
        raw_item_count=len(batch.items),
        errors=batch.errors,
    )
    report_path = repository.write_report(markdown, run_date)
    notification_result = None
    if notify:
        notification_result = send_daily_report_to_feishu(
            run_date=run_date,
            candidates=candidates,
            source_count=len(config.enabled_sources),
            raw_item_count=len(batch.items),
            error_count=len(batch.errors),
            report_path=report_path,
        )
    return DailyRunResult(
        raw_path=raw_path,
        candidates_path=candidates_path,
        report_path=report_path,
        source_count=len(config.enabled_sources),
        raw_item_count=len(batch.items),
        candidate_count=len(candidates),
        error_count=len(batch.errors),
        notification_result=notification_result,
    )


def send_daily_report_to_feishu(
    run_date: date,
    candidates: list[TopicCandidate],
    source_count: int,
    raw_item_count: int,
    error_count: int,
    report_path: Path,
) -> FeishuSendResult | None:
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        return None
    secret = os.getenv("FEISHU_SECRET", "").strip() or None
    text = daily_report_to_feishu_text(
        run_date=run_date,
        candidates=candidates,
        source_count=source_count,
        raw_item_count=raw_item_count,
        error_count=error_count,
        report_path=report_path,
    )
    return FeishuWebhookNotifier(webhook_url=webhook, secret=secret).send_text(text)


def daily_report_to_feishu_text(
    run_date: date,
    candidates: list[TopicCandidate],
    source_count: int,
    raw_item_count: int,
    error_count: int,
    report_path: Path,
) -> str:
    lines = [
        f"每日低竞争热点选题雷达 - {run_date.isoformat()}",
        f"采集源：{source_count} | 原始条目：{raw_item_count} | 入选选题：{len(candidates)} | 错误：{error_count}",
        f"报告：{report_path}",
        "",
        "今日优先选题：",
    ]
    if not candidates:
        lines.append("暂无达到最低分的候选题。")
    for index, candidate in enumerate(candidates[:10], start=1):
        lines.extend(
            [
                f"{index}. [{candidate.score:.1f} / 竞争{candidate.competition_level}] {candidate.title}",
                f"角度：{candidate.suggested_angle}",
                f"核验：{candidate.safety_note}",
            ]
        )
        if candidate.links:
            lines.append(f"链接：{candidate.links[0]}")
        lines.append("")
    lines.extend(
        [
            "发布前复核：",
            "1. 打开原文核对时间、上下文和来源。",
            "2. 查抖音、B站、小红书、YouTube 最近24小时同角度数量。",
            "3. 涉及时政、监管、司法、公司负面内容，至少补一个官方或主流媒体来源。",
        ]
    )
    return "\n".join(lines)


def parse_run_time(value: str) -> datetime_time:
    try:
        parsed = datetime_time.fromisoformat(value)
    except ValueError as error:
        raise ValueError("run time must use HH:MM or HH:MM:SS format") from error
    return parsed.replace(tzinfo=None)


def next_run_datetime(now: datetime, run_at: datetime_time) -> datetime:
    next_run = datetime.combine(now.date(), run_at, tzinfo=now.tzinfo)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def run_scheduler(
    config: AppConfig,
    base_dir: Path,
    run_at: str | None = None,
    timezone: str | None = None,
    run_on_start: bool = False,
    notify: bool = True,
) -> None:
    resolved_run_at = parse_run_time(run_at or config.runtime.daily_run_time)
    resolved_timezone = timezone or config.runtime.timezone
    tzinfo = ZoneInfo(resolved_timezone)

    def execute_once() -> None:
        started_at = datetime.now(tzinfo).isoformat(timespec="seconds")
        print(f"Starting hotspot workflow at {started_at}", flush=True)
        result = run_daily_workflow(config=config, base_dir=base_dir, notify=notify)
        _print_result(result)

    if run_on_start:
        execute_once()

    while True:
        now = datetime.now(tzinfo)
        next_run = next_run_datetime(now, resolved_run_at)
        sleep_seconds = max((next_run - now).total_seconds(), 1.0)
        print(f"Next hotspot workflow scheduled at {next_run.isoformat(timespec='seconds')}", flush=True)
        time_module.sleep(sleep_seconds)
        try:
            execute_once()
        except Exception as error:
            print(f"Hotspot workflow failed: {error}", flush=True)


def _print_result(result: DailyRunResult) -> None:
    print("Hotspot workflow completed", flush=True)
    print(f"sources={result.source_count}", flush=True)
    print(f"raw_items={result.raw_item_count}", flush=True)
    print(f"candidates={result.candidate_count}", flush=True)
    print(f"errors={result.error_count}", flush=True)
    print(f"raw_path={result.raw_path}", flush=True)
    print(f"candidates_path={result.candidates_path}", flush=True)
    print(f"report_path={result.report_path}", flush=True)
    if result.notification_result is None:
        print("feishu=skipped", flush=True)
    else:
        print(f"feishu_status={result.notification_result.status_code}", flush=True)
