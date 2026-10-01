from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys
from pathlib import Path

from telethon import TelegramClient, errors

from chat_discovery.classify import KyivClassifier
from chat_discovery.config import Settings
from chat_discovery.export import export_candidates
from chat_discovery.filtering import CandidateFilters, filter_candidates
from chat_discovery.providers.searxng import SearxngProvider
from chat_discovery.providers.telegram import TelegramProvider
from chat_discovery.service import DiscoveryService
from chat_discovery.storage import Repository


CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "config"))
DEFAULT_QUERY_FILE = CONFIG_DIR / "queries-kyiv.txt"
OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def load_queries(path: Path) -> list[str]:
    queries: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if value and not value.startswith("#") and value not in queries:
            queries.append(value)
    return queries


def resolve_queries(query_file: Path | None, direct_queries: list[str]) -> list[str]:
    queries: list[str] = []
    if query_file is not None:
        queries.extend(load_queries(query_file))
    for raw_query in direct_queries:
        query = raw_query.strip()
        if query and query not in queries:
            queries.append(query)
    if not queries:
        queries = load_queries(DEFAULT_QUERY_FILE)
    return queries


def output_name(value: str) -> str:
    if not OUTPUT_NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "output name must be 1-64 characters: letters, digits, dot, underscore or hyphen"
        )
    return value


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def candidate_filters(args: argparse.Namespace) -> CandidateFilters:
    return CandidateFilters(
        min_members=args.min_members,
        min_messages=args.min_messages,
        min_unique_authors=args.min_unique_authors,
        max_days_since_last_message=args.max_days_since_last_message,
        entity_types=frozenset(args.entity_type),
        activity_statuses=frozenset(args.activity_status),
        captcha_statuses=frozenset(args.captcha_status),
    )


async def authorize(settings: Settings) -> None:
    api_id, api_hash = settings.require_telegram()
    settings.session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(settings.session_path), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Telegram session is already authorized.")
            return
        phone = getpass.getpass("Telegram phone (input hidden): ")
        sent = await client.send_code_request(phone)
        code = getpass.getpass("Telegram login code (input hidden): ")
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
        except errors.SessionPasswordNeededError:
            password = getpass.getpass("Telegram 2FA password (input hidden): ")
            await client.sign_in(password=password)
        print("Telegram session authorized and stored in the data directory.")
    finally:
        await client.disconnect()


async def discover(args: argparse.Namespace, settings: Settings) -> None:
    queries = resolve_queries(args.query_file, args.query)
    repository = Repository(settings.database_path)
    classifier = KyivClassifier(args.terms_file)
    service = DiscoveryService(repository, classifier)
    telegram = None
    try:
        if args.telegram or args.validate or args.activity_days > 0:
            api_id, api_hash = settings.require_telegram()
            telegram = TelegramProvider(
                api_id,
                api_hash,
                settings.session_path,
                limit_per_query=args.limit_per_query,
            )

        searxng = None
        if args.web:
            if not settings.searxng_url:
                raise RuntimeError("SEARXNG_URL is required when --web is enabled.")
            searxng = SearxngProvider(settings.searxng_url, limit_per_query=args.limit_per_query)

        if telegram is not None:
            async with telegram:
                result = await service.run(
                    queries,
                    args.input,
                    telegram,
                    searxng,
                    args.validate,
                    args.output_dir,
                    args.min_score,
                    args.output_name,
                    args.activity_days,
                    args.active_min_messages,
                    args.activity_max_messages,
                    candidate_filters(args),
                )
        else:
            result = await service.run(
                queries,
                args.input,
                None,
                searxng,
                False,
                args.output_dir,
                args.min_score,
                args.output_name,
                0,
                args.active_min_messages,
                args.activity_max_messages,
                candidate_filters(args),
            )

        print(f"Run {result['run_id']} completed: {result['discovered']} discovered, {result['total']} total.")
        for label, path in result["paths"].items():
            print(f"{label}: {path}")
    finally:
        repository.close()


def export_existing(args: argparse.Namespace, settings: Settings) -> None:
    repository = Repository(settings.database_path)
    try:
        candidates = repository.list_candidates()
        filters = candidate_filters(args)
        if filters.active:
            candidates = filter_candidates(candidates, filters)
        paths = export_candidates(candidates, args.output_dir, args.min_score, args.output_name)
        for label, path in paths.items():
            print(f"{label}: {path}")
    finally:
        repository.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover and export public Telegram groups and channels.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth", help="Authorize the local read-only MTProto session interactively.")

    discover_parser = subparsers.add_parser("discover", help="Run discovery, validation and export.")
    discover_parser.add_argument(
        "--query", action="append", default=[], help="Search query; repeat for multiple queries."
    )
    discover_parser.add_argument(
        "--query-file", type=Path, default=None, help="UTF-8 file with one search query per line."
    )
    discover_parser.add_argument("--terms-file", type=Path, default=CONFIG_DIR / "kyiv-terms.json")
    discover_parser.add_argument("--input", type=Path, action="append", default=[])
    discover_parser.add_argument("--output-dir", type=Path, default=Path("data/exports"))
    discover_parser.add_argument("--output-name", type=output_name, default="telegram-results")
    discover_parser.add_argument("--limit-per-query", type=int, default=30)
    discover_parser.add_argument("--min-score", type=int, default=0)
    discover_parser.add_argument("--telegram", action=argparse.BooleanOptionalAction, default=True)
    discover_parser.add_argument("--web", action=argparse.BooleanOptionalAction, default=False)
    discover_parser.add_argument("--validate", action=argparse.BooleanOptionalAction, default=True)
    discover_parser.add_argument(
        "--activity-days",
        type=non_negative_int,
        default=0,
        help="Scan public message history for this many days; 0 disables activity scanning.",
    )
    discover_parser.add_argument(
        "--active-min-messages",
        type=positive_int,
        default=10,
        help="Messages in the selected period required for status=active.",
    )
    discover_parser.add_argument(
        "--activity-max-messages",
        type=positive_int,
        default=5000,
        help="Safety cap per chat; capped metrics are marked as lower bounds.",
    )
    add_filter_arguments(discover_parser)

    export_parser = subparsers.add_parser("export", help="Rebuild exports from the current database.")
    export_parser.add_argument("--output-dir", type=Path, default=Path("data/exports"))
    export_parser.add_argument("--output-name", type=output_name, default="telegram-results")
    export_parser.add_argument("--min-score", type=int, default=0)
    add_filter_arguments(export_parser)
    return parser


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-members", type=non_negative_int, default=None)
    parser.add_argument("--min-messages", type=non_negative_int, default=None)
    parser.add_argument("--min-unique-authors", type=non_negative_int, default=None)
    parser.add_argument("--max-days-since-last-message", type=float, default=None)
    parser.add_argument(
        "--entity-type", action="append", choices=("group", "channel", "unknown"), default=[]
    )
    parser.add_argument(
        "--activity-status",
        action="append",
        choices=("active", "low_activity", "inactive", "unknown", "unavailable"),
        default=[],
    )
    parser.add_argument(
        "--captcha-status", action="append", choices=("yes", "no", "unknown"), default=[]
    )


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_environment()
    try:
        if args.command == "auth":
            asyncio.run(authorize(settings))
        elif args.command == "discover":
            asyncio.run(discover(args, settings))
        elif args.command == "export":
            export_existing(args, settings)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
