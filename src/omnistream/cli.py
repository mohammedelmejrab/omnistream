import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omni")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "replay", "serve"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    print(f"omni {args.command}: not implemented yet", file=sys.stderr)
    return 1
