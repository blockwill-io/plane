# BlockWill fork — Plane as an OAuth 2.0 authorization server.
#
# The same endpoints Plane Cloud exposes, so the Plane MCP server's stock
# PlaneOAuthProvider works against this instance unchanged:
#
#   GET  /auth/o/authorize-app/          start: validate the client, remember the
#                                        request, then consent (or login first)
#   GET  /auth/o/authorize-app/consent/  "Allow <app> to use your Plane account?"
#   POST /auth/o/authorize-app/consent/  Allow -> redirect_uri?code=..&state=..
#   POST /auth/o/token/                  authorization_code / refresh_token grants
#   GET  /auth/o/app-installation/       which workspace a token is for
#
# Authorization code flow (RFC 6749 §4.1) with PKCE (RFC 7636, S256 only).
# Redirect URIs must match a registered one exactly. Codes are single-use and
# live 10 minutes; re-using one revokes what it minted. Access tokens live an
# hour, refresh tokens a year; refreshing rotates both tokens. Register a client with
# `python manage.py create_oauth_app`.

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from plane.db.models import (
    OAuthApplication,
    OAuthAuthorizationCode,
    OAuthToken,
    Workspace,
)
from plane.db.models.oauth import hash_secret, new_secret
from plane.utils.host import base_host

CODE_TTL = timedelta(minutes=10)
ACCESS_TTL = timedelta(hours=1)
# Refreshing rotates the pair with a fresh REFRESH_TTL, so this is how long a
# connection survives without being used, not a hard cap on its age.
REFRESH_TTL = timedelta(days=365)
PENDING_TTL_SECONDS = 15 * 60

ACCESS_PREFIX = "plane_oat_"
REFRESH_PREFIX = "plane_ort_"
CODE_PREFIX = "plane_oac_"

PENDING_COOKIE = "plane_oauth_request"
PENDING_SALT = "plane.oauth.pending-request"
COOKIE_PATH = "/auth/o/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_params(uri, params):
    parts = urlparse(uri)
    query = parse_qsl(parts.query, keep_blank_values=True) + [(k, v) for k, v in params.items() if v is not None]
    return urlunparse(parts._replace(query=urlencode(query)))


def _redirect_error(redirect_uri, error, state, description=None):
    return HttpResponseRedirect(
        _with_params(redirect_uri, {"error": error, "error_description": description, "state": state})
    )


def _page(title, body, status=200):
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · Plane</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f6f7f9; --card:#fff; --fg:#1d1f24; --muted:#60646c; --line:#e3e5e8;
           --accent:#3f76ff; --accent-fg:#fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111214; --card:#1b1c1f; --fg:#eceef1; --muted:#9a9ea6;
           --line:#2c2e33; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:24px 16px;
          background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  main {{ width:100%; max-width:420px; background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:28px; }}
  h1 {{ font-size:19px; margin:0 0 6px; }}
  p {{ margin:0 0 14px; color:var(--muted); }}
  strong {{ color:var(--fg); }}
  ul {{ margin:0 0 18px; padding-left:18px; color:var(--muted); }}
  label {{ display:block; font-weight:600; margin:0 0 6px; }}
  select {{ width:100%; padding:9px 10px; border:1px solid var(--line); border-radius:8px; background:var(--card);
            color:var(--fg); font:inherit; margin-bottom:20px; }}
  .row {{ display:flex; gap:10px; }}
  button {{ flex:1; padding:10px 14px; border-radius:8px; font:inherit; font-weight:600; cursor:pointer;
            border:1px solid var(--line); background:transparent; color:var(--fg); }}
  button.primary {{ background:var(--accent); border-color:var(--accent); color:var(--accent-fg); }}
  .who {{ font-size:13px; }}
</style></head>
<body><main>{body}</main></body></html>"""
    response = HttpResponse(html, status=status)
    response["Cache-Control"] = "no-store"
    response["X-Frame-Options"] = "DENY"
    return response


def _error_page(message, status=400):
    return _page("Can't connect", f"<h1>Can't connect this app</h1><p>{escape(message)}</p>", status=status)


def _workspaces_for(user):
    return Workspace.objects.filter(
        workspace_member__member=user,
        workspace_member__is_active=True,
        workspace_member__deleted_at__isnull=True,
    ).distinct()


def _token_json(body, status=200):
    response = JsonResponse(body, status=status)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _token_error(error, description, status=400):
    return _token_json({"error": error, "error_description": description}, status=status)


def _client_credentials(request):
    """client_secret_basic, falling back to client_secret_post."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode()
            client_id, _, client_secret = decoded.partition(":")
            return unquote(client_id), unquote(client_secret)
        except (ValueError, UnicodeDecodeError):
            return None, None
    return request.POST.get("client_id"), request.POST.get("client_secret")


def _pkce_ok(code, verifier):
    if not code.code_challenge:
        return True
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(expected, code.code_challenge)


