# BlockWill fork — Plane as an OAuth 2.0 authorization server.
#
# Plane Cloud lets third-party apps (the Plane MCP server, so Claude) sign a
# user in through the browser; Community Edition ships no such endpoints. These
# three tables back the ones in plane/authentication/views/oauth_provider.py.
# Secrets, codes and tokens are stored only as SHA-256 hashes.

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import BaseModel


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_secret(prefix: str) -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


class OAuthApplication(BaseModel):
    """A client allowed to send users through the sign-in flow."""

    name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=64, unique=True)
    client_secret_hash = models.CharField(max_length=64)
    # One exact redirect URI per line.
    redirect_uris = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "OAuth Application"
        verbose_name_plural = "OAuth Applications"
        db_table = "oauth_applications"
        ordering = ("-created_at",)

    def __str__(self):
        return self.name

    @property
    def redirect_uri_list(self):
        return [line.strip() for line in self.redirect_uris.splitlines() if line.strip()]

    def check_secret(self, secret: str) -> bool:
        return secrets.compare_digest(self.client_secret_hash, hash_secret(secret or ""))


class OAuthAuthorizationCode(BaseModel):
    """A one-time code, minted after the user clicks Allow."""

    application = models.ForeignKey(OAuthApplication, on_delete=models.CASCADE, related_name="codes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="oauth_codes")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="oauth_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    redirect_uri = models.TextField()
    scope = models.CharField(max_length=255, blank=True, default="")
    code_challenge = models.CharField(max_length=128, blank=True, default="")
    code_challenge_method = models.CharField(max_length=10, blank=True, default="")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "OAuth Authorization Code"
        verbose_name_plural = "OAuth Authorization Codes"
        db_table = "oauth_authorization_codes"
        ordering = ("-created_at",)


class OAuthToken(BaseModel):
    """An access token and its refresh token. Refreshing revokes the old pair."""

    application = models.ForeignKey(OAuthApplication, on_delete=models.CASCADE, related_name="tokens")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="oauth_tokens")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="oauth_tokens")
    authorization_code = models.ForeignKey(
        OAuthAuthorizationCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="tokens"
    )
    access_token_hash = models.CharField(max_length=64, unique=True)
    refresh_token_hash = models.CharField(max_length=64, unique=True)
    scope = models.CharField(max_length=255, blank=True, default="")
    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "OAuth Token"
        verbose_name_plural = "OAuth Tokens"
        db_table = "oauth_tokens"
        ordering = ("-created_at",)

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])
