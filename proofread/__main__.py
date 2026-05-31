"""CLI entrypoint: `proofread <input.xml> --lang en`."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import load_config
from .runner import run


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="proofread",
        description=(
            "Proofread <p> elements in an XML file using a GenAI model. "
            "Errors are wrapped in <error type=... correction=... reason=...> "
            "tags while preserving the exact original text length."
        ),
    )
    parser.add_argument("input", type=Path, help="Path to the input XML file.")
    parser.add_argument(
        "--lang",
        required=True,
        help="BCP-47 language tag (e.g. en, fr, de). Determines proofing conventions.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stderr,
    )
    try:
        config = load_config()
        asyncio.run(run(args.input, args.lang, config))
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