def _issue_tokens(application, user, workspace, scope, authorization_code=None):
    access, refresh = new_secret(ACCESS_PREFIX), new_secret(REFRESH_PREFIX)
    now = timezone.now()
    OAuthToken.objects.create(
        application=application,
        user=user,
        workspace=workspace,
        authorization_code=authorization_code,
        access_token_hash=hash_secret(access),
        refresh_token_hash=hash_secret(refresh),
        scope=scope,
        access_expires_at=now + ACCESS_TTL,
        refresh_expires_at=now + REFRESH_TTL,
    )
    return _token_json(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TTL.total_seconds()),
            "refresh_token": refresh,
            # The MCP server's OAuth proxy sizes its own refresh token from this.
            "refresh_expires_in": int(REFRESH_TTL.total_seconds()),
            "scope": scope,
        }
    )


def token_from_bearer(request):
    """The live OAuthToken behind an `Authorization: Bearer plane_oat_...` header, or None."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    raw = header[7:].strip()
    if not raw.startswith(ACCESS_PREFIX):
        return None
    return (
        OAuthToken.objects.filter(
            access_token_hash=hash_secret(raw),
            revoked_at__isnull=True,
            access_expires_at__gt=timezone.now(),
            application__is_active=True,
            user__is_active=True,
        )
        .select_related("user", "workspace", "application")
        .first()
    )


# ---------------------------------------------------------------------------
# Authorize + consent
# ---------------------------------------------------------------------------


class OAuthAuthorizeEndpoint(View):
    def get(self, request):
        params = request.GET
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri", "")
        state = params.get("state")

        application = OAuthApplication.objects.filter(client_id=client_id, is_active=True).first()
        if application is None:
            return _error_page("This app isn't registered with this Plane instance.")
        registered = application.redirect_uri_list
        if not redirect_uri and len(registered) == 1:
            redirect_uri = registered[0]
        if redirect_uri not in registered:
            # Never redirect to an unregistered URI, not even with an error.
            return _error_page("The app sent a redirect address this Plane instance doesn't know.")

        if params.get("response_type") != "code":
            return _redirect_error(redirect_uri, "unsupported_response_type", state, "response_type must be code")
        challenge = params.get("code_challenge", "")
        method = params.get("code_challenge_method", "plain" if challenge else "")
        if challenge and method != "S256":
            return _redirect_error(redirect_uri, "invalid_request", state, "only S256 PKCE is supported")

        pending = signing.dumps(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": params.get("scope", ""),
                "code_challenge": challenge,
                "code_challenge_method": method,
            },
            salt=PENDING_SALT,
        )
        if request.user.is_authenticated:
            response = HttpResponseRedirect(f"{COOKIE_PATH}authorize-app/consent/")
        else:
            # Plane's login follows next_path inside the web app, so land on a
            # web route that bounces back to the consent screen afterwards.
            response = HttpResponseRedirect(f"{base_host(request=request, is_app=True)}/oauth/continue")
        response.set_cookie(
            PENDING_COOKIE,
            pending,
            max_age=PENDING_TTL_SECONDS,
            path=COOKIE_PATH,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=True,
            samesite="Lax",
        )
        return response


class OAuthConsentEndpoint(View):
    def _pending(self, request):
        raw = request.COOKIES.get(PENDING_COOKIE)
        if not raw:
            return None, None
        try:
            pending = signing.loads(raw, salt=PENDING_SALT, max_age=PENDING_TTL_SECONDS)
        except signing.BadSignature:
            return None, None
        application = OAuthApplication.objects.filter(client_id=pending.get("client_id"), is_active=True).first()
        if application is None or pending.get("redirect_uri") not in application.redirect_uri_list:
            return None, None
        return pending, application

    def get(self, request):
        pending, application = self._pending(request)
        if pending is None:
            return _error_page("This sign-in link has expired. Go back to the app and connect again.")
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{base_host(request=request, is_app=True)}/oauth/continue")

        workspaces = list(_workspaces_for(request.user).order_by("name"))
        if not workspaces:
            return _error_page("Your Plane account isn't a member of any workspace yet.")

        options = "".join(f'<option value="{escape(w.slug)}">{escape(w.name)}</option>' for w in workspaces)
        app = escape(application.name)
        body = f"""
<h1>Allow {app} to use your Plane account?</h1>
<p class="who">Signed in as <strong>{escape(request.user.email)}</strong></p>
<p>{app} will be able to, as you:</p>
<ul><li>read your projects, work items, cycles, modules and pages</li>
<li>create, update and delete them, within your permissions</li></ul>
<form method="post">
  <input type="hidden" name="csrfmiddlewaretoken" value="{escape(get_token(request))}">
  <label for="workspace">Workspace</label>
  <select id="workspace" name="workspace">{options}</select>
  <div class="row">
    <button type="submit" name="decision" value="deny">Cancel</button>
    <button type="submit" name="decision" value="allow" class="primary">Allow</button>
  </div>
