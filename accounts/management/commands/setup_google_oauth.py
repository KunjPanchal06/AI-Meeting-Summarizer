"""
Management command to create/update the Google OAuth SocialApp record.

Reads GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from environment variables
and provisions the allauth SocialApp so the app works without manual admin setup.
"""

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Create or update the Google SocialApp for django-allauth OAuth"

    def handle(self, *args, **options):
        # Lazy import so the command fails gracefully if allauth isn't installed yet
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            self.stdout.write(
                self.style.WARNING(
                    "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set — "
                    "skipping SocialApp creation. Google OAuth will not work "
                    "until these are configured."
                )
            )
            return

        social_app, created = SocialApp.objects.update_or_create(
            provider="google",
            defaults={
                "name": "Google",
                "client_id": client_id,
                "secret": client_secret,
            },
        )

        # Ensure the app is linked to the current Site
        site = Site.objects.get_current()
        social_app.sites.add(site)

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created Google SocialApp (client_id={client_id[:12]}…)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated Google SocialApp (client_id={client_id[:12]}…)"
                )
            )
