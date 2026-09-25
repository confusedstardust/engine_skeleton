from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webgal_backend.asset_library import sync_generated_job_assets
from webgal_backend.config import settings


def candidate_jobs(job_id: str | None):
    paths = [settings.jobs_dir / job_id / "job.json"] if job_id else sorted(settings.jobs_dir.glob("*/job.json"))
    for path in paths:
        if not path.exists():
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        identity = job.get("identity")
        if isinstance(identity, dict) and identity.get("type") == "sso" and identity.get("user_id"):
            yield job, path.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Register existing Forge generated assets in the NarrativeOS asset library.")
    parser.add_argument("--job-id", help="Only inspect or backfill one job")
    parser.add_argument("--execute", action="store_true", help="Upload and write records; omission is a dry run")
    args = parser.parse_args()
    jobs = list(candidate_jobs(args.job_id))
    if not args.execute:
        files = sum(
            1 for _, directory in jobs
            for root in (directory / "public" / "game", directory / "draft" / "game")
            for category in ("background", "figure", "vocal", "bgm", "soundeffect")
            if (root / category).exists()
            for path in (root / category).iterdir() if path.is_file()
        )
        print(json.dumps({"mode": "dry-run", "jobs": len(jobs), "candidate_files": files}, ensure_ascii=False))
        return 0
    if not settings.asset_library_enabled:
        parser.error("WEBGAL_ASSET_LIBRARY_ENABLED must be true for --execute")
    total = 0
    for job, directory in jobs:
        records = sync_generated_job_assets(job, directory)
        total += len(records)
        print(json.dumps({"job_id": job["id"], "registered": len(records)}, ensure_ascii=False))
    print(json.dumps({"mode": "execute", "jobs": len(jobs), "registered": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
