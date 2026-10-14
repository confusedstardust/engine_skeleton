"""One bounded compensation pass: python -m webgal_backend.reconcile_payments."""
import asyncio
import logging

from .payments import database_call, get_payment_store, payment_enabled, synchronize_order


async def main():
    if not payment_enabled():
        raise SystemExit("WECHATPAY_ENABLED is false; no merchant calls made")
    orders = await database_call(get_payment_store().list_pending_orders, 100)
    from credit_system.subscriptions import issue_due
    credit_months = await database_call(issue_due, get_payment_store())
    completed = 0
    for order in orders:
        try:
            updated = await synchronize_order(order)
            completed += updated["status"] != "PENDING"
        except Exception:
            logging.exception("Payment reconciliation failed for order_id=%s", order["id"])
    print(f"Checked {len(orders)} orders; {completed} reached a final state; {credit_months} monthly credit grants issued.")


if __name__ == "__main__":
    asyncio.run(main())
