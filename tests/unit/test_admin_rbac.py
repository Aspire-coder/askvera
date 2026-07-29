"""Authorization and market-isolation tests for portal administrators."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import admin_routes
from services import admin_users


def _principal(*scopes: dict[str, str], role: str = "section_scoped") -> dict:
    return {"role": role, "status": "active", "scopes": list(scopes)}


def _request(principal: dict) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(admin_identity=principal, correlation_id="admin-test")
    )


def test_country_scope_allows_only_its_market() -> None:
    principal = _principal({"market": "CA", "section": "insights", "permission": "view"})

    assert admin_users.can_access(principal, "insights", "view", "CA")
    assert not admin_users.can_access(principal, "insights", "view", "US")
    assert not admin_users.can_access(principal, "knowledge", "view", "CA")


def test_country_scoped_viewer_can_open_section_before_market_filtering() -> None:
    principal = _principal({"market": "GB", "section": "flow", "permission": "view"})

    assert admin_users.can_access(principal, "flow", "view")
    assert admin_users.accessible_markets(principal, "flow", "view") == {"GB"}


def test_permission_hierarchy_is_section_specific() -> None:
    principal = _principal(
        {"market": "CA", "section": "knowledge", "permission": "publish"},
        {"market": "CA", "section": "users", "permission": "view"},
    )

    assert admin_users.can_access(principal, "knowledge", "stage", "CA")
    assert admin_users.can_access(principal, "knowledge", "view", "CA")
    assert not admin_users.can_access(principal, "users", "manage", "CA")


def test_disabled_admin_is_denied() -> None:
    principal = {"role": "super_admin", "status": "disabled", "scopes": []}

    assert not admin_users.can_access(principal, "insights", "view", "CA")
    with pytest.raises(HTTPException) as exc_info:
        admin_users.require_admin_access(_request(principal), "insights", "view", "CA")

    assert exc_info.value.status_code == 403


def test_trace_list_is_filtered_to_authorized_market(monkeypatch) -> None:
    principal = _principal({"market": "CA", "section": "flow", "permission": "view"})
    traces = [
        {"correlation_id": "ca-1", "country": "CA"},
        {"correlation_id": "us-1", "country": "US"},
    ]
    monkeypatch.setattr(admin_routes.pipeline_trace_store, "latest", lambda *_: traces)

    response = admin_routes.traces(_request(principal), limit=20)

    assert response["data"] == [traces[0]]


def test_ingestion_list_includes_local_and_global_records(monkeypatch) -> None:
    principal = _principal({"market": "CA", "section": "knowledge", "permission": "view"})
    jobs = [
        {"job_id": "ca", "country": "CA", "access_scope": "country"},
        {"job_id": "us", "country": "US", "access_scope": "country"},
        {"job_id": "global", "country": "GLOBAL", "access_scope": "global"},
    ]
    monkeypatch.setattr(admin_routes, "list_ingestion_jobs", lambda *_: jobs)

    response = admin_routes.ingestions(_request(principal), limit=50)

    assert [item["job_id"] for item in response["data"]] == ["ca", "global"]


def test_country_publisher_cannot_upload_global_content() -> None:
    principal = _principal({"market": "CA", "section": "knowledge", "permission": "publish"})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            admin_routes.upload_document(
                _request(principal),
                SimpleNamespace(add_task=lambda *_args, **_kwargs: None),
                SimpleNamespace(filename="policy.pdf", read=lambda *_args: b""),
                country="CA",
                language="en",
                document_type="policy",
                access_scope="global",
            )
        )

    assert exc_info.value.status_code == 403


def test_insights_all_markets_is_limited_to_assigned_scopes(monkeypatch) -> None:
    principal = _principal(
        {"market": "DE", "section": "insights", "permission": "view"},
        {"market": "CH", "section": "insights", "permission": "view"},
    )
    captured: dict = {}

    def overview_stub(**kwargs):
        captured.update(kwargs)
        return {"totals": {}}

    monkeypatch.setattr(admin_routes, "analytics_overview", overview_stub)

    response = admin_routes.overview(_request(principal))

    assert response["data"] == {"totals": {}}
    assert captured["allowed_countries"] == {"DE", "CH"}


def test_insights_rejects_unassigned_market() -> None:
    principal = _principal({"market": "CA", "section": "insights", "permission": "view"})

    with pytest.raises(HTTPException) as exc_info:
        admin_routes.overview(_request(principal), country="US")

    assert exc_info.value.status_code == 403


def test_country_admin_can_update_only_assigned_support_route(monkeypatch) -> None:
    principal = _principal(
        {"market": "GB", "section": "support", "permission": "manage"}
    )
    request = _request(principal)
    captured: dict = {}

    def update_stub(country, **values):
        captured.update({"country": country, **values})
        return {"country": country, **values}

    monkeypatch.setattr(admin_routes, "upsert_support_route", update_stub)

    response = admin_routes.support_route_update(
        "GB",
        admin_routes.SupportRouteInput(
            department="Customer Service",
            email="support@example.com",
            enabled=True,
        ),
        request,
    )

    assert response["data"]["country"] == "GB"
    assert captured["actor_sub"] == ""

    with pytest.raises(HTTPException) as exc_info:
        admin_routes.support_route_update(
            "DE",
            admin_routes.SupportRouteInput(
                department="Customer Service",
                email="support@example.com",
                enabled=True,
            ),
            request,
        )

    assert exc_info.value.status_code == 403


def test_country_admin_cannot_receive_global_admin_sections() -> None:
    with pytest.raises(ValueError, match="Country Admin"):
        admin_users._validate_role_scopes(
            "country_admin",
            [{"market": "CA", "section": "users", "permission": "manage"}],
        )


def test_users_permission_requires_all_market_scope() -> None:
    with pytest.raises(ValueError, match="Users and Audit"):
        admin_users._validate_role_scopes(
            "section_scoped",
            [{"market": "GB", "section": "users", "permission": "view"}],
        )


def test_auditor_is_read_only() -> None:
    scopes = [
        {"market": "*", "section": "users", "permission": "view"},
        {"market": "*", "section": "audit", "permission": "view"},
    ]

    assert admin_users._validate_role_scopes("auditor", scopes) == scopes
    with pytest.raises(ValueError, match="read-only"):
        admin_users._validate_role_scopes(
            "auditor",
            [{"market": "*", "section": "users", "permission": "manage"}],
        )


def test_create_user_requests_cognito_email_invite(monkeypatch) -> None:
    calls: list[dict] = []
    group_calls: list[dict] = []

    class Cognito:
        def admin_create_user(self, **kwargs):
            calls.append(kwargs)
            return {"User": {"Attributes": [{"Name": "sub", "Value": "cognito-sub"}]}}

        def admin_add_user_to_group(self, **kwargs):
            group_calls.append(kwargs)

        def admin_delete_user(self, **_kwargs):
            raise AssertionError("compensation should not run")

    class Result:
        rowcount = 1

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(admin_users, "get_aws_clients", lambda: SimpleNamespace(cognito_idp=Cognito()))
    monkeypatch.setattr(admin_users, "get_engine", lambda: Engine())
    monkeypatch.setattr(
        admin_users,
        "get_admin_user",
        lambda user_id: {"id": user_id, "email": "admin@example.com", "scopes": []},
    )

    admin_users.create_admin_user(
        email="admin@example.com",
        role="section_scoped",
        scopes=[{"market": "CA", "section": "insights", "permission": "view"}],
        actor_sub="actor",
    )

    assert calls[0]["DesiredDeliveryMediums"] == ["EMAIL"]
    assert "MessageAction" not in calls[0]
    assert calls[0]["Username"] == "admin@example.com"
    assert group_calls == [
        {
            "UserPoolId": admin_users.settings.ADMIN_COGNITO_USER_POOL_ID,
            "Username": "admin@example.com",
            "GroupName": admin_users.settings.ADMIN_COGNITO_REQUIRED_GROUP,
        }
    ]


def test_first_login_links_invited_profile_by_email(monkeypatch) -> None:
    statements: list[tuple[str, dict]] = []
    invited = {
        "id": "user-1",
        "cognito_sub": None,
        "email": "admin@example.com",
        "role": "section_scoped",
        "status": "invited",
    }

    class Result:
        def __init__(self, row=None):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    class Connection:
        def execute(self, statement, parameters=None):
            sql = str(statement)
            statements.append((sql, parameters or {}))
            return Result(invited if "SELECT * FROM admin_users" in sql else None)

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(admin_users, "get_engine", lambda: Engine())
    monkeypatch.setattr(
        admin_users,
        "get_admin_user",
        lambda _user_id: {**invited, "cognito_sub": "new-sub", "status": "active", "scopes": []},
    )

    result = admin_users.sync_admin_identity({"sub": "new-sub", "email": "admin@example.com"})

    assert result["cognito_sub"] == "new-sub"
    select_sql, select_parameters = next(
        item for item in statements if "SELECT * FROM admin_users" in item[0]
    )
    assert "lower(email) = :email" in select_sql
    assert select_parameters == {"sub": "new-sub", "email": "admin@example.com"}
    assert any(parameters.get("sub") == "new-sub" for _, parameters in statements)


def test_disable_user_calls_cognito_and_persists_status(monkeypatch) -> None:
    disabled: list[dict] = []
    statements: list[tuple[str, dict]] = []

    class Cognito:
        def admin_disable_user(self, **kwargs):
            disabled.append(kwargs)

        def admin_enable_user(self, **_kwargs):
            raise AssertionError("wrong Cognito operation")

    class Result:
        rowcount = 1

        def __init__(self, row=None, scalar=1):
            self.row = row
            self.scalar = scalar

        def mappings(self):
            return self

        def first(self):
            return self.row

        def scalar_one(self):
            return self.scalar

    class Connection:
        def execute(self, statement, parameters=None):
            sql = str(statement)
            statements.append((sql, parameters or {}))
            if "SELECT role, status, cognito_sub" in sql:
                return Result(
                    {
                        "role": "section_scoped",
                        "status": "active",
                        "cognito_sub": "user-sub",
                    }
                )
            return Result()

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(admin_users, "get_aws_clients", lambda: SimpleNamespace(cognito_idp=Cognito()))
    monkeypatch.setattr(admin_users, "get_engine", lambda: Engine())
    monkeypatch.setattr(
        admin_users,
        "get_admin_user",
        lambda _user_id: {"id": "user-1", "email": "admin@example.com", "status": "active"},
    )

    admin_users.set_admin_user_enabled("user-1", False, "actor")

    assert disabled[0]["Username"] == "admin@example.com"
    assert any(
        "SET status = 'disabled'" in sql and parameters.get("id") == "user-1"
        for sql, parameters in statements
    )


def test_first_admin_requires_configured_bootstrap_email(monkeypatch) -> None:
    class Result:
        def __init__(self, row=None, scalar=0):
            self.row = row
            self.scalar = scalar

        def mappings(self):
            return self

        def first(self):
            return self.row

        def scalar_one(self):
            return self.scalar

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(admin_users, "get_engine", lambda: Engine())
    monkeypatch.setattr(
        admin_users.settings,
        "ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL",
        "approved@example.com",
    )

    with pytest.raises(HTTPException) as exc_info:
        admin_users.sync_admin_identity(
            {"sub": "unexpected-sub", "email": "unexpected@example.com"}
        )

    assert exc_info.value.status_code == 403
    assert "not been approved" in exc_info.value.detail


def test_last_active_super_admin_cannot_be_disabled(monkeypatch) -> None:
    class Result:
        rowcount = 1

        def __init__(self, row=None, scalar=0):
            self.row = row
            self.scalar = scalar

        def mappings(self):
            return self

        def first(self):
            return self.row

        def scalar_one(self):
            return self.scalar

    class Connection:
        def execute(self, statement, _parameters=None):
            sql = str(statement)
            if "SELECT role, status, cognito_sub" in sql:
                return Result(
                    {
                        "role": "super_admin",
                        "status": "active",
                        "cognito_sub": "target-sub",
                    }
                )
            if "SELECT COUNT(*) FROM admin_users" in sql:
                return Result(scalar=0)
            return Result()

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    class Cognito:
        def admin_disable_user(self, **_kwargs):
            raise AssertionError("Cognito must not be called")

    monkeypatch.setattr(admin_users, "get_engine", lambda: Engine())
    monkeypatch.setattr(
        admin_users,
        "get_admin_user",
        lambda _user_id: {
            "id": "user-1",
            "email": "owner@example.com",
            "role": "super_admin",
            "status": "active",
        },
    )
    monkeypatch.setattr(
        admin_users,
        "get_aws_clients",
        lambda: SimpleNamespace(cognito_idp=Cognito()),
    )

    with pytest.raises(ValueError, match="At least one active Super Admin"):
        admin_users.set_admin_user_enabled("user-1", False, "different-actor")
