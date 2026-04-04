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


def test_resolve_company_single_tenant(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios" / "01-default.yaml"
    services = AppServices(tmp_path / "st.sqlite3", scenario_file)
    services.init_schema()
    services.bootstrap_defaults()
    company = services.resolve_company({}, single_tenant=True)
    assert company is not None
    assert company.slug == "demo-partner"


def test_resolve_company_single_tenant_slug(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios" / "01-default.yaml"
    services = AppServices(tmp_path / "st2.sqlite3", scenario_file)
    services.init_schema()
    services.bootstrap_defaults()
    services.create_company(
        name="Other",
        slug="other-co",
        scenario_name="auth_reversal",
        scenario_names=["auth_reversal"],
        expected_de32="999",
    )
    picked = services.resolve_company({}, single_tenant=True, default_company_slug="other-co")
    assert picked is not None
    assert picked.slug == "other-co"


def test_simple_partner_bootstrap(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios" / "01-default.yaml"
    services = AppServices(tmp_path / "pb.sqlite3", scenario_file)
    services.init_schema()
    services.bootstrap_defaults(
        admin_username="partner",
        admin_password="secret",
        simple_partner_bootstrap=True,
    )
    user = services.authenticate("partner", "secret")
    assert user is not None
    assert user.role == "partner_user"
    assert user.company_id is not None


def test_resolve_company_single_tenant_two_companies_without_slug(tmp_path: Path) -> None:
    scenario_file = Path(__file__).resolve().parent.parent / "scenarios" / "01-default.yaml"
    services = AppServices(tmp_path / "st3.sqlite3", scenario_file)
    services.init_schema()
    services.bootstrap_defaults()
    services.create_company(
        name="Second",
        slug="second-co",
        scenario_name="auth_reversal",
        scenario_names=["auth_reversal"],
        expected_de32="999",
    )
    assert services.resolve_company({}, single_tenant=True) is None


def test_user_plan_scenarios_roundtrip(tmp_path: Path) -> None:
    scenario_dir = Path(__file__).resolve().parent.parent / "scenarios"
    services = AppServices(tmp_path / "plan.sqlite3", scenario_dir)
    services.init_schema()
    services.bootstrap_defaults()
    admin = services.authenticate("admin", "admin")
    assert admin is not None
    services.set_user_selected_scenarios(admin.id, ["auth_reversal", "nonexistent_skip"])
    names = services.get_user_selected_scenarios(admin.id)
    assert names == ["auth_reversal"]
