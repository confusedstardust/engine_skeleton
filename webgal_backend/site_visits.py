"""Count unique Forge browser visits by Beijing calendar day."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .database import database_transaction

router = APIRouter()
BEIJING = timezone(timedelta(hours=8))


class Visit(BaseModel):
    visitor_id: UUID


@router.get("/play/_telemetry/visitor.js", include_in_schema=False)
def visitor_script():
    return FileResponse(Path(__file__).with_name("site_visitor.js"), media_type="text/javascript")


@router.post("/play/_telemetry/visit", status_code=204)
def record_site_visit(visit: Visit):
    day = datetime.now(BEIJING).date()
    visitor_hash = sha256(visit.visitor_id.bytes).digest()
    with database_transaction() as cursor:
        cursor.execute(
            """INSERT INTO site_daily_visitors (visit_date, visitor_hash) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE visitor_hash = site_daily_visitors.visitor_hash""",
            (day, visitor_hash),
        )
    return Response(status_code=204)
