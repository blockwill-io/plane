"""BlockWill fork — Plane as an OAuth authorization server.

Walks the flow the Plane MCP server's PlaneOAuthProvider drives: authorize ->
(login) -> consent -> code -> token -> v1 API with the bearer token ->
app-installation -> refresh. Plus the ways it must refuse.
"""

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from plane.db.models import OAuthApplication, OAuthAuthorizationCode, OAuthToken, Workspace, WorkspaceMember
from plane.db.models.oauth import hash_secret

REDIRECT = "https://mcp.example.com/http/auth/callback"


@pytest.fixture(autouse=True)
def local_settings(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "oauth"}}
    settings.APP_BASE_URL = "https://plane.example.com"


@pytest.fixture
def app(db):
    secret = "s3cret-" + secrets.token_hex(8)
    application = OAuthApplication.objects.create(
        name="Plane MCP", client_id="plane_app_test", client_secret_hash=hash_secret(secret), redirect_uris=REDIRECT
    )
    application.plain_secret = secret
    return application


@pytest.fixture
def browser(create_user):
    client = Client()
    client.force_login(create_user)
    return client


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize(client, app, challenge, **extra):
    params = {
        "client_id": app.client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "state": "xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "read write",
        **extra,
    }
    return client.get("/auth/o/authorize-app/", params)


def allow(client, workspace):
    return client.post("/auth/o/authorize-app/consent/", {"decision": "allow", "workspace": workspace.slug})


