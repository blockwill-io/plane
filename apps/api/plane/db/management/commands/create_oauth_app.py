# BlockWill fork — register (or rotate) an OAuth client for the sign-in flow in
# plane/authentication/views/oauth_provider.py.
#
#   python manage.py create_oauth_app --name "Plane MCP" \
#       --redirect-uri https://mcp-plane.blockwill.io/http/auth/callback
#
# Prints the client id and secret once; only the secret's hash is stored.
# Re-running with the same --name rotates the secret and replaces the
# redirect URIs, which signs everyone using that app out.

import secrets

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from plane.db.models import OAuthApplication
from plane.db.models.oauth import hash_secret


class Command(BaseCommand):
    help = "Register or rotate an OAuth client application"

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--redirect-uri", action="append", required=True, dest="redirect_uris")

    def handle(self, *args, **options):
        uris = [uri.strip() for uri in options["redirect_uris"] if uri.strip()]
        for uri in uris:
            if not (uri.startswith("https://") or uri.startswith("http://localhost")):
                raise CommandError(f"redirect URI must be https (or http://localhost): {uri}")

        secret = secrets.token_urlsafe(40)
        app = OAuthApplication.objects.filter(name=options["name"]).first()
        if app is None:
            app = OAuthApplication(name=options["name"], client_id=f"plane_app_{secrets.token_hex(12)}")
            verb = "Created"
        else:
            app.tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
            verb = "Rotated"
        app.client_secret_hash = hash_secret(secret)
        app.redirect_uris = "\n".join(uris)
        app.is_active = True
        app.save()

        self.stdout.write(f"{verb} OAuth app {app.name!r}")
        self.stdout.write(f"client_id={app.client_id}")
        self.stdout.write(f"client_secret={secret}")
        self.stdout.write("Store the secret now; it is not shown again.")
