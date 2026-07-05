"""Print media storage diagnostics (local disk vs S3) for deployed debugging."""
from __future__ import annotations

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from party.models import Post


class Command(BaseCommand):
    help = "Diagnose media storage and sample post image URLs."

    def handle(self, *args, **options):
        backend = settings.STORAGES["default"]["BACKEND"]
        self.stdout.write(f"Storage backend: {backend}")
        self.stdout.write(f"MEDIA_URL: {settings.MEDIA_URL}")

        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        if bucket:
            self.stdout.write(f"S3 bucket: {bucket}")
            self.stdout.write(f"S3 region: {getattr(settings, 'AWS_S3_REGION_NAME', '?')}")
            self.stdout.write(f"Querystring auth: {getattr(settings, 'AWS_QUERYSTRING_AUTH', '?')}")
            key_id = getattr(settings, "AWS_ACCESS_KEY_ID", "") or ""
            self.stdout.write(f"Access key set: {'yes' if key_id else 'NO — uploads will fail'}")
        else:
            self.stdout.write("S3: not configured (using local FileSystemStorage)")

        posts = (
            Post.objects.filter(image__isnull=False)
            .exclude(image="")
            .order_by("-id")[:8]
        )
        if not posts:
            self.stdout.write(self.style.WARNING("No posts with images in the database."))
            return

        self.stdout.write(f"\nSample posts ({posts.count()}):")
        for post in posts:
            name = post.image.name
            self.stdout.write(f"\n  Post #{post.id} — {name}")
            try:
                exists = default_storage.exists(name)
                self.stdout.write(f"    exists in storage: {exists}")
                if exists:
                    self.stdout.write(f"    size: {default_storage.size(name)} bytes")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    exists check failed: {exc}"))
            try:
                url = post.image.url
                signed = "X-Amz-" in url or "AWSAccessKeyId=" in url
                self.stdout.write(f"    signed URL: {signed}")
                self.stdout.write(f"    url: {url[:140]}{'…' if len(url) > 140 else ''}")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    url failed: {exc}"))
