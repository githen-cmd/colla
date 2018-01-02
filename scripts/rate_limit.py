"""GitHub API rate-limit helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone


class RateLimitError(Exception):
    def __init__(self, message: str, reset_at: int | None = None):
        super().__init__(message)
        self.reset_at = reset_at


def run_gh(args: list[str], *, token: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
        env=env,
    )


def parse_rate_limit_reset(stderr: str) -> int | None:
    match = re.search(r"rate limit.*?(\d{10})", stderr, re.I)
    if match:
        return int(match.group(1))
    return None


def gh_with_retry(args: list[str], *, token: str | None = None, max_retries: int = 4, delay: float = 30.0) -> str:
    last_err = ""
    for attempt in range(max_retries):
        result = run_gh(args, token=token, check=False)
        if result.returncode == 0:
            return result.stdout.strip()

        combined = (result.stderr or "") + (result.stdout or "")
        last_err = combined
        lower = combined.lower()
        if "rate limit" in lower or "secondary rate limit" in lower or result.returncode == 429:
            reset = parse_rate_limit_reset(combined)
            wait = delay * (2**attempt)
            if reset:
                wait = max(wait, reset - int(time.time()) + 1)
            time.sleep(wait)
            continue
        raise RuntimeError(f"gh {' '.join(args)} failed: {combined}")

    raise RateLimitError(last_err)


def switch_account(username: str) -> None:
    allowed = {"githen-cmd", "pedrosatotop"}
    if username not in allowed:
        raise ValueError(f"Refusing to switch to disallowed account: {username}")
    gh_with_retry(["auth", "switch", "--user", username])


def token_for_user(username: str) -> str | None:
    mapping = {
        "githen-cmd": os.environ.get("GH_TOKEN_GITHEN"),
        "pedrosatotop": os.environ.get("GH_TOKEN_PEDRO"),
    }
    return mapping.get(username)


def gh_as_user(args: list[str], username: str) -> str:
    token = token_for_user(username)
    if token:
        return gh_with_retry(args, token=token)
    switch_account(username)
    return gh_with_retry(args)


def sleep_between(delay: float) -> None:
    time.sleep(delay)


def load_done_ids(path) -> set[int]:
    done: set[int] = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        done.add(json.loads(line)["id"])
    return done


def count_done_today(path, cap_day: str | None = None) -> int:
    if not path.exists():
        return 0
    today = cap_day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("replayed_at", "").startswith(today):
            count += 1
    return count
