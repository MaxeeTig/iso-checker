from pathlib import Path

from iso_checker.app_services import AppServices
from iso_checker.auth import hash_password, issue_session_cookie, parse_session_cookie, verify_password


def test_password_hash_and_verify() -> None:
    stored = hash_password("secret-pass")
    assert verify_password("secret-pass", stored)
    assert not verify_password("wrong-pass", stored)


def test_session_cookie_roundtrip() -> None:
    cookie = issue_session_cookie({"user_id": 7, "role": "admin"}, "secret")
    payload = parse_session_cookie(cookie, "secret")
    assert payload is not None
    assert payload["user_id"] == 7
    assert payload["role"] == "admin"


def test_services_bootstrap_and_resolve_company(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios" / "01-default.yaml"
    services = AppServices(tmp_path / "app.sqlite3", scenario_file)
    services.init_schema()
    services.bootstrap_defaults(admin_username="admin", admin_password="admin")

    admin = services.authenticate("admin", "admin")
    assert admin is not None
    assert admin.role == "admin"

    companies = services.list_companies()
    assert len(companies) == 1
    company = services.resolve_company({"32": "123456", "41": "TERM0001", "42": "MERCHANTID00001"})
    assert company is not None
    assert company.slug == "demo-partner"
    assert company.assigned_scenarios == (company.scenario_name,)


def test_company_can_have_multiple_assigned_scenarios(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios"
    services = AppServices(tmp_path / "app.sqlite3", scenario_file)
    services.init_schema()
    company_id = services.create_company(
        name="Partner A",
        slug="partner-a",
        scenario_name="auth_reversal",
        scenario_names=["auth_reversal", "network_echo", "sign_on_sign_off"],
        expected_de32="123456",
    )
    company = services.get_company(company_id)
    assert company is not None
    assert company.scenario_name == "auth_reversal"
    assert company.assigned_scenarios == ("auth_reversal", "network_echo", "sign_on_sign_off")
