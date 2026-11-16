"""Explicit, dry-run-by-default legacy Teacher Plaza link repair.

Old Teacher Plaza rows may still contain '/practice/works/{id}/' even after
the work URL generator is fixed. This operator command re-publishes only an
already-published work, keeps its published version, and repairs local metadata
after remote confirmation. Never auto-run it on service startup.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Callable

from .storage import read_json, utc_now, write_json
from .teacher_ecosystem import publication_status, publish_work
from .work_store import WorkConflictError, WorkStore
from .work_urls import work_page_url, work_cover_url


def eligible_repairs(store: WorkStore, frontend_url: str,
                     work_id: str | None = None, force: bool = False) -> list[dict]:
    candidates = [store.path(work_id)] if work_id else list(store.root.glob("*/"))
    plans = []
    for directory in candidates:
        try:
            saved = read_json(directory / "work.json")
            if (saved.get("id") != directory.name or
                    saved.get("publication_status") != "published" or
                    not saved.get("published_version_id")):
                continue
            canonical = work_page_url(frontend_url, saved["id"])
            if force or saved.get("public_url") != canonical:
                plans.append({"id": saved["id"], "owner": saved["owner_user_id"],
                              "version": saved["published_version_id"],
                              "old_url": saved.get("public_url"), "new_url": canonical,
                              "work": saved})
        except (OSError, ValueError, KeyError, AttributeError):
            continue
    return plans


def repair_one(store: WorkStore, plan: dict, frontend_url: str,
               *, lookup: Callable = publication_status,
               publish: Callable = publish_work,
               author_override: str | None = None) -> str:
    """Re-publish remote listing first; update local URL only after confirmation."""
    remote = lookup(plan["id"])
    if not isinstance(remote, dict) or remote.get("published") is not True:
        raise WorkConflictError("Remote listing is not confirmed published")
    details = remote.get("work") if isinstance(remote.get("work"), dict) else remote
    author = (details.get("authorName") or details.get("author_name") or author_override)
    if not isinstance(author, str) or not author.strip():
        raise WorkConflictError("Cannot preserve author attribution; supply --author-name for one work")
    saved = plan["work"]
    metadata = saved.get("published_metadata") or {}
    payload = {
        "ownerUserId": plan["owner"], "authorName": author.strip(),
        "jobId": plan["id"], "resourceType": "INTERACTIVE_HTML",
        "title": metadata.get("title") or saved["title"],
        "summary": metadata.get("summary") or "",
        "subject": metadata.get("subject"),
        "grade": metadata.get("grade"),
        "tags": metadata.get("tags") or [],
        "coverUrl": work_cover_url(frontend_url, plan["id"]),
        "playUrl": plan["new_url"], "quizUrl": None,
    }
    result = publish(payload)
    if not isinstance(result, dict) or result.get("published") is not True:
        raise WorkConflictError("Teacher Plaza has not confirmed the updated URL")
    with store.locked():
        current = store.get(plan["owner"], plan["id"])
        if (current.get("publication_status") != "published" or
                current.get("published_version_id") != plan["version"]):
            raise WorkConflictError("Publication changed during link repair; review remote listing")
        current["public_url"] = plan["new_url"]
        current["updated_at"] = utc_now()
        write_json(store.path(plan["id"]) / "work.json", current)
    return plan["new_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair existing wrong-base-path Teacher Plaza links")
    parser.add_argument("--frontend-url", default=os.getenv("WEBGAL_FRONTEND_URL", ""))
    parser.add_argument("--work-id", help="Restrict to one published saved work")
    parser.add_argument("--author-name", help="Only for a single work when remote status lacks author")
    parser.add_argument("--force", action="store_true",
                        help="Recheck remote index even when the local URL already looks correct")
    parser.add_argument("--execute", action="store_true", help="Explicitly update remote index")
    args = parser.parse_args()
    if not args.frontend_url:
        parser.error("WEBGAL_FRONTEND_URL or --frontend-url is required")
    if args.author_name and not args.work_id:
        parser.error("--author-name requires --work-id")
    if args.force and not args.work_id:
        parser.error("--force requires --work-id")
    store = WorkStore()
    pending = eligible_repairs(store, args.frontend_url, args.work_id, force=args.force)
    print(f"Potential legacy links: {len(pending)}")
    for item in pending:
        print(f"{item['id']}: {item['old_url']} -> {item['new_url']}")
        if not args.execute:
            continue
        try:
            print("Updated:", repair_one(store, item, args.frontend_url,
                                         author_override=args.author_name))
        except Exception as error:
            # Log only the error class, never secrets or remote credential bodies.
            print(f"SKIPPED {item['id']}: {type(error).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
