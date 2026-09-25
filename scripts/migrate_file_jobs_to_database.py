from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webgal_backend.config import settings
from webgal_backend.database import database_connection
from webgal_backend.storage import _canonical_status


def load_jobs(job_id: str | None):
    paths = [settings.jobs_dir / job_id / "job.json"] if job_id else sorted(settings.jobs_dir.glob("*/job.json"))
    for path in paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            yield payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate file-backed Forge jobs into generation_jobs.")
    parser.add_argument("--job-id")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    jobs = list(load_jobs(args.job_id))
    eligible = [job for job in jobs if isinstance(job.get("identity"), dict) and job["identity"].get("type") == "sso" and job["identity"].get("user_id")]
    summary = {"mode": "execute" if args.execute else "dry-run", "found": len(jobs), "eligible_sso": len(eligible), "skipped_non_sso": len(jobs) - len(eligible)}
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    migrated = existing = missing_users = 0
    with database_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for job in eligible:
                    job_id = str(job["id"])
                    user_id = str(job["identity"]["user_id"])
                    cursor.execute("SELECT id FROM generation_jobs WHERE id=%s", (job_id,))
                    if cursor.fetchone():
                        existing += 1
                        continue
                    cursor.execute("SELECT id FROM users WHERE id=%s", (user_id,))
                    if not cursor.fetchone():
                        missing_users += 1
                        continue
                    game_id = uuid.uuid5(uuid.NAMESPACE_URL, f"narrativeos:legacy-game:{job_id}").hex
                    source = str(job.get("source_material") or "")
                    options = job.get("options") if isinstance(job.get("options"), dict) else {}
                    title = str(options.get("classroom_topic") or "").strip() or next((line.strip() for line in source.splitlines() if line.strip()), "未命名作品")
                    request_json = json.dumps({"source_material": source, "options": options}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    created_at = job.get("created_at")
                    updated_at = job.get("updated_at") or created_at
                    cursor.execute(
                        "INSERT INTO games(id,owner_user_id,title,status,visibility,created_at,updated_at) VALUES(%s,%s,%s,'DRAFT','PRIVATE',%s,%s)",
                        (game_id, user_id, title[:200], created_at, updated_at),
                    )
                    legacy_status = str(job.get("status") or "CREATED")
                    cursor.execute(
                        """INSERT INTO generation_jobs
                        (id,game_id,owner_user_id,source_material,request_key,request_hash,status,legacy_status,phase,
                         draft_revision,published_revision,build_state,dirty_scopes,options_json,artifact_manifest_json,
                         job_storage_prefix,source_sha256,error_message,lock_version,created_at,updated_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s)""",
                        (job_id, game_id, user_id, source, f"legacy:{job_id}", hashlib.sha256(request_json.encode()).hexdigest(),
                         _canonical_status(legacy_status), legacy_status, job.get("phase"), int(job.get("draft_revision", 0)),
                         int(job.get("published_revision", 0)), job.get("build_state", "NONE"),
                         json.dumps(job.get("dirty_scopes", []), ensure_ascii=False), json.dumps(options, ensure_ascii=False),
                         json.dumps(job.get("artifacts", {}), ensure_ascii=False), f"jobs/{job_id}",
                         hashlib.sha256(source.encode()).hexdigest(), job.get("error"), created_at, updated_at),
                    )
                    history = job.get("history") if isinstance(job.get("history"), list) else []
                    for event in history:
                        if isinstance(event, dict):
                            cursor.execute(
                                "INSERT INTO generation_job_events(job_id,event_type,status,phase,message,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                                (job_id, "ERROR" if event.get("error") else "STATUS", event.get("status"), event.get("phase"), event.get("error"), event.get("at") or created_at),
                            )
                    migrated += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    print(json.dumps({**summary, "migrated": migrated, "already_existing": existing, "missing_users": missing_users}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
