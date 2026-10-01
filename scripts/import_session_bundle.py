#!/usr/bin/env python3
"""Import a Telethon session and Telegram API settings from a protected ZIP."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import one Telethon .session and app_id/app_hash from a protected ZIP. "
            "All unrelated archive entries are ignored."
        )
    )
    parser.add_argument("bundle", type=Path, help="Path to the protected session ZIP")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root; defaults to the parent of scripts/",
    )
    return parser.parse_args()


def load_session_files(bundle_path: Path) -> tuple[bytes, int, str]:
    try:
        with ZipFile(bundle_path) as bundle:
            session_names = [name for name in bundle.namelist() if name.lower().endswith(".session")]
            if len(session_names) != 1:
                raise RuntimeError(
                    f"expected exactly one .session file in bundle, found {len(session_names)}"
                )

            candidates: list[tuple[int, str]] = []
            for name in bundle.namelist():
                if not name.lower().endswith(".json"):
                    continue
                try:
                    payload = json.loads(bundle.read(name).decode("utf-8-sig"))
                    app_id = int(payload["app_id"])
                    app_hash = str(payload["app_hash"]).strip()
                except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if app_id > 0 and app_hash:
                    candidates.append((app_id, app_hash))

            if len(candidates) != 1:
                raise RuntimeError(
                    "expected exactly one JSON file containing app_id and app_hash"
                )

            session_data = bundle.read(session_names[0])
    except BadZipFile as error:
        raise RuntimeError("bundle is not a valid ZIP file") from error

    if not session_data.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("the .session file is not a SQLite Telethon session")
    app_id, app_hash = candidates[0]
    return session_data, app_id, app_hash


def render_env(template: str, app_id: int, app_hash: str) -> str:
    lines: list[str] = []
    found_id = False
    found_hash = False
    for line in template.splitlines():
        if line.startswith("TELEGRAM_API_ID="):
            lines.append(f"TELEGRAM_API_ID={app_id}")
            found_id = True
        elif line.startswith("TELEGRAM_API_HASH="):
            lines.append(f"TELEGRAM_API_HASH={app_hash}")
            found_hash = True
        else:
            lines.append(line)
    if not found_id or not found_hash:
        raise RuntimeError(".env.example has no Telegram API placeholders")
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    bundle_path = args.bundle.expanduser().resolve()
    project_dir = args.project_dir.expanduser().resolve()
    env_example = project_dir / ".env.example"
    env_path = project_dir / ".env"
    data_dir = project_dir / "data"
    session_path = data_dir / "telegram.session"

    if not bundle_path.is_file():
        raise SystemExit(f"error: bundle not found: {bundle_path}")
    if not env_example.is_file():
        raise SystemExit(f"error: project .env.example not found: {env_example}")
    existing = [str(path) for path in (env_path, session_path) if path.exists()]
    if existing:
        raise SystemExit(
            "error: refusing to overwrite existing local credentials: " + ", ".join(existing)
        )

    try:
        session_data, app_id, app_hash = load_session_files(bundle_path)
        env_data = render_env(env_example.read_text(encoding="utf-8"), app_id, app_hash)
        data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(data_dir, 0o700)
        atomic_write(session_path, session_data, 0o600)
        atomic_write(env_path, env_data.encode("utf-8"), 0o600)
    except Exception as error:
        session_path.unlink(missing_ok=True)
        env_path.unlink(missing_ok=True)
        raise SystemExit(f"error: {error}") from error

    print("Session bundle imported locally.")
    print(f"Session: {session_path}")
    print(f"Settings: {env_path}")
    print("Unrelated archive entries were ignored.")


if __name__ == "__main__":
    main()
