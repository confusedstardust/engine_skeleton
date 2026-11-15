"""Count unique Forge browser visits by Beijing calendar day."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .database import database_transaction

router = APIRouter()
BEIJING = timezone(timedelta(hours=8))


# Filter only known crawler User-Agents at write time. Never block the requested
# HTML/JS/assets: crawlers should still be allowed to index public pages.
# Both direct Forge telemetry and the website reverse proxy reach this handler.
_EXCLUDED_UA_TOKENS = ("googleother", "googlebot", "reflectionbot",
                       "baiduspider", "baidu.com/search/spider")


def is_excluded_visitor_agent(user_agent: str | None) -> bool:
    agent = (user_agent or "").casefold()
    return any(token in agent for token in _EXCLUDED_UA_TOKENS)


class Visit(BaseModel):
    visitor_id: UUID


@router.get("/play/_telemetry/visitor.js", include_in_schema=False)
def visitor_script():
    return FileResponse(Path(__file__).with_name("site_visitor.js"), media_type="text/javascript")


@router.post("/play/_telemetry/visit", status_code=204)
def record_site_visit(visit: Visit, request: Request):
    if is_excluded_visitor_agent(request.headers.get("user-agent")):
        # Preserve the existing telemetry contract and avoid triggering retries.
        return Response(status_code=204)
    day = datetime.now(BEIJING).date()
    visitor_hash = sha256(visit.visitor_id.bytes).digest()
    with database_transaction() as cursor:
        cursor.execute(
            """INSERT INTO site_daily_visitors (visit_date, visitor_hash) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE visitor_hash = site_daily_visitors.visitor_hash""",
            (day, visitor_hash),
        )
    return Response(status_code=204)
