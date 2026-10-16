"""Monthly grants for prepaid annual plans; no provider calls or auto-renewal."""
import calendar
import logging
from datetime import datetime, timezone

from .errors import CreditConflictError, CreditStateError


def anniversary(start: datetime, months: int) -> datetime:
    year, zero_month = divmod(start.year * 12 + start.month - 1 + months, 12)
    month = zero_month + 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


def ensure_schedule_locked(cursor, order, benefit):
    if benefit.get("billing_period") != "year":
        return
    if benefit.get("credit_delivery") != "monthly" or benefit.get("subscription_months") != 12:
        raise CreditStateError("Annual credits require an explicit 12-month delivery schedule")
    units = int(benefit["credits"]) * int(order["quantity"])
    start = order["paid_at"]
    if not isinstance(start, datetime):
        raise CreditStateError("Annual order has no payment timestamp")
    cursor.execute("SELECT * FROM subscription_credit_schedules WHERE order_id=%s FOR UPDATE", (order["id"],))
    existing = cursor.fetchone()
    if existing:
        if existing["user_id"] != order["user_id"] or int(existing["monthly_credits"]) != units or int(existing["total_cycles"]) != 12:
            raise CreditConflictError("Annual credit schedule conflicts with order snapshot")
        return
    cursor.execute("""INSERT INTO subscription_credit_schedules
        (order_id,user_id,monthly_credits,total_cycles,issued_cycles,starts_at,next_issue_at)
        VALUES (%s,%s,%s,12,1,%s,%s)""", (order["id"],order["user_id"],units,start,anniversary(start,1)))


def issue_for_user(store, user_id, *, now=None):
    from .store import _canonical_json, _stable_id
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    issued = 0
    with store.transaction() as cursor:
        cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
        if cursor.fetchone() is None:
            return 0
        cursor.execute("""SELECT * FROM subscription_credit_schedules
            WHERE user_id=%s AND next_issue_at<=%s ORDER BY order_id FOR UPDATE""", (user_id,now))
        schedules = cursor.fetchall()
        for schedule in schedules:
            cursor.execute("SELECT status,fulfillment_status FROM purchase_orders WHERE id=%s FOR UPDATE", (schedule["order_id"],))
            order = cursor.fetchone()
            if not order or order["status"] != "PAID" or order["fulfillment_status"] != "FULFILLED":
                # Refund/hold states stop delivery. Keep the date for explicit recovery.
                continue
            cycle = int(schedule["issued_cycles"])
            total = int(schedule["total_cycles"])
            units = int(schedule["monthly_credits"])
            while cycle < total and anniversary(schedule["starts_at"],cycle) <= now:
                due = anniversary(schedule["starts_at"],cycle)
                cycle += 1
                key = f"credits:month:{cycle}"
                grant_id = _stable_id("annual-credit-month-v1",schedule["order_id"],str(cycle))
                cursor.execute("SELECT id FROM entitlement_grants WHERE order_id=%s AND benefit_key=%s FOR UPDATE", (schedule["order_id"],key))
                if cursor.fetchone() is not None:
                    raise CreditStateError("Credit month exists ahead of its schedule counter")
                cursor.execute("""INSERT INTO entitlement_grants
                    (id,user_id,source,source_key,order_id,benefit_key,kind,status,
                     units_granted,units_available,units_reserved,units_consumed,units_revoked,
                     starts_at,expires_at,metadata_json)
                    VALUES (%s,%s,'ORDER',%s,%s,%s,'CREDITS','ACTIVE',%s,%s,0,0,0,%s,NULL,%s)""",
                    (grant_id,user_id,f"{schedule['order_id']}:month:{cycle}",schedule["order_id"],key,units,units,due,
                     _canonical_json({"schema_version":1,"source_order_id":schedule["order_id"],"credit_cycle":cycle})))
                store._insert_ledger(cursor,event_key=f"grant:{grant_id}",grant_id=grant_id,reservation_id=None,
                    user_id=user_id,action="GRANT",deltas=(units,0,0,0),after=(units,0,0,0))
                issued += 1
            next_due = anniversary(schedule["starts_at"],cycle) if cycle < total else None
            cursor.execute("UPDATE subscription_credit_schedules SET issued_cycles=%s,next_issue_at=%s WHERE order_id=%s",
                           (cycle,next_due,schedule["order_id"]))
    return issued


def issue_due(store, *, limit=100):
    with store.transaction() as cursor:
        cursor.execute("""SELECT s.user_id FROM subscription_credit_schedules s
            JOIN purchase_orders o ON o.id=s.order_id
            WHERE s.next_issue_at<=CURRENT_TIMESTAMP(3) AND o.status='PAID' AND o.fulfillment_status='FULFILLED'
            GROUP BY s.user_id ORDER BY MIN(s.next_issue_at) LIMIT %s""", (limit,))
        users = [row["user_id"] for row in cursor.fetchall()]
    issued = 0
    for user_id in users:
        try:
            issued += issue_for_user(store,user_id)
        except Exception:
            logging.getLogger(__name__).exception("Monthly credit delivery failed for one account; will retry")
    return issued
