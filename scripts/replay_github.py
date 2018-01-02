"""Replay pending PR units to GitHub with rate-limit pacing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.git_utils import git, run
from scripts.rate_limit import count_done_today, gh_as_user, load_done_ids, sleep_between

CONFIG_PATH = ROOT / "data" / "config.yaml"
QUEUE_DIR = ROOT / "queue"
PENDING_PATH = QUEUE_DIR / "pending.jsonl"
DONE_PATH = QUEUE_DIR / "done.jsonl"
FAILED_PATH = QUEUE_DIR / "failed.jsonl"
LOG_PATH = QUEUE_DIR / "replay.log"


def log(msg: str) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)
    print(msg)


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_pending() -> list[dict]:
    if not PENDING_PATH.exists():
        return []
    return [json.loads(line) for line in PENDING_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_line(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def ensure_remote_main_at(sha: str) -> None:
    git("fetch", "origin", "main")
    try:
        remote_sha = git("rev-parse", "origin/main").stdout.strip()
    except Exception:
        remote_sha = ""
    if remote_sha != sha:
        git("push", "origin", f"{sha}:refs/heads/main", "--force-with-lease")


def replay_one(entry: dict, repo: str, delay: float) -> dict:
    pr_meta = entry["pr"]
    author = entry["author"]
    reviewer = pr_meta["reviewer"]
    branch = entry["branch"]
    tip = entry["tip_sha"]
    base = entry["base_sha"]

    log(f"PR #{entry['id']}: ensure main at {base[:7]}")
    ensure_remote_main_at(base)

    log(f"PR #{entry['id']}: push branch {branch} as {author}")
    gh_as_user(["auth", "status"], author)
    run(["git", "push", "origin", f"{tip}:refs/heads/{branch}"], cwd=ROOT)

    sleep_between(delay)

    body = f"Backdated work replay for `{branch}`."
    pr_url = gh_as_user(
        [
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            pr_meta["title"],
            "--body",
            body,
        ],
        author,
    )
    pr_number = pr_url.rstrip("/").split("/")[-1]
    log(f"PR #{entry['id']}: opened #{pr_number}")

    sleep_between(delay)

    review_kind = pr_meta.get("review_kind", "approve")
    if review_kind == "comment_then_approve":
        gh_as_user(
            ["pr", "comment", pr_number, "--repo", repo, "--body", pr_meta["comment"]],
            reviewer,
        )
        sleep_between(delay)
        gh_as_user(
            ["pr", "review", pr_number, "--repo", repo, "--approve", "--body", "Approved after comment."],
            reviewer,
        )
    elif review_kind == "request_changes":
        gh_as_user(
            [
                "pr",
                "review",
                pr_number,
                "--repo",
                repo,
                "--request-changes",
                "--body",
                pr_meta.get("request_changes_comment", "Please address feedback."),
            ],
            reviewer,
        )
        sleep_between(delay)
        gh_as_user(
            ["pr", "review", pr_number, "--repo", repo, "--approve", "--body", "Thanks for the fix."],
            reviewer,
        )
    else:
        gh_as_user(
            ["pr", "review", pr_number, "--repo", repo, "--approve", "--body", pr_meta["comment"]],
            reviewer,
        )

    sleep_between(delay)

    gh_as_user(["pr", "merge", pr_number, "--repo", repo, "--merge", "--delete-branch"], reviewer)
    log(f"PR #{entry['id']}: merged #{pr_number}")

    git("fetch", "origin", "main")
    git("checkout", "main")
    git("reset", "--hard", "origin/main")

    return {
        **entry,
        "pr_number": int(pr_number),
        "pr_url": pr_url,
        "replayed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay PR queue to GitHub")
    parser.add_argument("--daily-cap", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max PRs this run")
    parser.add_argument("--resume", action="store_true", help="Skip IDs already in done.jsonl")
    args = parser.parse_args()

    cfg = load_config()
    replay_cfg = cfg.get("replay", {})
    daily_cap = args.daily_cap or replay_cfg.get("daily_cap", 20)
    delay = args.delay or replay_cfg.get("delay_seconds", 30)
    repo = cfg["repo"]

    done_ids = load_done_ids(DONE_PATH) if args.resume else set()
    already_today = count_done_today(DONE_PATH)
    remaining_today = max(0, daily_cap - already_today)

    if remaining_today == 0:
        log(f"Daily cap reached ({daily_cap}). Try again tomorrow.")
        return

    pending = [e for e in read_pending() if e["id"] not in done_ids]
    if args.limit:
        pending = pending[: args.limit]

    pending = pending[:remaining_today]
    if not pending:
        log("No pending PR units to replay.")
        return

    log(f"Replaying {len(pending)} PR(s) to {repo} (cap {daily_cap}/day)")

    for entry in pending:
        try:
            result = replay_one(entry, repo, delay)
            append_line(DONE_PATH, result)
        except Exception as exc:  # noqa: BLE001
            log(f"PR #{entry['id']} FAILED: {exc}")
            append_line(FAILED_PATH, {**entry, "error": str(exc)})


if __name__ == "__main__":
    main()
