from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from iso_checker.config import Settings, load_settings
from iso_checker.logging_report import configure_logging
from iso_checker.scenario_engine import load_scenario_file
from iso_checker.server import serve


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="iso-checker", description="SVFE Host2Host partner simulator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="Listen for TCP Host2Host connections")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument(
        "--scenario-file",
        type=Path,
        default=Path("scenarios/default.yaml"),
        help="Scenario YAML path (default: scenarios/default.yaml)",
    )
    p_serve.add_argument("--scenario-name", default=None)
    p_serve.add_argument("--log-level", default="INFO")
    p_serve.add_argument("--report", type=Path, default=None, help="Append JSON Lines events to this file")
    p_serve.add_argument("--json", action="store_true", help="Structured JSON logs on stderr")

    p_val = sub.add_parser("validate-scenarios", help="Load and validate scenario YAML")
    p_val.add_argument("scenario_file", type=Path)
    p_val.add_argument("--scenario-name", default=None)

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        settings = load_settings(
            host=args.host,
            port=args.port,
            scenario_file=args.scenario_file,
            scenario_name=args.scenario_name,
            log_level=args.log_level,
            report_path=args.report,
            json_stdout=args.json,
        )
        configure_logging(settings.log_level, settings.json_stdout)
        try:
            asyncio.run(
                serve(
                    settings.host,
                    settings.port,
                    settings.scenario_file,
                    settings.scenario_name,
                    settings.report_path,
                )
            )
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "validate-scenarios":
        load_scenario_file(args.scenario_file, args.scenario_name)
        print(f"OK: {args.scenario_file}", file=sys.stdout)
        return


if __name__ == "__main__":
    main()
