"""Shared media storage diagnostics (CLI + admin web page)."""
from __future__ import annotations

import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from django.conf import settings
from django.core.files.storage import default_storage

from party.models import Post


def _normalize_region(region: str | None) -> str:
    if not region:
        return "us-east-1"
    return region


def _detect_bucket_region(bucket: str) -> tuple[str | None, str]:
    """Return (region, error). us-east-1 buckets report an empty LocationConstraint."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client(
            "s3",
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1") or "us-east-1",
        )
        resp = client.get_bucket_location(Bucket=bucket)
        return _normalize_region(resp.get("LocationConstraint")), ""
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        return None, f"{code}: {exc}"
    except Exception as exc:
        return None, str(exc)


def _parse_s3_error(body: str) -> dict[str, str]:
    out = {"code": "", "message": "", "region": ""}
    try:
        root = ET.fromstring(body)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for tag, key in (("Code", "code"), ("Message", "message"), ("Region", "region")):
            el = root.find(f"s3:{tag}", ns) or root.find(tag)
            if el is not None and el.text:
                out[key] = el.text.strip()
    except ET.ParseError:
        m = re.search(r"<Code>([^<]+)</Code>", body)
        if m:
            out["code"] = m.group(1)
        m = re.search(r"<Message>([^<]+)</Message>", body)
        if m:
            out["message"] = m.group(1)
        m = re.search(r"<Region>([^<]+)</Region>", body)
        if m:
            out["region"] = m.group(1)
    return out


def _probe_presigned_url(url: str) -> dict:
    """HEAD the presigned URL the same way a browser img tag would."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {
                "http_status": resp.status,
                "content_type": resp.headers.get("Content-Type", ""),
                "ok": 200 <= resp.status < 300,
                "error_code": "",
                "error_message": "",
                "error_region": "",
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        err = _parse_s3_error(body)
        return {
            "http_status": exc.code,
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "ok": False,
            "error_code": err["code"],
            "error_message": err["message"],
            "error_region": err["region"],
        }
    except Exception as exc:
        return {
            "http_status": 0,
            "content_type": "",
            "ok": False,
            "error_code": "RequestFailed",
            "error_message": str(exc),
            "error_region": "",
        }


def media_diagnostics(*, sample_limit: int = 8) -> dict:
    backend = settings.STORAGES["default"]["BACKEND"]
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    key_id = getattr(settings, "AWS_ACCESS_KEY_ID", "") or ""
    configured_region = getattr(settings, "AWS_S3_REGION_NAME", "") or ""

    info = {
        "backend": backend,
        "media_url": settings.MEDIA_URL,
        "using_s3": "s3boto3" in backend.lower(),
        "bucket": bucket or "",
        "region": configured_region,
        "bucket_region": "",
        "region_mismatch": False,
        "querystring_auth": getattr(settings, "AWS_QUERYSTRING_AUTH", None),
        "access_key_set": bool(key_id),
        "samples": [],
        "ok": True,
        "issues": [],
    }

    if info["using_s3"] and not info["access_key_set"]:
        info["ok"] = False
        info["issues"].append("AWS_ACCESS_KEY_ID is missing — uploads and signed URLs will fail.")

    if info["using_s3"] and bucket:
        actual, err = _detect_bucket_region(bucket)
        if actual:
            info["bucket_region"] = actual
            if configured_region and actual != configured_region:
                info["region_mismatch"] = True
                info["ok"] = False
                info["issues"].append(
                    f"Region mismatch: Render has AWS_S3_REGION_NAME={configured_region!r} "
                    f"but the bucket is in {actual!r}. Set AWS_S3_REGION_NAME={actual} and redeploy."
                )
        elif err:
            info["issues"].append(f"Could not read bucket region: {err}")

    posts = (
        Post.objects.filter(image__isnull=False)
        .exclude(image="")
        .order_by("-id")[:sample_limit]
    )
    if not posts:
        info["issues"].append("No posts with images in the database.")
        if info["issues"]:
            info["ok"] = False
        return info

    for post in posts:
        row = {
            "id": post.id,
            "name": post.image.name,
            "exists": None,
            "size": None,
            "url": "",
            "signed": False,
            "http_status": 0,
            "content_type": "",
            "fetch_ok": False,
            "error_code": "",
            "error_message": "",
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
            if row["url"]:
                probe = _probe_presigned_url(row["url"])
                row.update({
                    "http_status": probe["http_status"],
                    "content_type": probe["content_type"],
                    "fetch_ok": probe["ok"],
                    "error_code": probe["error_code"],
                    "error_message": probe["error_message"],
                })
                if not probe["ok"]:
                    info["ok"] = False
                    hint = probe["error_message"] or probe["error_code"] or f"HTTP {probe['http_status']}"
                    info["issues"].append(f"Post #{post.id}: presigned URL failed — {hint}")
                    if probe.get("error_region") and probe["error_region"] != configured_region:
                        info["issues"].append(
                            f"S3 expects region {probe['error_region']!r} in the signature "
                            f"(Render has {configured_region!r})."
                        )
        except Exception as exc:
            row["error"] = row["error"] or f"url: {exc}"
            info["ok"] = False
            info["issues"].append(f"Post #{post.id}: could not build URL — {exc}")
        info["samples"].append(row)

    # De-dupe issue strings while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for issue in info["issues"]:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    info["issues"] = deduped

    return info
