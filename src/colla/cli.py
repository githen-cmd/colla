"""CLI entry point."""

import argparse

from colla import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="colla", description="File and config helpers")
    parser.add_argument("--version", action="version", version=f"colla {__version__}")
    parser.parse_args()


if __name__ == "__main__":
    main()
