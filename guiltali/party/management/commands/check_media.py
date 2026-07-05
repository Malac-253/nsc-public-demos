"""Print media storage diagnostics (local disk vs S3) for deployed debugging."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from party.media_diagnostics import media_diagnostics


class Command(BaseCommand):
    help = "Diagnose media storage and sample post image URLs."

    def handle(self, *args, **options):
        info = media_diagnostics()
        self.stdout.write(f"Storage backend: {info['backend']}")
        self.stdout.write(f"MEDIA_URL: {info['media_url']}")

        if info["using_s3"]:
            self.stdout.write(f"S3 bucket: {info['bucket']}")
            self.stdout.write(f"S3 region: {info['region']}")
            self.stdout.write(f"Querystring auth: {info['querystring_auth']}")
            self.stdout.write(
                f"Access key set: {'yes' if info['access_key_set'] else 'NO — uploads will fail'}"
            )
        else:
            self.stdout.write("S3: not configured (using local FileSystemStorage)")

        if info["issues"] and not info["samples"]:
            self.stdout.write(self.style.WARNING(info["issues"][0]))
            return

        if info["samples"]:
            self.stdout.write(f"\nSample posts ({len(info['samples'])}):")
            for row in info["samples"]:
                self.stdout.write(f"\n  Post #{row['id']} — {row['name']}")
                if row["error"]:
                    self.stdout.write(self.style.ERROR(f"    {row['error']}"))
                else:
                    self.stdout.write(f"    exists in storage: {row['exists']}")
                    if row["size"] is not None:
                        self.stdout.write(f"    size: {row['size']} bytes")
                    self.stdout.write(f"    signed URL: {row['signed']}")
                    url = row["url"]
                    self.stdout.write(f"    url: {url[:140]}{'…' if len(url) > 140 else ''}")

        for issue in info["issues"]:
            self.stdout.write(self.style.WARNING(issue))

        if info["ok"]:
            self.stdout.write(self.style.SUCCESS("\nMedia diagnostics: OK"))
        else:
            self.stdout.write(self.style.ERROR("\nMedia diagnostics: problems found"))
