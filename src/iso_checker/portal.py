from __future__ import annotations

import html
import json
from dataclasses import dataclass
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from iso_checker.app_services import AppServices, User
from iso_checker.auth import issue_session_cookie, parse_session_cookie
from iso_checker.reference_client import run_reference_scenario, scenario_reference_payloads_for_display


@dataclass(frozen=True)
class PortalConfig:
    simulator_host: str
    simulator_port: int
    scenario_file: Path
    portal_admin_enabled: bool = True
    single_tenant: bool = False


def create_portal_server(host: str, port: int, services: AppServices, session_secret: str, config: PortalConfig) -> ThreadingHTTPServer:
    handler = _make_handler(services, session_secret, config)
    return ThreadingHTTPServer((host, port), handler)


def _make_handler(services: AppServices, session_secret: str, config: PortalConfig):
    class PortalHandler(BaseHTTPRequestHandler):
        server_version = "IsoCheckerPortal/0.1"

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            user = self._current_user()
            if path == "/":
                if user:
                    self._redirect("/status")
                else:
                    self._redirect("/login")
                return
            if path == "/login" and method == "GET":
                return self._login_page()
            if path == "/login" and method == "POST":
                return self._login_submit()
            if path == "/logout":
                return self._logout(user)
            if not user:
                self._redirect("/login")
                return
            if path == "/status":
                return self._status_page(user)
            if path == "/companies" and method == "GET":
                if not config.portal_admin_enabled:
                    return self.send_error(404)
                return self._companies_page(user)
            if path == "/companies" and method == "POST":
                if not config.portal_admin_enabled:
                    return self.send_error(404)
                return self._companies_create(user)
            if path == "/users" and method == "GET":
                if not config.portal_admin_enabled:
                    return self.send_error(404)
                return self._users_page(user)
            if path == "/users" and method == "POST":
                if not config.portal_admin_enabled:
                    return self.send_error(404)
                return self._users_create(user)
            if path == "/plan" and method == "GET":
                return self._plan_page(user)
            if path == "/plan" and method == "POST":
                return self._plan_save(user)
            if path == "/tcp-scenario" and method == "POST":
                return self._tcp_scenario_save(user)
            if path == "/scenarios":
                return self._scenarios_page(user)
            if path == "/runs":
                return self._runs_page(user)
            if path.startswith("/runs/"):
                try:
                    run_id = int(path.split("/")[-1])
                except ValueError:
                    self.send_error(404)
                    return
                return self._run_detail_page(user, run_id)
            if path == "/tests" and method == "GET":
                return self._tests_page(user)
            if path == "/tests/run" and method == "POST":
                return self._tests_run(user)
            self.send_error(404)

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            parsed = parse_qs(body, keep_blank_values=True)
            return {key: values[0] for key, values in parsed.items()}

        def _read_form_multi(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            return {key: values for key, values in parse_qs(body, keep_blank_values=True).items()}

        def _current_user(self) -> User | None:
            header = self.headers.get("Cookie")
            if not header:
                return None
            jar = cookies.SimpleCookie()
            jar.load(header)
            morsel = jar.get("iso_checker_session")
            if not morsel:
                return None
            payload = parse_session_cookie(morsel.value, session_secret)
            if not payload:
                return None
            user_id = int(payload.get("user_id", 0))
            user = services.get_user(user_id)
            if not user or not user.active:
                return None
            return user

        def _set_session_cookie(self, user: User) -> None:
            token = issue_session_cookie(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "company_id": user.company_id,
                },
                session_secret,
            )
            self.send_header("Set-Cookie", f"iso_checker_session={token}; HttpOnly; Path=/; SameSite=Lax")

        def _clear_session_cookie(self) -> None:
            self.send_header("Set-Cookie", "iso_checker_session=deleted; Max-Age=0; Path=/; SameSite=Lax")

        def _redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def _send_html(self, body: str, *, status: int = 200) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _layout(self, title: str, body: str, user: User | None = None) -> str:
            nav = ""
            if user:
                links = [
                    '<a href="/status">Status</a>',
                    '<a href="/plan">Plan</a>',
                    '<a href="/scenarios">Scenarios</a>',
                    '<a href="/runs">Runs</a>',
                    '<a href="/tests">Tests</a>',
                ]
                if config.portal_admin_enabled and user.role == "admin":
                    links.extend(
                        [
                            '<a href="/companies">Companies</a>',
                            '<a href="/users">Users</a>',
                        ]
                    )
                links.append('<a href="/logout">Logout</a>')
                nav = f"""
                <nav>
                  <span>Signed in as <strong>{html.escape(user.username)}</strong></span>
                  {' '.join(links)}
                </nav>
                """
            return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Georgia, serif; margin: 0; background: #f6f4ef; color: #1f2328; }}
    header {{ background: linear-gradient(135deg, #e5d9be, #f4efe2); padding: 24px; border-bottom: 1px solid #cfbf9a; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    nav {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
    nav a {{ color: #6a2c00; text-decoration: none; }}
    h1, h2 {{ margin-top: 0; }}
    .panel {{ background: #fffdf8; border: 1px solid #d7ccb4; padding: 16px; margin-bottom: 16px; border-radius: 10px; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e3dac5; text-align: left; padding: 8px; vertical-align: top; }}
    form {{ display: grid; gap: 10px; }}
    input, select, button, textarea {{ font: inherit; padding: 8px; }}
    button {{ background: #6a2c00; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f2ede2; padding: 12px; border-radius: 8px; }}
    .muted {{ color: #6a6f76; }}
  </style>
</head>
<body>
  <header>
    <h1>ISO Checker Portal</h1>
    {nav}
  </header>
  <main>{body}</main>
</body>
</html>"""

        def _require_admin(self, user: User) -> bool:
            if user.role == "admin":
                return True
            self._send_html(self._layout("Forbidden", "<div class='panel'><h2>Forbidden</h2><p>Admin access required.</p></div>", user), status=403)
            return False

        def _login_page(self, error: str | None = None) -> None:
            error_html = f"<p style='color:#a40000'>{html.escape(error)}</p>" if error else ""
            body = f"""
            <div class="panel" style="max-width:420px;margin:40px auto;">
              <h2>Login</h2>
              {error_html}
              <form method="post" action="/login">
                <label>Username <input name="username" required></label>
                <label>Password <input type="password" name="password" required></label>
                <button type="submit">Sign in</button>
              </form>
            </div>
            """
            self._send_html(self._layout("Login", body))

        def _login_submit(self) -> None:
            form = self._read_form()
            user = services.authenticate(form.get("username", ""), form.get("password", ""))
            if not user:
                self._login_page("Invalid credentials.")
                return
            services.audit("login", user_id=user.id, company_id=user.company_id, details={"username": user.username})
            self.send_response(303)
            self._set_session_cookie(user)
            self.send_header("Location", "/status")
            self.end_headers()

        def _logout(self, user: User | None) -> None:
            if user:
                services.audit("logout", user_id=user.id, company_id=user.company_id, details={"username": user.username})
            self.send_response(303)
            self._clear_session_cookie()
            self.send_header("Location", "/login")
            self.end_headers()

        def _scenario_select_options(self, scenarios: list[dict[str, Any]], selected: str) -> str:
            return "".join(
                f'<option value="{html.escape(s["name"])}"'
                f'{" selected" if s["name"] == selected else ""}>'
                f"{html.escape(s['name'])}</option>"
                for s in scenarios
            )

        def _status_page(self, user: User) -> None:
            runs = services.list_runs(user)
            companies = services.list_companies()
            scenarios = services.list_scenarios()
            st_note = (
                "<p class='muted'>Simulator uses <strong>single-tenant</strong> TCP resolution (no DE32/41/42 match).</p>"
                if config.single_tenant
                else "<p class='muted'>External clients must send DE32/41/42 matching the company record unless single-tenant mode is enabled.</p>"
            )
            tcp_panel = ""
            if user.role == "admin" and companies:
                co0 = companies[0]
                scen_opts = self._scenario_select_options(scenarios, co0.scenario_name)
                company_opts = "".join(
                    f'<option value="{c.id}">{html.escape(c.name)}</option>' for c in companies
                )
                tcp_panel = f"""
              <section class="panel">
                <h2>TCP default scenario</h2>
                <p class="muted">YAML scenario used for the selected company on each new external TCP session (when the process has no global <code>--scenario-name</code>). Pick company and scenario, then save.</p>
                <form method="post" action="/tcp-scenario">
                  <label>Company <select name="company_id">{company_opts}</select></label>
                  <label>Scenario <select name="scenario_name">{scen_opts}</select></label>
                  <button type="submit">Save</button>
                </form>
              </section>"""
            elif user.company_id:
                co = services.get_company(user.company_id)
                if co:
                    scen_opts = self._scenario_select_options(scenarios, co.scenario_name)
                    tcp_panel = f"""
              <section class="panel">
                <h2>TCP default scenario</h2>
                <p class="muted">Company <strong>{html.escape(co.name)}</strong> — used for new Host2Host sessions from your systems.</p>
                <form method="post" action="/tcp-scenario">
                  <input type="hidden" name="company_id" value="{co.id}">
                  <label>Scenario <select name="scenario_name">{scen_opts}</select></label>
                  <button type="submit">Save</button>
                </form>
              </section>"""
            body = f"""
            <div class="grid">
              <section class="panel">
                <h2>Runtime</h2>
                <p>Simulator listener: <strong>{html.escape(config.simulator_host)}:{config.simulator_port}</strong></p>
                <p>Scenario file: <code>{html.escape(str(config.scenario_file))}</code></p>
                <p>Tracked scenarios: <strong>{len(scenarios)}</strong></p>
                <p>Recent audits: <strong>{services.count_recent_audits()}</strong></p>
                {st_note}
              </section>
              <section class="panel">
                <h2>Tenancy</h2>
                <p>Companies: <strong>{len(companies)}</strong></p>
                <p>Your role: <strong>{html.escape(user.role)}</strong></p>
                <p>Your company id: <strong>{html.escape(str(user.company_id or "-"))}</strong></p>
              </section>
              <section class="panel">
                <h2>Recent activity</h2>
                <p>Visible runs: <strong>{len(runs)}</strong></p>
                <p class="muted">Use the Runs page for message timelines and validation details.</p>
              </section>
              {tcp_panel}
            </div>
            """
            self._send_html(self._layout("Status", body, user))

        def _companies_page(self, user: User) -> None:
            if not self._require_admin(user):
                return
            rows = []
            for company in services.list_companies():
                rows.append(
                    f"<tr><td>{company.id}</td><td>{html.escape(company.name)}</td><td>{html.escape(company.slug)}</td>"
                    f"<td>{html.escape(company.scenario_name)}</td><td>{html.escape(', '.join(company.assigned_scenarios))}</td>"
                    f"<td>{html.escape(company.expected_de32 or '')}</td>"
                    f"<td>{html.escape(company.expected_de41 or '')}</td><td>{html.escape(company.expected_de42 or '')}</td></tr>"
                )
            scenario_options = "".join(
                f'<option value="{html.escape(item["name"])}">{html.escape(item["name"])}</option>'
                for item in services.list_scenarios()
            )
            scenario_checks = "".join(
                f"<label><input type='checkbox' name='scenario_names' value='{html.escape(item['name'])}'> {html.escape(item['name'])}</label>"
                for item in services.list_scenarios()
            )
            body = f"""
            <div class="grid">
              <section class="panel">
                <h2>Create company</h2>
                <form method="post" action="/companies">
                  <label>Name <input name="name" required></label>
                  <label>Slug <input name="slug" required></label>
                  <label>Default scenario <select name="scenario_name">{scenario_options}</select></label>
                  <fieldset>
                    <legend>Assigned scenarios</legend>
                    {scenario_checks}
                  </fieldset>
                  <label>Expected DE32 <input name="expected_de32"></label>
                  <label>Expected DE41 <input name="expected_de41"></label>
                  <label>Expected DE42 <input name="expected_de42"></label>
                  <button type="submit">Create company</button>
                </form>
              </section>
              <section class="panel">
                <h2>Companies</h2>
                <table>
                  <tr><th>ID</th><th>Name</th><th>Slug</th><th>Default</th><th>Assigned</th><th>DE32</th><th>DE41</th><th>DE42</th></tr>
                  {''.join(rows)}
                </table>
              </section>
            </div>
            """
            self._send_html(self._layout("Companies", body, user))

        def _companies_create(self, user: User) -> None:
            if not self._require_admin(user):
                return
            form_multi = self._read_form_multi()
            form = {key: values[0] for key, values in form_multi.items() if values}
            services.create_company(
                name=form.get("name", "").strip(),
                slug=form.get("slug", "").strip(),
                scenario_name=form.get("scenario_name", "").strip(),
                scenario_names=[item.strip() for item in form_multi.get("scenario_names", []) if item.strip()],
                expected_de32=form.get("expected_de32", "").strip() or None,
                expected_de41=form.get("expected_de41", "").strip() or None,
                expected_de42=form.get("expected_de42", "").strip() or None,
            )
            services.audit("company_created", user_id=user.id, details={"slug": form.get("slug", "")})
            self._redirect("/companies")

        def _users_page(self, user: User) -> None:
            if not self._require_admin(user):
                return
            users = services.list_users()
            company_options = ['<option value="">No company (admin)</option>']
            for company in services.list_companies():
                company_options.append(f'<option value="{company.id}">{html.escape(company.name)}</option>')
            rows = []
            for item in users:
                rows.append(
                    f"<tr><td>{item['id']}</td><td>{html.escape(str(item['username']))}</td><td>{html.escape(str(item['role']))}</td>"
                    f"<td>{html.escape(str(item.get('company_name') or '-'))}</td></tr>"
                )
            body = f"""
            <div class="grid">
              <section class="panel">
                <h2>Create user</h2>
                <form method="post" action="/users">
                  <label>Username <input name="username" required></label>
                  <label>Password <input type="password" name="password" required></label>
                  <label>Role
                    <select name="role">
                      <option value="partner_user">partner_user</option>
                      <option value="admin">admin</option>
                    </select>
                  </label>
                  <label>Company <select name="company_id">{''.join(company_options)}</select></label>
                  <button type="submit">Create user</button>
                </form>
              </section>
              <section class="panel">
                <h2>Users</h2>
                <table>
                  <tr><th>ID</th><th>Username</th><th>Role</th><th>Company</th></tr>
                  {''.join(rows)}
                </table>
              </section>
            </div>
            """
            self._send_html(self._layout("Users", body, user))

        def _users_create(self, user: User) -> None:
            if not self._require_admin(user):
                return
            form = self._read_form()
            company_id_raw = form.get("company_id", "").strip()
            company_id = int(company_id_raw) if company_id_raw else None
            services.create_user(
                username=form.get("username", "").strip(),
                password=form.get("password", ""),
                role=form.get("role", "partner_user").strip(),
                company_id=company_id,
            )
            services.audit("user_created", user_id=user.id, company_id=company_id, details={"username": form.get("username", "")})
            self._redirect("/users")

        def _scenarios_page(self, user: User) -> None:
            rows = []
            for item in services.list_scenarios():
                rc = "yes" if item.get("reference_client_ready") else "no"
                rows.append(
                    f"<tr><td>{html.escape(item['name'])}</td><td>{html.escape(item['filename'])}</td>"
                    f"<td>{html.escape(item['description'])}</td><td>{rc}</td></tr>"
                )
            body = f"""
            <div class="panel">
              <h2>Scenario catalog</h2>
              <p class="muted">Reference client = all steps define <code>reference_request</code> (portal Tests / <code>client_run_scenario.py</code>).</p>
              <table>
                <tr><th>Name</th><th>Filename</th><th>Description</th><th>Ref. client</th></tr>
                {''.join(rows)}
              </table>
            </div>
            """
            self._send_html(self._layout("Scenarios", body, user))

        def _runs_page(self, user: User) -> None:
            rows = []
            for run in services.list_runs(user):
                rows.append(
                    f"<tr><td><a href='/runs/{run['id']}'>{run['id']}</a></td><td>{html.escape(str(run['company_name']))}</td>"
                    f"<td>{html.escape(str(run['scenario_name']))}</td><td>{html.escape(str(run['status']))}</td>"
                    f"<td>{html.escape(str(run['started_at']))}</td><td>{html.escape(str(run.get('summary') or ''))}</td></tr>"
                )
            body = f"""
            <div class="panel">
              <h2>Scenario runs</h2>
              <table>
                <tr><th>ID</th><th>Company</th><th>Scenario</th><th>Status</th><th>Started</th><th>Summary</th></tr>
                {''.join(rows)}
              </table>
            </div>
            """
            self._send_html(self._layout("Runs", body, user))

        def _run_detail_page(self, user: User, run_id: int) -> None:
            run = services.get_run(run_id, user)
            if not run:
                self.send_error(404)
                return
            rows = []
            for event in services.list_messages_for_run(run_id, user):
                payload = html.escape(json.dumps(json.loads(event["payload_json"]), indent=2, ensure_ascii=False))
                rows.append(
                    f"<tr><td>{event['seq']}</td><td>{html.escape(str(event['direction']))}</td><td>{html.escape(str(event['mti'] or ''))}</td>"
                    f"<td>{html.escape(str(event['validation_status'] or ''))}</td><td>{html.escape(str(event['error_code'] or ''))}</td>"
                    f"<td><details><summary>Payload</summary><pre>{payload}</pre></details></td></tr>"
                )
            body = f"""
            <div class="panel">
              <h2>Run #{run['id']}</h2>
              <p>Company: <strong>{html.escape(str(run['company_name']))}</strong></p>
              <p>Scenario: <strong>{html.escape(str(run['scenario_name']))}</strong></p>
              <p>Status: <strong>{html.escape(str(run['status']))}</strong></p>
              <p>Client: <code>{html.escape(str(run.get('client_addr') or ''))}</code></p>
              <p>Summary: {html.escape(str(run.get('summary') or ''))}</p>
            </div>
            <div class="panel">
              <h2>Messages</h2>
              <table>
                <tr><th>Seq</th><th>Direction</th><th>MTI</th><th>Validation</th><th>Error</th><th>Payload</th></tr>
                {''.join(rows)}
              </table>
            </div>
            """
            self._send_html(self._layout(f"Run {run_id}", body, user))

        def _tests_page(self, user: User, result: str | None = None) -> None:
            all_sc = services.list_scenarios()
            plan = services.get_user_selected_scenarios(user.id)
            runnable_all = [s for s in all_sc if s.get("reference_client_ready")]
            if plan:
                runnable = [s for s in runnable_all if s["name"] in set(plan)]
            else:
                runnable = runnable_all
            options = "".join(
                f'<option value="{html.escape(item["name"])}">{html.escape(item["name"])}</option>'
                for item in runnable
            )
            if not options:
                options = '<option value="">(no reference-ready scenarios; check Plan or Scenarios)</option>'
            plan_note = (
                f"<p class='muted'>Your plan lists {len(plan)} scenario(s); showing {len(runnable)} reference-ready match(es). "
                "Empty plan = all reference-ready scenarios.</p>"
                if plan
                else "<p class='muted'>Empty plan: all reference-ready scenarios are listed. Set a plan on the Plan page to focus the list.</p>"
            )
            result_panel = ""
            if result is not None:
                result_panel = f"<div class='panel'><h2>Last launch output</h2><pre>{html.escape(result)}</pre></div>"
            body = f"""
            <div class="grid">
              <section class="panel">
                <h2>Launch reference client</h2>
                {plan_note}
                <form method="post" action="/tests/run">
                  <label>Scenario
                    <select name="scenario">{options}</select>
                  </label>
                  <label>Host <input name="host" value="{html.escape(config.simulator_host)}"></label>
                  <label>Port <input name="port" value="{config.simulator_port}"></label>
                  <button type="submit">Run test</button>
                </form>
                <p class="muted">Runs on the portal host against your YAML <code>reference_request</code> templates (STAN and company DE32/41/42 applied automatically).</p>
              </section>
              {result_panel}
            </div>
            """
            self._send_html(self._layout("Tests", body, user))

        def _tests_run(self, user: User) -> None:
            form = self._read_form()
            scenario = form.get("scenario", "").strip()
            host = form.get("host", config.simulator_host) or config.simulator_host
            port_raw = form.get("port", str(config.simulator_port))
            try:
                port = int(port_raw)
            except ValueError:
                port = config.simulator_port
            company = services.get_company(user.company_id) if user.company_id else None
            lines: list[str] = []
            if scenario:
                try:
                    preview = scenario_reference_payloads_for_display(config.scenario_file, scenario)
                    lines.append("Reference templates from YAML (before STAN / company field overlay):")
                    lines.append(json.dumps(preview, indent=2, ensure_ascii=False))
                    lines.append("")
                except Exception as exc:
                    lines.append(f"(Could not load scenario preview: {exc})")
                    lines.append("")
                result = run_reference_scenario(
                    host,
                    port,
                    config.scenario_file,
                    scenario,
                    company=company,
                )
                lines.extend(result.lines)
                if result.error:
                    lines.append(f"Failed: {result.error}")
            else:
                lines.append("No scenario selected.")
            output = "\n".join(lines)
            services.audit(
                "test_launched",
                user_id=user.id,
                company_id=user.company_id,
                details={"scenario": scenario, "host": host, "port": port},
            )
            self._tests_page(user, output)

        def _plan_page(self, user: User) -> None:
            all_s = services.list_scenarios()
            picked = set(services.get_user_selected_scenarios(user.id))
            checks = []
            for s in all_s:
                sel = " checked" if s["name"] in picked else ""
                tag = " ✓ ref.client" if s.get("reference_client_ready") else ""
                checks.append(
                    f"<label><input type='checkbox' name='scenario_names' value='{html.escape(s['name'])}'{sel}>"
                    f" {html.escape(s['name'])}{tag}</label>"
                )
            body = f"""
            <div class="panel">
              <h2>Test plan</h2>
              <p class="muted">Pick scenarios you want to focus on. The Tests page only lists reference-client-ready scenarios that appear here; if you select nothing, Tests shows every reference-ready scenario.</p>
              <form method="post" action="/plan">
                <fieldset><legend>Scenarios</legend>{"".join(checks)}</fieldset>
                <button type="submit">Save plan</button>
              </form>
            </div>
            """
            self._send_html(self._layout("Plan", body, user))

        def _plan_save(self, user: User) -> None:
            form_multi = self._read_form_multi()
            names = [item.strip() for item in form_multi.get("scenario_names", []) if item.strip()]
            services.set_user_selected_scenarios(user.id, names)
            services.audit("plan_updated", user_id=user.id, company_id=user.company_id, details={"scenarios": names})
            self._redirect("/plan")

        def _tcp_scenario_save(self, user: User) -> None:
            form = self._read_form()
            name = form.get("scenario_name", "").strip()
            if not name:
                self._redirect("/status")
                return
            try:
                if user.role == "admin":
                    cid = int(form.get("company_id", "0"))
                    services.set_company_default_scenario(cid, name)
                    services.audit(
                        "tcp_default_scenario",
                        user_id=user.id,
                        company_id=cid,
                        details={"scenario_name": name},
                    )
                elif user.company_id:
                    raw_cid = form.get("company_id", "").strip()
                    if raw_cid and int(raw_cid) != user.company_id:
                        self._send_html(
                            self._layout(
                                "Forbidden",
                                "<div class='panel'><h2>Forbidden</h2><p>Invalid company.</p></div>",
                                user,
                            ),
                            status=403,
                        )
                        return
                    services.set_company_default_scenario(user.company_id, name)
                    services.audit(
                        "tcp_default_scenario",
                        user_id=user.id,
                        company_id=user.company_id,
                        details={"scenario_name": name},
                    )
                else:
                    self._send_html(
                        self._layout(
                            "Forbidden",
                            "<div class='panel'><h2>Forbidden</h2><p>No company to update.</p></div>",
                            user,
                        ),
                        status=403,
                    )
                    return
            except Exception as exc:
                self._send_html(
                    self._layout("Error", f"<div class='panel'><p>{html.escape(str(exc))}</p></div>", user),
                    status=400,
                )
                return
            self._redirect("/status")

    return PortalHandler
