"""Shared media storage diagnostics (CLI + admin web page)."""
from __future__ import annotations

from django.conf import settings
from django.core.files.storage import default_storage

from party.models import Post


def media_diagnostics(*, sample_limit: int = 8) -> dict:
    backend = settings.STORAGES["default"]["BACKEND"]
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    key_id = getattr(settings, "AWS_ACCESS_KEY_ID", "") or ""

    info = {
        "backend": backend,
        "media_url": settings.MEDIA_URL,
        "using_s3": "s3boto3" in backend.lower(),
        "bucket": bucket or "",
        "region": getattr(settings, "AWS_S3_REGION_NAME", ""),
        "querystring_auth": getattr(settings, "AWS_QUERYSTRING_AUTH", None),
        "access_key_set": bool(key_id),
        "samples": [],
        "ok": True,
        "issues": [],
    }

    if info["using_s3"] and not info["access_key_set"]:
        info["ok"] = False
        info["issues"].append("AWS_ACCESS_KEY_ID is missing — uploads and signed URLs will fail.")

    posts = (
        Post.objects.filter(image__isnull=False)
        .exclude(image="")
        .order_by("-id")[:sample_limit]
    )
    if not posts:
        info["issues"].append("No posts with images in the database.")
        return info

    for post in posts:
        row = {
            "id": post.id,
            "name": post.image.name,
            "exists": None,
            "size": None,
            "url": "",
            "signed": False,
            "error": "",
        }
        try:
            row["exists"] = default_storage.exists(post.image.name)
            if row["exists"]:
                row["size"] = default_storage.size(post.image.name)
            elif info["using_s3"]:
                info["ok"] = False
                info["issues"].append(f"Post #{post.id}: file missing in S3 ({post.image.name}).")
        except Exception as exc:
            row["error"] = f"exists check: {exc}"
            info["ok"] = False
            info["issues"].append(f"Post #{post.id}: {row['error']}")
        try:
            row["url"] = post.image.url
            row["signed"] = "X-Amz-" in row["url"] or "AWSAccessKeyId=" in row["url"]
            if info["using_s3"] and not row["signed"]:
                info["ok"] = False
                info["issues"].append(f"Post #{post.id}: URL is not presigned (private bucket will 403).")
        except Exception as exc:
            row["error"] = row["error"] or f"url: {exc}"
            info["ok"] = False
            info["issues"].append(f"Post #{post.id}: could not build URL — {exc}")
        info["samples"].append(row)

    return info
