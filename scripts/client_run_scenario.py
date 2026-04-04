#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from iso_checker.reference_client import run_reference_scenario  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ISO checker scenarios as a TCP client (from YAML reference_request).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8583)
    parser.add_argument("--scenario-file", type=Path, default=Path("scenarios"), help="Scenario directory or YAML file")
    parser.add_argument("--scenario", required=True, help="Scenario name (must define reference_request on every step)")
    args = parser.parse_args()
    path = args.scenario_file
    if not path.exists():
        print(f"Scenario path not found: {path}", file=sys.stderr)
        return 2
    result = run_reference_scenario(
        args.host,
        args.port,
        path,
        args.scenario,
        company=None,
    )
    for line in result.lines:
        print(line)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
