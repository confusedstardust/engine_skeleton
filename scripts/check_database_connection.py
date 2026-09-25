from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webgal_backend.config import settings
from webgal_backend.database import database_connection


REQUIRED_TABLES = {
    "users", "games", "generation_jobs", "generation_job_events",
    "assets", "asset_files", "draft_asset_usages",
}
REQUIRED_COLUMNS = {
    "generation_jobs": {"source_material", "lock_version", "artifact_manifest_json"},
    "assets": {"source_key"},
}
BUSINESS_TABLES = (
    "games", "generation_jobs", "generation_job_events", "game_versions",
    "assets", "asset_files", "draft_asset_usages", "asset_usages",
    "game_likes", "game_favorites", "products", "purchase_orders",
    "payment_attempts", "entitlement_grants", "credit_reservations",
    "credit_ledger", "outbox_events",
)


def main() -> int:
    report: dict[str, object] = {
        "configured": bool(settings.database_url),
        "database_job_store_enabled": settings.database_job_store_enabled,
        "asset_library_enabled": settings.asset_library_enabled,
    }
    if not settings.database_url:
        report.update({"connected": False, "error": "NARRATIVEOS_DATABASE_URL is not configured"})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    try:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION() version, DATABASE() database_name, @@session.time_zone time_zone")
                server = cursor.fetchone()
                cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
                tables = {str(row["TABLE_NAME"]) for row in cursor.fetchall()}
                missing_columns: dict[str, list[str]] = {}
                for table, required in REQUIRED_COLUMNS.items():
                    if table not in tables:
                        continue
                    cursor.execute(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
                        (table,),
                    )
                    present = {str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
                    if required - present:
                        missing_columns[table] = sorted(required - present)
                cursor.execute("SELECT COUNT(*) count FROM users")
                user_count = int(cursor.fetchone()["count"])
                row_counts: dict[str, int] = {}
                for table in BUSINESS_TABLES:
                    if table in tables:
                        cursor.execute(f"SELECT COUNT(*) count FROM `{table}`")
                        row_counts[table] = int(cursor.fetchone()["count"])
                missing_tables = sorted(REQUIRED_TABLES - tables)
                write_probe = "SKIPPED_SCHEMA_INCOMPLETE" if missing_tables or missing_columns else "SKIPPED_NO_USER"
                if user_count and not missing_tables and not missing_columns:
                    cursor.execute("SELECT id FROM users ORDER BY created_at,id LIMIT 1")
                    user_id = str(cursor.fetchone()["id"])
                    game_id, job_id = uuid.uuid4().hex, uuid.uuid4().hex
                    cursor.execute(
                        "INSERT INTO games(id,owner_user_id,title,status,visibility) VALUES(%s,%s,'connection probe','DRAFT','PRIVATE')",
                        (game_id, user_id),
                    )
                    cursor.execute(
                        """INSERT INTO generation_jobs
                        (id,game_id,owner_user_id,source_material,request_key,request_hash,status,legacy_status,job_storage_prefix)
                        VALUES(%s,%s,%s,'connection probe',%s,REPEAT('0',64),'CREATED','CREATED',%s)""",
                        (job_id, game_id, user_id, job_id, f"jobs/{job_id}"),
                    )
                    cursor.execute(
                        "INSERT INTO generation_job_events(job_id,event_type,status) VALUES(%s,'PROBE','CREATED')",
                        (job_id,),
                    )
                    write_probe = "PASS_ROLLED_BACK"
                connection.rollback()
            report.update({
                "connected": True,
                "server_version": server["version"],
                "database": server["database_name"],
                "session_time_zone": server["time_zone"],
                "required_tables_present": sorted(REQUIRED_TABLES & tables),
                "required_tables_missing": missing_tables,
                "required_columns_missing": missing_columns,
                "table_count": len(tables),
                "user_count": user_count,
                "business_row_counts": row_counts,
                "write_probe": write_probe,
            })
    except Exception as exc:
        report.update({"connected": False, "error_type": type(exc).__name__, "error": str(exc)})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["required_tables_missing"] and not report["required_columns_missing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
