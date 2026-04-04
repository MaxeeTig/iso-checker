from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from pathlib import Path

from iso_checker.app_services import AppServices
from iso_checker.config import Settings, load_settings
from iso_checker.logging_report import configure_logging
from iso_checker.portal import PortalConfig, create_portal_server
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
        default=Path("scenarios"),
        help="Scenario YAML file or directory (default: scenarios)",
    )
    p_serve.add_argument("--scenario-name", default=None)
    p_serve.add_argument("--log-level", default="INFO")
    p_serve.add_argument("--report", type=Path, default=None, help="Append JSON Lines events to this file")
    p_serve.add_argument("--json", action="store_true", help="Structured JSON logs on stderr")

    p_app = sub.add_parser("serve-app", help="Run TCP simulator and partner portal together")
    p_app.add_argument("--host", default=None)
    p_app.add_argument("--port", type=int, default=None)
    p_app.add_argument("--http-host", default=None)
    p_app.add_argument("--http-port", type=int, default=None)
    p_app.add_argument(
        "--scenario-file",
        type=Path,
        default=Path("scenarios"),
        help="Scenario YAML file or directory (default: scenarios)",
    )
    p_app.add_argument("--scenario-name", default=None)
    p_app.add_argument("--db-path", type=Path, default=None)
    p_app.add_argument("--session-secret", default=None)
    p_app.add_argument("--log-level", default="INFO")
    p_app.add_argument("--report", type=Path, default=None, help="Append JSON Lines events to this file")
    p_app.add_argument("--json", action="store_true", help="Structured JSON logs on stderr")
    p_app.add_argument("--admin-username", default="admin")
    p_app.add_argument("--admin-password", default="admin")

    p_init = sub.add_parser("init-db", help="Initialize SQLite schema and bootstrap an admin user")
    p_init.add_argument("--db-path", type=Path, default=Path("var/iso_checker.sqlite3"))
    p_init.add_argument(
        "--scenario-file",
        type=Path,
        default=Path("scenarios"),
        help="Scenario YAML file or directory (default: scenarios)",
    )
    p_init.add_argument("--admin-username", default="admin")
    p_init.add_argument("--admin-password", default="admin")

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

    if args.cmd == "serve-app":
        settings = load_settings(
            host=args.host,
            port=args.port,
            http_host=args.http_host,
            http_port=args.http_port,
            scenario_file=args.scenario_file,
            scenario_name=args.scenario_name,
            db_path=args.db_path,
            session_secret=args.session_secret,
            log_level=args.log_level,
            report_path=args.report,
            json_stdout=args.json,
        )
        configure_logging(settings.log_level, settings.json_stdout)
        services = AppServices(settings.db_path, settings.scenario_file)
        services.init_schema()
        services.bootstrap_defaults(admin_username=args.admin_username, admin_password=args.admin_password)
        portal = create_portal_server(
            settings.http_host,
            settings.http_port,
            services,
            settings.session_secret,
            PortalConfig(
                simulator_host=settings.host,
                simulator_port=settings.port,
                scenario_file=settings.scenario_file,
            ),
        )
        thread = threading.Thread(target=portal.serve_forever, name="iso-checker-portal", daemon=True)
        thread.start()
        print(
            f"Portal listening on http://{settings.http_host}:{settings.http_port} "
            f"(bootstrap admin: {args.admin_username}/{args.admin_password})",
            file=sys.stderr,
        )
        try:
            asyncio.run(
                serve(
                    settings.host,
                    settings.port,
                    settings.scenario_file,
                    settings.scenario_name,
                    settings.report_path,
                    services,
                )
            )
        except KeyboardInterrupt:
            pass
        finally:
            portal.shutdown()
            portal.server_close()
            thread.join(timeout=2.0)
        return

    if args.cmd == "init-db":
        services = AppServices(args.db_path, args.scenario_file)
        services.init_schema()
        services.bootstrap_defaults(admin_username=args.admin_username, admin_password=args.admin_password)
        print(f"OK: initialized {args.db_path}", file=sys.stdout)
        return

    if args.cmd == "validate-scenarios":
        load_scenario_file(args.scenario_file, args.scenario_name)
        print(f"OK: {args.scenario_file}", file=sys.stdout)
        return


if __name__ == "__main__":
    main()
