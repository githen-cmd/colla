"""Template patches applied incrementally to build project history."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    path = ROOT / rel
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _append(rel: str, content: str) -> None:
    existing = _read(rel)
    _write(rel, existing + content)


def _replace(rel: str, old: str, new: str) -> None:
    text = _read(rel)
    if old not in text:
        raise ValueError(f"Pattern not found in {rel}: {old!r}")
    _write(rel, text.replace(old, new, 1))


def _bump_version(patch: bool = True) -> None:
    text = _read("src/colla/__init__.py")
    match = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', text)
    if not match:
        raise ValueError("Could not find __version__")
    major, minor, patch_num = map(int, match.groups())
    if patch:
        patch_num += 1
    else:
        minor += 1
        patch_num = 0
    new_ver = f"{major}.{minor}.{patch_num}"
    _write("src/colla/__init__.py", f'"""colla — file and config helper CLI."""\n\n__version__ = "{new_ver}"\n')


PatchFn = Callable[[], None]


def init_readme() -> None:
    _write(
        "README.md",
        "# colla\n\nSmall Python CLI for file and config utilities.\n\n"
        "## Install\n\n```bash\npip install -e .\n```\n\n"
        "## Usage\n\n```bash\ncolla --help\n```\n",
    )


def add_usage_section() -> None:
    _append("README.md", "\n## Commands\n\nRun `colla --version` to check the installed version.\n")


def add_dev_section() -> None:
    _append("README.md", "\n## Development\n\n```bash\npython -m pytest\n```\n")


def add_cli_help_text() -> None:
    _replace(
        "src/colla/cli.py",
        "    parser.parse_args()\n",
        '    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")\n'
        "    parser.parse_args()\n",
    )


def add_files_module() -> None:
    _write(
        "src/colla/files.py",
        '"""File helpers."""\n\nfrom pathlib import Path\n\n\n'
        "def read_text(path: str | Path, encoding: str = 'utf-8') -> str:\n"
        '    """Read a text file."""\n'
        "    return Path(path).read_text(encoding=encoding)\n\n\n"
        "def write_text(path: str | Path, content: str, encoding: str = 'utf-8') -> None:\n"
        '    """Write text to a file."""\n'
        "    p = Path(path)\n"
        "    p.parent.mkdir(parents=True, exist_ok=True)\n"
        "    p.write_text(content, encoding=encoding)\n",
    )


def wire_read_command() -> None:
    _replace(
        "src/colla/cli.py",
        "import argparse\n",
        "import argparse\n\nfrom colla.files import read_text\n",
    )
    _replace(
        "src/colla/cli.py",
        '    parser.add_argument("--version", action="version", version=f"colla {__version__}")\n',
        '    parser.add_argument("--version", action="version", version=f"colla {__version__}")\n'
        '    sub = parser.add_subparsers(dest="command")\n'
        "    read_p = sub.add_parser('read', help='Read a file')\n"
        "    read_p.add_argument('path')\n",
    )
    _replace(
        "src/colla/cli.py",
        "    parser.parse_args()\n",
        "    args = parser.parse_args()\n"
        "    if args.command == 'read':\n"
        "        print(read_text(args.path))\n",
    )


def wire_write_command() -> None:
    _replace(
        "src/colla/cli.py",
        "from colla.files import read_text\n",
        "from colla.files import read_text, write_text\n",
    )
    _replace(
        "src/colla/cli.py",
        "    read_p.add_argument('path')\n",
        "    read_p.add_argument('path')\n"
        "    write_p = sub.add_parser('write', help='Write a file')\n"
        "    write_p.add_argument('path')\n"
        "    write_p.add_argument('content')\n",
    )
    _replace(
        "src/colla/cli.py",
        "        print(read_text(args.path))\n",
        "        print(read_text(args.path))\n"
        "    elif args.command == 'write':\n"
        "        write_text(args.path, args.content)\n",
    )


def add_files_tests() -> None:
    _write(
        "tests/test_files.py",
        "from pathlib import Path\n\nfrom colla.files import read_text, write_text\n\n\n"
        "def test_write_and_read(tmp_path: Path):\n"
        "    target = tmp_path / 'sample.txt'\n"
        "    write_text(target, 'hello')\n"
        "    assert read_text(target) == 'hello'\n",
    )


def add_config_module() -> None:
    _write(
        "src/colla/config.py",
        '"""Config loading helpers."""\n\nimport json\nfrom pathlib import Path\n\n\n'
        "class ConfigError(Exception):\n"
        '    """Raised when config is invalid."""\n\n\n'
        "def load_json(path: str | Path) -> dict:\n"
        '    """Load a JSON config file."""\n'
        "    data = json.loads(Path(path).read_text(encoding='utf-8'))\n"
        "    if not isinstance(data, dict):\n"
        "        raise ConfigError('Root must be an object')\n"
        "    return data\n",
    )


def add_config_validate() -> None:
    _append(
        "src/colla/config.py",
        "\n\nREQUIRED_KEYS = ('name',)\n\n\n"
        "def validate_config(data: dict) -> None:\n"
        '    """Ensure required keys exist."""\n'
        "    missing = [k for k in REQUIRED_KEYS if k not in data]\n"
        "    if missing:\n"
        "        raise ConfigError(f'Missing keys: {missing}')\n",
    )


def wire_config_command() -> None:
    _replace(
        "src/colla/cli.py",
        "from colla.files import read_text, write_text\n",
        "from colla.config import load_json, validate_config\n"
        "from colla.files import read_text, write_text\n",
    )
    _replace(
        "src/colla/cli.py",
        "    write_p.add_argument('content')\n",
        "    write_p.add_argument('content')\n"
        "    cfg_p = sub.add_parser('config', help='Validate config file')\n"
        "    cfg_p.add_argument('path')\n",
    )
    _replace(
        "src/colla/cli.py",
        "        write_text(args.path, args.content)\n",
        "        write_text(args.path, args.content)\n"
        "    elif args.command == 'config':\n"
        "        data = load_json(args.path)\n"
        "        validate_config(data)\n"
        "        print('Config OK')\n",
    )


def add_yaml_support() -> None:
    _replace("pyproject.toml", 'dependencies = []', 'dependencies = ["PyYAML>=6.0"]')
    _append(
        "src/colla/config.py",
        "\n\nimport yaml\n\n\n"
        "def load_yaml(path: str | Path) -> dict:\n"
        '    """Load a YAML config file."""\n'
        "    data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))\n"
        "    if not isinstance(data, dict):\n"
        "        raise ConfigError('Root must be an object')\n"
        "    return data\n",
    )


def add_batch_module() -> None:
    _write(
        "src/colla/batch.py",
        '"""Batch file operations."""\n\nfrom pathlib import Path\n\n\n'
        "def rename_suffix(directory: str | Path, old: str, new: str, dry_run: bool = False) -> int:\n"
        '    """Rename files matching a suffix."""\n'
        "    count = 0\n"
        "    for path in Path(directory).iterdir():\n"
        "        if not path.is_file() or not path.name.endswith(old):\n"
        "            continue\n"
        "        target = path.with_name(path.name[: -len(old)] + new)\n"
        "        if not dry_run:\n"
        "            path.rename(target)\n"
        "        count += 1\n"
        "    return count\n",
    )


def wire_batch_command() -> None:
    _replace(
        "src/colla/cli.py",
        "from colla.config import load_json, validate_config\n",
        "from colla.batch import rename_suffix\n"
        "from colla.config import load_json, validate_config\n",
    )
    _replace(
        "src/colla/cli.py",
        "    cfg_p.add_argument('path')\n",
        "    cfg_p.add_argument('path')\n"
        "    batch_p = sub.add_parser('batch-rename', help='Batch rename by suffix')\n"
        "    batch_p.add_argument('directory')\n"
        "    batch_p.add_argument('old_suffix')\n"
        "    batch_p.add_argument('new_suffix')\n"
        "    batch_p.add_argument('--dry-run', action='store_true')\n",
    )
    _replace(
        "src/colla/cli.py",
        "        print('Config OK')\n",
        "        print('Config OK')\n"
        "    elif args.command == 'batch-rename':\n"
        "        n = rename_suffix(args.directory, args.old_suffix, args.new_suffix, args.dry_run)\n"
        "        print(f'Renamed {n} files')\n",
    )


def refactor_cli_parser() -> None:
    text = _read("src/colla/cli.py")
    if "def build_parser()" in text and "\ndef main()" in text:
        return

    imports = []
    for line in text.splitlines():
        if line.startswith("def "):
            break
        imports.append(line)
    while imports and imports[-1] == "":
        imports.pop()

    body = '''

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="colla", description="File and config helpers")
    parser.add_argument("--version", action="version", version=f"colla {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    sub = parser.add_subparsers(dest="command")
    read_p = sub.add_parser('read', help='Read a file')
    read_p.add_argument('path')
    write_p = sub.add_parser('write', help='Write a file')
    write_p.add_argument('path')
    write_p.add_argument('content')
    cfg_p = sub.add_parser('config', help='Validate config file')
    cfg_p.add_argument('path')
    batch_p = sub.add_parser('batch-rename', help='Batch rename by suffix')
    batch_p.add_argument('directory')
    batch_p.add_argument('old_suffix')
    batch_p.add_argument('new_suffix')
    batch_p.add_argument('--dry-run', action='store_true')
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == 'read':
        print(read_text(args.path))
    elif args.command == 'write':
        write_text(args.path, args.content)
    elif args.command == 'config':
        data = load_json(args.path)
        validate_config(data)
        print('Config OK')
    elif args.command == 'batch-rename':
        n = rename_suffix(args.directory, args.old_suffix, args.new_suffix, args.dry_run)
        print(f'Renamed {n} files')


if __name__ == "__main__":
    main()
'''
    _write("src/colla/cli.py", "\n".join(imports) + body)


def add_copy_helper() -> None:
    text = _read("src/colla/files.py")
    if "def copy_file(" in text:
        return
    _append(
        "src/colla/files.py",
        "\n\nimport shutil\n\n\n"
        "def copy_file(src: str | Path, dst: str | Path) -> None:\n"
        '    """Copy a file."""\n'
        "    shutil.copy2(src, dst)\n",
    )


def docs_config_example() -> None:
    _write(
        "docs/config-example.json",
        '{\n  "name": "demo",\n  "enabled": true\n}\n',
    )


def add_logging() -> None:
    _write(
        "src/colla/logutil.py",
        '"""Logging helpers."""\n\nimport logging\n\n\n'
        "def setup_logging(verbose: bool = False) -> None:\n"
        '    """Configure root logger."""\n'
        "    level = logging.DEBUG if verbose else logging.INFO\n"
        "    logging.basicConfig(level=level, format='%(levelname)s %(message)s')\n",
    )
    cli = _read("src/colla/cli.py")
    if "from colla.logutil import setup_logging" not in cli:
        _replace(
            "src/colla/cli.py",
            "import argparse\n",
            "import argparse\n\nfrom colla.logutil import setup_logging\n",
        )
    cli = _read("src/colla/cli.py")
    if "setup_logging(" not in cli:
        if "args = build_parser().parse_args()" in cli:
            _replace(
                "src/colla/cli.py",
                "    args = build_parser().parse_args()\n",
                "    args = build_parser().parse_args()\n"
                "    setup_logging(getattr(args, 'verbose', False))\n",
            )
        else:
            _replace(
                "src/colla/cli.py",
                "    args = parser.parse_args()\n",
                "    args = parser.parse_args()\n"
                "    setup_logging(getattr(args, 'verbose', False))\n",
            )


def bump_patch_version() -> None:
    _bump_version(patch=True)


def bump_minor_version() -> None:
    _bump_version(patch=False)


def fix_typo_readme() -> None:
    text = _read("README.md")
    if "config helpers" in text:
        _replace("README.md", "config helpers", "config utilities")
    elif "config utilities" in text:
        _replace("README.md", "config utilities", "config helpers")
    else:
        _append("README.md", "\n<!-- wording tweak -->\n")


def add_changelog_entry() -> None:
    if not (ROOT / "CHANGELOG.md").exists():
        _write("CHANGELOG.md", "# Changelog\n\n## Unreleased\n\n- Maintenance and docs updates.\n")
    else:
        _append("CHANGELOG.md", "\n- Minor maintenance update.\n")


def pin_python_version() -> None:
    text = _read("pyproject.toml")
    if 'requires-python = ">=3.9"' in text:
        return
    _replace("pyproject.toml", 'requires-python = ">=3.8"', 'requires-python = ">=3.9"')


ERA_TEMPLATES: dict[str, list[str]] = {
    "2018": [
        "init_readme",
        "add_usage_section",
        "add_cli_help_text",
        "add_dev_section",
        "bump_patch_version",
    ],
    "2019": [
        "add_files_module",
        "wire_read_command",
        "wire_write_command",
        "add_files_tests",
        "bump_minor_version",
    ],
    "2020": [
        "add_config_module",
        "add_config_validate",
        "wire_config_command",
        "add_yaml_support",
        "docs_config_example",
    ],
    "2021": [
        "add_batch_module",
        "wire_batch_command",
        "add_copy_helper",
        "refactor_cli_parser",
        "bump_patch_version",
    ],
    "2022": [
        "add_logging",
        "fix_typo_readme",
        "add_changelog_entry",
        "pin_python_version",
        "bump_minor_version",
    ],
}

FILLER_TEMPLATES: list[str] = [
    "bump_patch_version",
    "fix_typo_readme",
    "add_changelog_entry",
]

REGISTRY: dict[str, PatchFn] = {
    "init_readme": init_readme,
    "add_usage_section": add_usage_section,
    "add_dev_section": add_dev_section,
    "add_cli_help_text": add_cli_help_text,
    "add_files_module": add_files_module,
    "wire_read_command": wire_read_command,
    "wire_write_command": wire_write_command,
    "add_files_tests": add_files_tests,
    "add_config_module": add_config_module,
    "add_config_validate": add_config_validate,
    "wire_config_command": wire_config_command,
    "add_yaml_support": add_yaml_support,
    "add_batch_module": add_batch_module,
    "wire_batch_command": wire_batch_command,
    "add_logging": add_logging,
    "add_copy_helper": add_copy_helper,
    "docs_config_example": docs_config_example,
    "refactor_cli_parser": refactor_cli_parser,
    "bump_patch_version": bump_patch_version,
    "bump_minor_version": bump_minor_version,
    "fix_typo_readme": fix_typo_readme,
    "add_changelog_entry": add_changelog_entry,
    "pin_python_version": pin_python_version,
}


def template_message(name: str) -> str:
    messages = {
        "init_readme": "docs: expand README intro",
        "add_usage_section": "docs: add commands section",
        "add_dev_section": "docs: add development section",
        "add_cli_help_text": "feat: add verbose flag",
        "add_files_module": "feat: add file helpers module",
        "wire_read_command": "feat: add read subcommand",
        "wire_write_command": "feat: add write subcommand",
        "add_files_tests": "test: cover file helpers",
        "add_config_module": "feat: add config loader",
        "add_config_validate": "feat: validate config keys",
        "wire_config_command": "feat: add config subcommand",
        "add_yaml_support": "feat: add YAML config support",
        "add_batch_module": "feat: add batch rename helper",
        "wire_batch_command": "feat: add batch-rename command",
        "add_logging": "feat: add logging setup",
        "add_copy_helper": "feat: add copy_file helper",
        "docs_config_example": "docs: add config example",
        "refactor_cli_parser": "refactor: extract build_parser",
        "bump_patch_version": "chore: bump patch version",
        "bump_minor_version": "chore: bump minor version",
        "fix_typo_readme": "docs: fix README wording",
        "add_changelog_entry": "docs: add changelog",
        "pin_python_version": "chore: require Python 3.9+",
    }
    return messages.get(name, f"chore: apply {name}")


def pick_template(year: str, index: int) -> str:
    pool = ERA_TEMPLATES.get(year, FILLER_TEMPLATES)
    if index < len(pool):
        return pool[index]
    return FILLER_TEMPLATES[(index - len(pool)) % len(FILLER_TEMPLATES)]


def apply_template(name: str) -> None:
    fn = REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"Unknown template: {name}")
    fn()