def code_from(response):
    query = parse_qs(urlparse(response["Location"]).query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def exchange(app, **data):
    return Client().post(
        "/auth/o/token/",
        {"client_id": app.client_id, "client_secret": app.plain_secret, **data},
    )


def full_flow(browser, app, workspace):
    verifier, challenge = pkce()
    assert authorize(browser, app, challenge)["Location"] == "/auth/o/authorize-app/consent/"
    code = code_from(allow(browser, workspace))
    return exchange(app, grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier)


@pytest.mark.contract
@pytest.mark.django_db
class TestOAuthFlow:
    def test_end_to_end(self, browser, app, workspace, create_user):
        verifier, challenge = pkce()
        assert authorize(browser, app, challenge).status_code == 302

        page = browser.get("/auth/o/authorize-app/consent/")
        assert page.status_code == 200
        html = page.content.decode()
        assert "Allow Plane MCP" in html and workspace.name in html and create_user.email in html

        response = allow(browser, workspace)
        assert response["Location"].startswith(REDIRECT + "?")
        code = code_from(response)

        tokens = exchange(
            app, grant_type="authorization_code", code=code, redirect_uri=REDIRECT, code_verifier=verifier
        )
        assert tokens.status_code == 200
        body = tokens.json()
        assert body["token_type"] == "Bearer" and body["expires_in"] == 3600
        assert body["refresh_expires_in"] == 365 * 24 * 3600
        assert body["access_token"].startswith("plane_oat_") and body["refresh_token"].startswith("plane_ort_")

        # The token works on the v1 API, as the user who allowed it.
        api = Client(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")
        me = api.get("/api/v1/users/me/")
        assert me.status_code == 200 and me.json()["email"] == create_user.email
        assert api.get(f"/api/v1/workspaces/{workspace.slug}/projects/").status_code == 200

        installs = api.get("/auth/o/app-installation/").json()
        assert installs[0]["workspace_detail"]["slug"] == workspace.slug

        # Refresh rotates both tokens and retires the old pair.
        refreshed = exchange(app, grant_type="refresh_token", refresh_token=body["refresh_token"]).json()
        assert refreshed["access_token"] != body["access_token"]
        assert api.get("/api/v1/users/me/").status_code == 403
        assert (
            Client(HTTP_AUTHORIZATION=f"Bearer {refreshed['access_token']}").get("/api/v1/users/me/").status_code == 200
        )
        assert exchange(app, grant_type="refresh_token", refresh_token=body["refresh_token"]).status_code == 400

    def test_basic_client_auth(self, browser, app, workspace):
        verifier, challenge = pkce()
        authorize(browser, app, challenge)
        code = code_from(allow(browser, workspace))
        basic = base64.b64encode(f"{app.client_id}:{app.plain_secret}".encode()).decode()
        response = Client().post(
            "/auth/o/token/",
            {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier},
            HTTP_AUTHORIZATION=f"Basic {basic}",
        )
        assert response.status_code == 200

    def test_signed_out_browser_goes_through_plane_login(self, app, create_user, workspace):
        client = Client()
        _, challenge = pkce()
        response = authorize(client, app, challenge)
        assert response["Location"].endswith("/oauth/continue")
        assert "plane_oauth_request" in response.cookies
        # after logging in, the web app bounces back to consent with the cookie intact
        client.force_login(create_user)
        assert client.get("/auth/o/authorize-app/consent/").status_code == 200

    def test_deny(self, browser, app, workspace):
        authorize(browser, app, pkce()[1])
        response = browser.post("/auth/o/authorize-app/consent/", {"decision": "deny"})
        query = parse_qs(urlparse(response["Location"]).query)
        assert query["error"] == ["access_denied"] and query["state"] == ["xyz"]
        assert not OAuthAuthorizationCode.objects.exists()


@pytest.mark.contract
@pytest.mark.django_db
class TestOAuthRefusals:
    def test_unknown_client_and_redirect_never_redirect(self, browser, app):
        assert browser.get("/auth/o/authorize-app/", {"client_id": "nope", "response_type": "code"}).status_code == 400
        response = authorize(browser, app, pkce()[1], redirect_uri="https://evil.example.com/cb")
        assert response.status_code == 400 and "Location" not in response

    def test_plain_pkce_rejected(self, browser, app):
        response = authorize(browser, app, "abc", code_challenge_method="plain")
        assert parse_qs(urlparse(response["Location"]).query)["error"] == ["invalid_request"]

    def test_wrong_verifier_secret_and_redirect(self, browser, app, workspace):
        verifier, challenge = pkce()
        authorize(browser, app, challenge)
        code = code_from(allow(browser, workspace))
        base = {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT}
        assert exchange(app, **base, code_verifier="wrong").json()["error"] == "invalid_grant"
        bad_secret = Client().post("/auth/o/token/", {**base, "client_id": app.client_id, "client_secret": "x"})
        assert bad_secret.status_code == 401
        assert exchange(app, **{**base, "redirect_uri": REDIRECT + "x"}, code_verifier=verifier).status_code == 400

    def test_code_replay_revokes_tokens(self, browser, app, workspace):
        verifier, challenge = pkce()
        authorize(browser, app, challenge)
        code = code_from(allow(browser, workspace))
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier}
        access = exchange(app, **data).json()["access_token"]
        assert exchange(app, **data).json()["error"] == "invalid_grant"
        assert Client(HTTP_AUTHORIZATION=f"Bearer {access}").get("/api/v1/users/me/").status_code == 403

    def test_expired_code(self, browser, app, workspace):
        verifier, challenge = pkce()
        authorize(browser, app, challenge)
        code = code_from(allow(browser, workspace))
        OAuthAuthorizationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier}
        assert exchange(app, **data).json()["error"] == "invalid_grant"

    def test_expired_access_token(self, browser, app, workspace):
        access = full_flow(browser, app, workspace).json()["access_token"]
        OAuthToken.objects.update(access_expires_at=timezone.now() - timedelta(seconds=1))
        assert Client(HTTP_AUTHORIZATION=f"Bearer {access}").get("/api/v1/users/me/").status_code == 403

    def test_cannot_pick_someone_elses_workspace(self, browser, app, workspace, create_user):
        other = Workspace.objects.create(name="Other", slug="other-ws", owner=create_user)
        WorkspaceMember.objects.filter(workspace=other).delete()
        authorize(browser, app, pkce()[1])
        assert allow(browser, other).status_code == 400

    def test_refresh_stops_when_membership_ends(self, browser, app, workspace, create_user):
        refresh = full_flow(browser, app, workspace).json()["refresh_token"]
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(is_active=False)
        assert exchange(app, grant_type="refresh_token", refresh_token=refresh).json()["error"] == "invalid_grant"

    def test_other_bearer_tokens_are_left_alone(self, api_key_client):
        # A non-OAuth bearer header must not break API-key auth.
        api_key_client.credentials(HTTP_X_API_KEY="test-api-token-12345", HTTP_AUTHORIZATION="Bearer something-else")
        assert api_key_client.get("/api/v1/users/me/").status_code == 200


@pytest.mark.django_db
def test_create_oauth_app_command(capsys):
    call_command("create_oauth_app", "--name", "Plane MCP", "--redirect-uri", REDIRECT)
    out = capsys.readouterr().out
    secret = out.split("client_secret=")[1].split()[0]
    app = OAuthApplication.objects.get(name="Plane MCP")
    assert app.check_secret(secret) and app.redirect_uri_list == [REDIRECT]

    call_command("create_oauth_app", "--name", "Plane MCP", "--redirect-uri", REDIRECT)
    assert not app.__class__.objects.get(pk=app.pk).check_secret(secret)
