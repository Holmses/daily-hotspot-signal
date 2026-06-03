from __future__ import annotations

import argparse
from pathlib import Path

from hotspot_signal.config import load_config, load_env_file
from hotspot_signal.scheduler.daily import run_daily_workflow, run_fetch_workflow, run_scheduler


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily low-competition hotspot topic CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_sources = subparsers.add_parser("list-sources", help="List enabled and disabled sources")
    list_sources.add_argument("--config", default="configs/sources.toml.example")

    fetch = subparsers.add_parser("fetch", help="Fetch raw hotspot items and write a raw JSON cache")
    fetch.add_argument("--config", default="configs/sources.toml.example")
    fetch.add_argument("--as-of", default=None, help="Report date in ISO format, defaults to today")

    run_daily = subparsers.add_parser("run-daily", help="Fetch sources, score topics, and write a report once")
    run_daily.add_argument("--config", default="configs/sources.toml.example")
    run_daily.add_argument("--as-of", default=None, help="Report date in ISO format, defaults to today")
    run_daily.add_argument("--no-notify", action="store_true", help="Skip Feishu notification even when configured")

    scheduler = subparsers.add_parser(
        "run-scheduler",
        help="Run the daily workflow on a fixed local time inside a long-running process",
    )
    scheduler.add_argument("--config", default="configs/sources.toml.example")
    scheduler.add_argument("--run-at", default=None, help="Daily run time, defaults to [runtime].daily_run_time")
    scheduler.add_argument("--timezone", default=None, help="Scheduler timezone, defaults to [runtime].timezone")
    scheduler.add_argument("--run-on-start", action="store_true")
    scheduler.add_argument("--no-notify", action="store_true", help="Skip Feishu notification even when configured")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    base_dir = Path.cwd()
    load_env_file(base_dir / ".env")
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = base_dir / config_path
    config = load_config(config_path)

    if args.command == "list-sources":
        for source in config.sources:
            state = "enabled" if source.enabled else "disabled"
            print(f"{source.name}\t{state}\t{source.kind}\t{source.category}\t{source.url}")
        return 0

    if not config.enabled_sources:
        parser.exit(1, "No enabled sources. Enable at least one [[sources]] entry in the config.\n")

    if args.command == "fetch":
        batch, raw_path = run_fetch_workflow(config=config, base_dir=base_dir, as_of=args.as_of)
        print(f"Raw hotspot cache written to: {raw_path}")
        print(f"items={len(batch.items)}")
        print(f"errors={len(batch.errors)}")
        for error in batch.errors:
            print(f"error[{error.source_name}]={error.message}")
        return 0

    if args.command == "run-daily":
        result = run_daily_workflow(
            config=config,
            base_dir=base_dir,
            as_of=args.as_of,
            notify=not args.no_notify,
        )
        print("Hotspot report generated")
        print(f"sources={result.source_count}")
        print(f"raw_items={result.raw_item_count}")
        print(f"candidates={result.candidate_count}")
        print(f"errors={result.error_count}")
        print(f"raw_path={result.raw_path}")
        print(f"candidates_path={result.candidates_path}")
        print(f"report_path={result.report_path}")
        print("feishu=skipped" if result.notification_result is None else f"feishu_status={result.notification_result.status_code}")
        return 0

    if args.command == "run-scheduler":
        run_scheduler(
            config=config,
            base_dir=base_dir,
            run_at=args.run_at,
            timezone=args.timezone,
            run_on_start=args.run_on_start,
            notify=not args.no_notify,
        )
        return 0

    parser.exit(2, f"Unknown command: {args.command}\n")


if __name__ == "__main__":
    raise SystemExit(main())
