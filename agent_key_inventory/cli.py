"""agent-key-inventory: what can this agent session reach, and what did it use?

  scan   list the credentials an agent run inherits (names and locations, never values)
  diff   compare a scan with a usage log; granted-but-unused authority is the finding

Exit codes: 0 ok, 1 unused grants over --max-unused (diff only), 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_key_inventory.scan import parse_env_file, parse_env_names, scan


def cmd_scan(args: argparse.Namespace) -> int:
    if args.env_names:
        env = parse_env_names(Path(args.env_names))
    elif args.env_file:
        env = parse_env_file(Path(args.env_file))
    else:
        env = dict(os.environ)
    grants = scan(Path(args.home).expanduser(), env, Path(args.cwd) if args.cwd else None)
    if args.json:
        print(json.dumps({"grants": grants}, indent=2))
    else:
        print(f"{len(grants)} grant(s) an agent run here would inherit")
        for g in grants:
            print(f"  {g['kind']:<24} {g['grant_id']:<48} {g['source']}")
    return 0


def load_usage(path: Path) -> dict[str, int]:
    """JSONL, one object per use: {"grant": "<grant_id>", ...}. Returns uses per grant."""
    uses: dict[str, int] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            grant = json.loads(line)["grant"]
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"{path}:{n}: expected a JSON object with a 'grant' field")
        uses[grant] = uses.get(grant, 0) + 1
    return uses


def cmd_diff(args: argparse.Namespace) -> int:
    grants = json.loads(Path(args.inventory).read_text(encoding="utf-8"))["grants"]
    uses = load_usage(Path(args.usage))
    granted = {g["grant_id"]: g for g in grants}
    used = sorted(g for g in granted if uses.get(g))
    unused = sorted(g for g in granted if not uses.get(g))
    unknown = sorted(u for u in uses if u not in granted)
    report = {"granted": len(granted), "used": used, "unused": unused, "used_but_not_in_inventory": unknown}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"granted {len(granted)}, used {len(used)}, unused {len(unused)}")
        for g in unused:
            print(f"  unused  {granted[g]['kind']:<24} {g}")
        for g in unknown:
            print(f"  used but not in inventory  {g}")
    return 1 if len(unused) > args.max_unused else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent-key-inventory", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="list inherited credentials by name and location")
    s.add_argument("--home", default="~", help="home directory to scan (default: ~)")
    s.add_argument("--cwd", help="project directory to check for .mcp.json")
    s.add_argument("--env-file", help="read the environment from a KEY=VALUE file instead of this process")
    s.add_argument("--env-names", help="read variable names only, one per line, instead of this process")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)
    d = sub.add_parser("diff", help="compare a scan with a usage log")
    d.add_argument("inventory", help="JSON written by `scan --json`")
    d.add_argument("usage", help="JSONL usage log, one {\"grant\": id} per use")
    d.add_argument("--max-unused", type=int, default=0, help="exit 1 when more grants than this went unused")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_diff)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"agent-key-inventory: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
