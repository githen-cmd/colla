"""Shared git helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=check,
    )


def git(*args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], env=env, check=check)


def rev_parse(ref: str = "HEAD") -> str:
    return git("rev-parse", ref).stdout.strip()


def current_branch() -> str:
    return git("branch", "--show-current").stdout.strip()


def ensure_clean_main() -> None:
    git("checkout", "main")
    status = git("status", "--porcelain").stdout.strip()
    if status:
        raise RuntimeError(f"Working tree not clean on main:\n{status}")


def commit_with_dates(
    message: str,
    author_name: str,
    author_email: str,
    when_iso: str,
) -> str:
    env = {
        "GIT_AUTHOR_DATE": when_iso,
        "GIT_COMMITTER_DATE": when_iso,
    }
    git("add", "-A")
    git(
        "-c",
        f"user.name={author_name}",
        "-c",
        f"user.email={author_email}",
        "commit",
        "-m",
        message,
        env=env,
    )
    return rev_parse("HEAD")
