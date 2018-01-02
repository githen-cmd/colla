"""Generate workday timeline with PR units for 2018-2022."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.templates.patches import pick_template, template_message

CONFIG_PATH = ROOT / "data" / "config.yaml"
OUTPUT_PATH = ROOT / "data" / "timeline.json"

PR_TITLES = [
    "Add {feature}",
    "Improve {feature}",
    "Fix edge case in {feature}",
    "Refactor {feature}",
    "Document {feature}",
    "Test coverage for {feature}",
]

PR_COMMENTS = [
    "Looks good — clean implementation.",
    "Nice work. Approved.",
    "Solid change; merging this.",
    "Good error handling here.",
    "Thanks — this reads well.",
    "LGTM after the small fix.",
]

REQUEST_CHANGES_COMMENTS = [
    "Could you add a guard for empty input?",
    "Please add a short docstring before merge.",
    "Minor: handle missing file path explicitly.",
]

FIX_MESSAGES = [
    "fix: address review feedback",
    "fix: handle edge case from review",
    "docs: add missing docstring",
]


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def is_workday(d: date, workdays: list[str]) -> bool:
    return d.strftime("%a") in workdays


def iter_workdays(start: date, end: date, workdays: list[str]):
    current = start
    while current <= end:
        if is_workday(current, workdays):
            yield current
        current += timedelta(days=1)


def random_time(rng: random.Random, tz: ZoneInfo) -> time:
    hour = rng.randint(9, 17)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return time(hour, minute, second)


def choose_commit_count(rng: random.Random, cfg: dict) -> int:
    weights = cfg["commits_per_day"]["weights"]
    values = list(range(cfg["commits_per_day"]["min"], cfg["commits_per_day"]["max"] + 1))
    return rng.choices(values, weights=weights, k=1)[0]


def split_into_prs(count: int, pr_min: int, pr_max: int, rng: random.Random) -> list[int]:
    sizes: list[int] = []
    remaining = count
    while remaining > 0:
        max_size = min(pr_max, remaining)
        min_size = pr_min
        if remaining <= pr_max:
            size = remaining
        else:
            size = rng.randint(min_size, max_size)
        sizes.append(size)
        remaining -= size
    return sizes


def branch_name(year: int, seq: int, template: str) -> str:
    slug = template.replace("_", "-")[:24]
    return f"feat/{year}-{seq:04d}-{slug}"


def pr_title(template: str, rng: random.Random) -> str:
    feature = template.replace("_", " ")
    return rng.choice(PR_TITLES).format(feature=feature)


def other_author(author: str, authors: dict) -> str:
    names = list(authors.keys())
    return names[(names.index(author) + 1) % len(names)]


def generate_timeline(cfg: dict, end_date: date) -> list[dict]:
    rng = random.Random(cfg.get("seed", 42))
    tz = ZoneInfo(cfg["timezone"])
    start = date.fromisoformat(cfg["start_date"])
    workdays = cfg["workdays"]
    authors = cfg["authors"]

    units: list[dict] = []
    pr_index = 0
    template_index_by_year: dict[str, int] = {}
    author_toggle = 0
    author_names = list(authors.keys())

    for day in iter_workdays(start, end_date, workdays):
        year = str(day.year)
        commit_count = choose_commit_count(rng, cfg)
        if commit_count == 0:
            continue

        pr_sizes = split_into_prs(commit_count, cfg["pr_size"]["min"], cfg["pr_size"]["max"], rng)
        idx = template_index_by_year.get(year, 0)

        for size in pr_sizes:
            author = author_names[author_toggle % len(author_names)]
            reviewer = other_author(author, authors)
            author_toggle += 1

            commits = []
            for _ in range(size):
                template = pick_template(year, idx)
                idx += 1
                when = datetime.combine(day, random_time(rng, tz), tzinfo=tz)
                commits.append(
                    {
                        "message": template_message(template),
                        "template": template,
                        "date": when.isoformat(),
                    }
                )

            review_kind = rng.choices(
                ["approve", "comment_then_approve", "request_changes"],
                weights=cfg["review_weights"],
                k=1,
            )[0]

            pr_index += 1
            branch = branch_name(day.year, pr_index, commits[0]["template"])
            unit = {
                "id": pr_index,
                "branch": branch,
                "author": author,
                "commits": commits,
                "pr": {
                    "title": pr_title(commits[0]["template"], rng),
                    "reviewer": reviewer,
                    "review_kind": review_kind,
                    "comment": rng.choice(PR_COMMENTS),
                    "request_changes_comment": rng.choice(REQUEST_CHANGES_COMMENTS),
                    "fix_message": rng.choice(FIX_MESSAGES),
                },
            }
            units.append(unit)

        template_index_by_year[year] = idx

    return units


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate collaboration timeline")
    parser.add_argument("--pilot", action="store_true", help="Stop at pilot_end_date (Jan-Mar 2018)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    cfg = load_config()
    end = date.fromisoformat(cfg["pilot_end_date"] if args.pilot else cfg["end_date"])
    units = generate_timeline(cfg, end)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump(units, fh, indent=2)

    total_commits = sum(len(u["commits"]) for u in units)
    print(f"Wrote {len(units)} PR units ({total_commits} commits) to {args.output}")


if __name__ == "__main__":
    main()
