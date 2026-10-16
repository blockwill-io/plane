# BlockWill fork — `Authorization: Bearer plane_oat_...` on the v1 API, for
# tokens minted by the OAuth flow in plane/authentication/views/oauth_provider.py.
# Headers that are not one of these tokens are left for other authenticators.

from django.utils import timezone
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from plane.authentication.views.oauth_provider import ACCESS_PREFIX, token_from_bearer


class OAuthBearerAuthentication(authentication.BaseAuthentication):
    www_authenticate_realm = "api"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith("bearer ") or not header[7:].strip().startswith(ACCESS_PREFIX):
            return None
        token = token_from_bearer(request)
        if token is None:
            raise AuthenticationFailed("OAuth access token is invalid or expired")
        now = timezone.now()
        # Throttle the write: once a minute is plenty for "last used".
        if token.last_used_at is None or (now - token.last_used_at).total_seconds() > 60:
            token.last_used_at = now
            token.save(update_fields=["last_used_at"])
        return token.user, token

    def authenticate_header(self, request):
        return f'Bearer realm="{self.www_authenticate_realm}"'
