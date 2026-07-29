"""Apply timeline entries as backdated local commits and build replay queue."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.git_utils import commit_with_dates, ensure_clean_main, git, rev_parse
from scripts.templates.patches import apply_template

CONFIG_PATH = ROOT / "data" / "config.yaml"
TIMELINE_PATH = ROOT / "data" / "timeline.json"
QUEUE_DIR = ROOT / "queue" / "runtime"
PENDING_PATH = QUEUE_DIR / "pending.jsonl"

GENERATED_PATHS = [
    "docs",
    "CHANGELOG.md",
    "src/colla/files.py",
    "src/colla/config.py",
    "src/colla/batch.py",
    "src/colla/logutil.py",
    "tests/test_files.py",
]


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reset_repo_state() -> None:
    git("checkout", "main")
    git("reset", "--hard", "HEAD")
    for rel in GENERATED_PATHS:
        target = ROOT / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    bootstrap_readme = (
        "# colla\n\nSmall Python CLI for file and config helpers.\n\n"
        "## Install\n\n```bash\npip install -e .\n```\n\n"
        "## Usage\n\n```bash\ncolla --help\n```\n"
    )
    (ROOT / "README.md").write_text(bootstrap_readme, encoding="utf-8")
    bootstrap_cli = '''"""CLI entry point."""

import argparse

from colla import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="colla", description="File and config helpers")
    parser.add_argument("--version", action="version", version=f"colla {__version__}")
    parser.parse_args()


if __name__ == "__main__":
    main()
'''
    (ROOT / "src/colla/cli.py").write_text(bootstrap_cli, encoding="utf-8")
    (ROOT / "src/colla/__init__.py").write_text(
        '"""colla — file and config helper CLI."""\n\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (ROOT / "pyproject.toml").write_text(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8").replace(
            'dependencies = ["PyYAML>=6.0"]', "dependencies = []"
        ),
        encoding="utf-8",
    )


def append_queue(entry: dict) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    with PENDING_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def clear_queue() -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text("", encoding="utf-8")
    (QUEUE_DIR / "done.jsonl").write_text("", encoding="utf-8")
    (QUEUE_DIR / "failed.jsonl").write_text("", encoding="utf-8")


def commit_bootstrap_if_dirty(authors: dict) -> None:
    """Commit reset_repo_state file rewrites so ensure_clean_main can pass."""
    status = git("status", "--porcelain").stdout.strip()
    if not status:
        return
    for rel in (
        "README.md",
        "src/colla/cli.py",
        "src/colla/__init__.py",
        "pyproject.toml",
    ):
        if (ROOT / rel).exists():
            git("add", "--", rel)
    staged = git("diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return
    author = authors["githen-cmd"]
    commit_with_dates(
        "chore: reset bootstrap for history replay",
        author["name"],
        author["email"],
        "2018-01-01T09:00:00-02:00",
    )


def build_history(timeline: list[dict], authors: dict, reset: bool) -> None:
    if reset:
        clear_queue()
        reset_repo_state()
        commit_bootstrap_if_dirty(authors)

    ensure_clean_main()

    for unit in timeline:
        base_sha = rev_parse("HEAD")
        commit_shas: list[str] = []

        for commit in unit["commits"]:
            apply_template(commit["template"])
            author_cfg = authors[unit["author"]]
            sha = commit_with_dates(
                commit["message"],
                author_cfg["name"],
                author_cfg["email"],
                commit["date"],
            )
            commit_shas.append(sha)

        pr = unit["pr"]
        if pr.get("review_kind") == "request_changes":
            fix_author = authors[unit["author"]]
            last_date = unit["commits"][-1]["date"]
            apply_template("bump_patch_version")
            fix_sha = commit_with_dates(
                pr.get("fix_message", "fix: address review feedback"),
                fix_author["name"],
                fix_author["email"],
                last_date,
            )
            commit_shas.append(fix_sha)

        entry = {
            "id": unit["id"],
            "branch": unit["branch"],
            "author": unit["author"],
            "base_sha": base_sha,
            "tip_sha": commit_shas[-1],
            "commit_shas": commit_shas,
            "commit_count": len(commit_shas),
            "pr": pr,
        }
        append_queue(entry)

    print(f"Built {len(timeline)} PR units. Queue: {PENDING_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build backdated commit history")
    parser.add_argument("--timeline", type=Path, default=TIMELINE_PATH)
    parser.add_argument("--no-reset", action="store_true", help="Append without clearing queue/repo")
    args = parser.parse_args()

    cfg = load_config()
    with args.timeline.open(encoding="utf-8") as fh:
        timeline = json.load(fh)

    build_history(timeline, cfg["authors"], reset=not args.no_reset)


if __name__ == "__main__":
    main()
