"""Canonical external links for published interactive works.

Next.js workbench uses trailingSlash=true and is mounted under a basePath,
normally /narrativeos. Never derive public sharing URLs from an untrusted
HTTP Host header: the configured WEBGAL_FRONTEND_URL is authoritative.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

WORK_ID = re.compile(r"^[0-9a-f]{32}$")


def _base(frontend_url: str) -> str:
    url = frontend_url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password:
        raise ValueError("Public workbench URL is invalid")
    if parts.query or parts.fragment:
        raise ValueError("Public workbench URL must not include a query or fragment")
    # Avoid duplicating the Next basePath if a config accidentally points at
    # the practice page instead of the workbench root.
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def work_page_url(frontend_url: str, work_id: str) -> str:
    if not WORK_ID.fullmatch(work_id):
        raise ValueError("Invalid public work identifier")
    return _base(frontend_url) + "/practice/works/" + work_id + "/"


def work_cover_url(frontend_url: str, work_id: str) -> str:
    if not WORK_ID.fullmatch(work_id):
        raise ValueError("Invalid public work identifier")
    return _base(frontend_url) + "/api/forge/public/works/" + work_id + "/cover.png"


def canonical_published_url(frontend_url: str, work_id: str, stored_url: str | None) -> str:
    """Use an existing published URL only if its origin/basePath match config.

    Repair old slashless records without silently turning an unrelated,
    potentially malicious stored URL into a shareable link.
    """
    canonical = work_page_url(frontend_url, work_id)
    if not stored_url:
        return canonical
    previous = urlsplit(stored_url)
    expected = urlsplit(canonical)
    if (previous.scheme, previous.netloc, previous.path.rstrip("/")) == (
        expected.scheme, expected.netloc, expected.path.rstrip("/")
    ):
        return canonical
    return canonical
