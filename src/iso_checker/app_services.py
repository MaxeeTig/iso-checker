from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iso_checker.auth import hash_password, verify_password
from iso_checker.logging_report import mask_pan
from iso_checker.scenario_engine import list_scenarios, load_scenario_file, scenario_supports_reference_client


@dataclass(frozen=True)
class Company:
    id: int
    name: str
    slug: str
    scenario_name: str
    assigned_scenarios: tuple[str, ...]
    expected_de32: str | None
    expected_de41: str | None
    expected_de42: str | None
    active: bool


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    company_id: int | None
    active: bool


class AppServices:
    def __init__(self, db_path: Path, scenario_file: Path) -> None:
        self.db_path = Path(db_path)
        self.scenario_file = Path(scenario_file)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    scenario_name TEXT NOT NULL,
                    expected_de32 TEXT,
                    expected_de41 TEXT,
                    expected_de42 TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    selected_scenarios_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scenario_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    scenario_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    client_addr TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    summary TEXT
                );

                CREATE TABLE IF NOT EXISTS message_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES scenario_runs(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    mti TEXT,
                    field2_masked TEXT,
                    field11 TEXT,
                    field32 TEXT,
                    field37 TEXT,
                    field41 TEXT,
                    field42 TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hex TEXT NOT NULL,
                    validation_status TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS company_scenarios (
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    scenario_name TEXT NOT NULL,
                    PRIMARY KEY (company_id, scenario_name)
                );
                """
            )
            company_rows = conn.execute("SELECT id, scenario_name FROM companies").fetchall()
            for row in company_rows:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO company_scenarios (company_id, scenario_name)
                    VALUES (?, ?)
                    """,
                    (row["id"], row["scenario_name"]),
                )
            user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "selected_scenarios_json" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN selected_scenarios_json TEXT NOT NULL DEFAULT '[]'")

    def bootstrap_defaults(
        self,
        *,
        admin_username: str = "admin",
        admin_password: str = "admin",
        simple_partner_bootstrap: bool = False,
    ) -> None:
        scenarios = self.list_scenarios()
        default_scenario = scenarios[0]["name"]
        with self._connect() as conn:
            company_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            if company_count == 0:
                conn.execute(
                    """
                    INSERT INTO companies (name, slug, scenario_name, expected_de32, expected_de41, expected_de42)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("Demo Partner", "demo-partner", default_scenario, "123456", "TERM0001", "MERCHANTID00001"),
                )
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count == 0:
                if simple_partner_bootstrap:
                    demo_id = conn.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()[0]
                    conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role, company_id)
                        VALUES (?, ?, ?, ?)
                        """,
                        (admin_username, hash_password(admin_password), "partner_user", int(demo_id)),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role, company_id)
                        VALUES (?, ?, ?, NULL)
                        """,
                        (admin_username, hash_password(admin_password), "admin"),
                    )

    def list_scenarios(self) -> list[dict[str, Any]]:
        return json.loads(json.dumps(self._load_scenario_catalog()))

    def _load_scenario_catalog(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for scenario in list_scenarios(self.scenario_file):
            name = str(scenario.get("name") or "unnamed")
            ref_ready = False
            try:
                sc = load_scenario_file(self.scenario_file, name)
                ref_ready = scenario_supports_reference_client(sc)
            except Exception:
                ref_ready = False
            out.append(
                {
                    "name": name,
                    "description": str(scenario.get("description") or ""),
                    "filename": str(scenario.get("_source_file") or self.scenario_file.name),
                    "reference_client_ready": ref_ready,
                }
            )
        return out

    def create_company(
        self,
        *,
        name: str,
        slug: str,
        scenario_name: str,
        scenario_names: list[str] | None = None,
        expected_de32: str | None = None,
        expected_de41: str | None = None,
        expected_de42: str | None = None,
    ) -> int:
        assigned = self._normalize_company_scenarios(scenario_name, scenario_names)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO companies (name, slug, scenario_name, expected_de32, expected_de41, expected_de42)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, slug, scenario_name, expected_de32 or None, expected_de41 or None, expected_de42 or None),
            )
            company_id = int(cur.lastrowid)
            conn.executemany(
                """
                INSERT INTO company_scenarios (company_id, scenario_name)
                VALUES (?, ?)
                """,
                [(company_id, item) for item in assigned],
            )
            return company_id

    def list_companies(self) -> list[Company]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.name, c.slug, c.scenario_name, c.expected_de32, c.expected_de41, c.expected_de42, c.active,
                       GROUP_CONCAT(cs.scenario_name, '|') AS assigned_scenarios
                FROM companies c
                LEFT JOIN company_scenarios cs ON cs.company_id = c.id
                GROUP BY c.id, c.name, c.slug, c.scenario_name, c.expected_de32, c.expected_de41, c.expected_de42, c.active
                ORDER BY c.name
                """
            ).fetchall()
        return [self._row_to_company(row) for row in rows]

    def get_company(self, company_id: int) -> Company | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT c.id, c.name, c.slug, c.scenario_name, c.expected_de32, c.expected_de41, c.expected_de42, c.active,
                       GROUP_CONCAT(cs.scenario_name, '|') AS assigned_scenarios
                FROM companies c
                LEFT JOIN company_scenarios cs ON cs.company_id = c.id
                WHERE c.id = ?
                GROUP BY c.id, c.name, c.slug, c.scenario_name, c.expected_de32, c.expected_de41, c.expected_de42, c.active
                """,
                (company_id,),
            ).fetchone()
        return self._row_to_company(row) if row else None

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        company_id: int | None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, company_id)
                VALUES (?, ?, ?, ?)
                """,
                (username, hash_password(password), role, company_id),
            )
            return int(cur.lastrowid)

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.username, u.role, u.company_id, u.active, c.name AS company_name
                FROM users u
                LEFT JOIN companies c ON c.id = u.company_id
                ORDER BY u.username
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def authenticate(self, username: str, password: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, company_id, active
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        if not row or not row["active"]:
            return None
        if not verify_password(password, str(row["password_hash"])):
            return None
        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            company_id=int(row["company_id"]) if row["company_id"] is not None else None,
            active=bool(row["active"]),
        )

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, company_id, active
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            company_id=int(row["company_id"]) if row["company_id"] is not None else None,
            active=bool(row["active"]),
        )

    def get_user_selected_scenarios(self, user_id: int) -> list[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT selected_scenarios_json FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return []
        try:
            data = json.loads(str(row["selected_scenarios_json"] or "[]"))
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass
        return []

    def set_user_selected_scenarios(self, user_id: int, names: list[str]) -> None:
        catalog = {str(x["name"]) for x in self._load_scenario_catalog()}
        filtered = sorted({n for n in names if n in catalog})
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET selected_scenarios_json = ? WHERE id = ?",
                (json.dumps(filtered, ensure_ascii=False), user_id),
            )

    def set_company_default_scenario(self, company_id: int, scenario_name: str) -> None:
        self.ensure_scenario_exists(scenario_name)
        with self._connect() as conn:
            conn.execute(
                "UPDATE companies SET scenario_name = ? WHERE id = ?",
                (scenario_name, company_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO company_scenarios (company_id, scenario_name)
                VALUES (?, ?)
                """,
                (company_id, scenario_name),
            )

    def _resolve_company_single_tenant(self, default_company_slug: str | None) -> Company | None:
        companies = [c for c in self.list_companies() if c.active]
        if default_company_slug:
            for c in companies:
                if c.slug == default_company_slug:
                    return c
            return None
        if len(companies) == 1:
            return companies[0]
        return None

    def resolve_company(
        self,
        decoded: dict[str, Any],
        *,
        single_tenant: bool = False,
        default_company_slug: str | None = None,
    ) -> Company | None:
        if single_tenant:
            return self._resolve_company_single_tenant(default_company_slug)
        companies = [company for company in self.list_companies() if company.active]
        candidates: list[tuple[int, Company]] = []
        for company in companies:
            score = 0
            for field_name, expected in (
                ("32", company.expected_de32),
                ("41", company.expected_de41),
                ("42", company.expected_de42),
            ):
                if not expected:
                    continue
                actual = str(decoded.get(field_name) or "").strip()
                if actual != expected:
                    score = -1
                    break
                score += 1
            if score >= 0:
                candidates.append((score, company))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        if len(candidates) == 1:
            return candidates[0][1]
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            return None
        return candidates[0][1]

    def ensure_scenario_exists(self, scenario_name: str) -> None:
        load_scenario_file(self.scenario_file, scenario_name)

    def _normalize_company_scenarios(self, default_scenario_name: str, scenario_names: list[str] | None) -> list[str]:
        assigned = [item.strip() for item in (scenario_names or []) if item.strip()]
        if default_scenario_name not in assigned:
            assigned.append(default_scenario_name)
        deduped = sorted(set(assigned))
        for item in deduped:
            self.ensure_scenario_exists(item)
        return deduped

    def create_run(self, *, company: Company, scenario_name: str, session_id: str, client_addr: str | None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scenario_runs (company_id, scenario_name, status, session_id, client_addr)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company.id, scenario_name, "running", session_id, client_addr),
            )
            return int(cur.lastrowid)

    def record_message(
        self,
        *,
        run_id: int,
        seq: int,
        direction: str,
        payload: bytes,
        decoded: dict[str, Any],
        validation_status: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        masked = self._sanitize_decoded(decoded)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message_events (
                    run_id, seq, direction, mti, field2_masked, field11, field32, field37, field41, field42,
                    payload_json, payload_hex, validation_status, error_code, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    seq,
                    direction,
                    str(decoded.get("t") or ""),
                    masked.get("2"),
                    str(decoded.get("11") or "") or None,
                    str(decoded.get("32") or "") or None,
                    str(decoded.get("37") or "") or None,
                    str(decoded.get("41") or "") or None,
                    str(decoded.get("42") or "") or None,
                    json.dumps(masked, ensure_ascii=False, sort_keys=True),
                    payload.hex(),
                    validation_status,
                    error_code,
                    error_message,
                ),
            )

    def finish_run(self, run_id: int, *, status: str, summary: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scenario_runs
                SET status = ?, summary = ?, finished_at = CURRENT_TIMESTAMP
                WHERE id = ? AND finished_at IS NULL
                """,
                (status, summary, run_id),
            )

    def audit(
        self,
        event_type: str,
        *,
        user_id: int | None = None,
        company_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (user_id, company_id, event_type, details_json)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, company_id, event_type, json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
            )

    def list_runs(self, user: User) -> list[dict[str, Any]]:
        sql = """
            SELECT r.id, r.scenario_name, r.status, r.session_id, r.client_addr, r.started_at, r.finished_at, r.summary,
                   c.name AS company_name, c.id AS company_id
            FROM scenario_runs r
            JOIN companies c ON c.id = r.company_id
        """
        params: tuple[Any, ...] = ()
        if user.role != "admin":
            sql += " WHERE r.company_id = ?"
            params = (user.company_id,)
        sql += " ORDER BY r.id DESC LIMIT 100"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: int, user: User) -> dict[str, Any] | None:
        sql = """
            SELECT r.id, r.scenario_name, r.status, r.session_id, r.client_addr, r.started_at, r.finished_at, r.summary,
                   c.name AS company_name, c.id AS company_id
            FROM scenario_runs r
            JOIN companies c ON c.id = r.company_id
            WHERE r.id = ?
        """
        params: tuple[Any, ...] = (run_id,)
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        if user.role != "admin" and int(row["company_id"]) != user.company_id:
            return None
        return dict(row)

    def list_messages_for_run(self, run_id: int, user: User) -> list[dict[str, Any]]:
        run = self.get_run(run_id, user)
        if not run:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, seq, direction, mti, field2_masked, field11, field32, field37, field41, field42,
                       payload_json, payload_hex, validation_status, error_code, error_message, created_at
                FROM message_events
                WHERE run_id = ?
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_recent_audits(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])

    def _sanitize_decoded(self, decoded: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in decoded.items():
            if key == "2":
                out[key] = mask_pan(str(value))
            elif key in {"35", "45", "52", "55"}:
                out[key] = "<redacted>"
            else:
                out[key] = str(value)
        return out

    def _row_to_company(self, row: sqlite3.Row) -> Company:
        assigned_raw = str(row["assigned_scenarios"] or "")
        assigned = tuple(sorted(item for item in assigned_raw.split("|") if item))
        if not assigned:
            assigned = (str(row["scenario_name"]),)
        return Company(
            id=int(row["id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            scenario_name=str(row["scenario_name"]),
            assigned_scenarios=assigned,
            expected_de32=str(row["expected_de32"]) if row["expected_de32"] is not None else None,
            expected_de41=str(row["expected_de41"]) if row["expected_de41"] is not None else None,
            expected_de42=str(row["expected_de42"]) if row["expected_de42"] is not None else None,
            active=bool(row["active"]),
        )