</form>"""
        return _page(f"Allow {application.name}", body)

    def post(self, request):
        pending, application = self._pending(request)
        if pending is None:
            return _error_page("This sign-in link has expired. Go back to the app and connect again.")
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{base_host(request=request, is_app=True)}/oauth/continue")

        redirect_uri, state = pending["redirect_uri"], pending.get("state")
        if request.POST.get("decision") != "allow":
            response = _redirect_error(redirect_uri, "access_denied", state, "the user declined")
        else:
            workspace = _workspaces_for(request.user).filter(slug=request.POST.get("workspace", "")).first()
            if workspace is None:
                return _error_page("Pick one of your workspaces.")
            code = new_secret(CODE_PREFIX)
            OAuthAuthorizationCode.objects.create(
                application=application,
                user=request.user,
                workspace=workspace,
                code_hash=hash_secret(code),
                redirect_uri=redirect_uri,
                scope=pending.get("scope", ""),
                code_challenge=pending.get("code_challenge", ""),
                code_challenge_method=pending.get("code_challenge_method", ""),
                expires_at=timezone.now() + CODE_TTL,
            )
            response = HttpResponseRedirect(_with_params(redirect_uri, {"code": code, "state": state}))
        response.delete_cookie(PENDING_COOKIE, path=COOKIE_PATH)
        return response


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class OAuthTokenEndpoint(View):
    def post(self, request):
        client_id, client_secret = _client_credentials(request)
        application = OAuthApplication.objects.filter(client_id=client_id or "", is_active=True).first()
        if application is None or not application.check_secret(client_secret):
            return _token_error("invalid_client", "unknown client or wrong secret", status=401)

        grant_type = request.POST.get("grant_type")
        if grant_type == "authorization_code":
            return self._authorization_code(request, application)
        if grant_type == "refresh_token":
            return self._refresh(request, application)
        return _token_error("unsupported_grant_type", "use authorization_code or refresh_token")

    def _authorization_code(self, request, application):
        raw = request.POST.get("code", "")
        with transaction.atomic():
            code = (
                OAuthAuthorizationCode.objects.select_for_update()
                .filter(code_hash=hash_secret(raw), application=application)
                .select_related("user", "workspace")
                .first()
            )
            if code is None:
                return _token_error("invalid_grant", "unknown code")
            if code.used_at is not None:
                # A replayed code: revoke everything it minted (RFC 6749 §4.1.2).
                for token in code.tokens.filter(revoked_at__isnull=True):
                    token.revoke()
                return _token_error("invalid_grant", "code already used")
            if code.expires_at <= timezone.now():
                return _token_error("invalid_grant", "code expired")
            if request.POST.get("redirect_uri", code.redirect_uri) != code.redirect_uri:
                return _token_error("invalid_grant", "redirect_uri does not match the authorization request")
            if not _pkce_ok(code, request.POST.get("code_verifier")):
                return _token_error("invalid_grant", "code_verifier does not match")
            if not code.user.is_active:
                return _token_error("invalid_grant", "user is inactive")
            code.used_at = timezone.now()
            code.save(update_fields=["used_at"])
            return _issue_tokens(application, code.user, code.workspace, code.scope, authorization_code=code)

    def _refresh(self, request, application):
        raw = request.POST.get("refresh_token", "")
        with transaction.atomic():
            token = (
                OAuthToken.objects.select_for_update()
                .filter(refresh_token_hash=hash_secret(raw), application=application)
                .select_related("user", "workspace")
                .first()
            )
            if token is None or token.revoked_at is not None or token.refresh_expires_at <= timezone.now():
                return _token_error("invalid_grant", "refresh token is invalid, expired or revoked")
            if not token.user.is_active or not _workspaces_for(token.user).filter(id=token.workspace_id).exists():
                token.revoke()
                return _token_error("invalid_grant", "user no longer has access")
            token.revoke()
            return _issue_tokens(application, token.user, token.workspace, token.scope, token.authorization_code)


# ---------------------------------------------------------------------------
# App installation
# ---------------------------------------------------------------------------


class OAuthAppInstallationEndpoint(View):
    """The workspace a token was granted for, in Plane Cloud's shape."""

    def get(self, request):
        token = token_from_bearer(request)
        if token is None:
            return JsonResponse({"error": "invalid_token"}, status=401)
        ws = token.workspace
        stamp = token.created_at.isoformat()
        return JsonResponse(
            [
                {
                    "id": str(token.id),
                    "workspace_detail": {
                        "name": ws.name,
                        "slug": ws.slug,
                        "id": str(ws.id),
                        "logo_url": getattr(ws, "logo_url", None),
                    },
                    "created_at": stamp,
                    "updated_at": stamp,
                    "deleted_at": None,
                    "status": "installed",
                    "created_by": str(token.user_id),
                    "updated_by": str(token.user_id),
                    "workspace": str(ws.id),
                    "application": str(token.application_id),
                    "installed_by": str(token.user_id),
                    "app_bot": str(token.user_id),
                    "webhook": None,
                }
            ],
            safe=False,
        )
