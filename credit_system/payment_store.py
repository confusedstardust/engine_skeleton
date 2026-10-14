"""Business orders and credit fulfilment share a single database transaction."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from wechatpay_native.notifications import PaymentTransaction, assert_expected_payment
from .errors import CreditConflictError, CreditNotFoundError, CreditStateError
from .store import MySQLCreditStore, _canonical_json, _json_object, _positive_units, _validate_user_id


class PaymentStore(MySQLCreditStore):
    def list_products(self) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM products WHERE kind='CREDIT_PACK' AND status='ACTIVE' AND currency='CNY' ORDER BY price_fen,id")
            return [self.product_view(row) for row in cursor.fetchall()]

    def is_payment_tester(self, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT is_tester FROM users WHERE id=%s", (_validate_user_id(user_id),))
            row = cursor.fetchone()
            return bool(row and row["is_tester"])

    def private_test_product(self):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM products WHERE sku='forge-private-payment-test-v1' AND status='DRAFT' AND kind='CREDIT_PACK' AND currency='CNY'")
            row = cursor.fetchone()
            if row is None or int(row["price_fen"]) != 10 or int(_json_object(row["benefit_json"]).get("credits", 0)) != 1:
                raise CreditNotFoundError("测试档位未配置")
            return self.product_view(row)

    def private_test_evidence(self, order_id, user_id):
        with self._transaction() as cursor:
            order = self._order_locked(cursor, order_id, user_id)
            if _json_object(order["product_snapshot"]).get("sku") != "forge-private-payment-test-v1":
                raise CreditNotFoundError("测试订单不存在")
            cursor.execute("SELECT COUNT(*) AS n FROM payment_notifications WHERE payment_attempt_id=%s AND status='PROCESSED'", (order["attempt"]["id"],))
            callbacks = int(cursor.fetchone()["n"])
            cursor.execute("SELECT COALESCE(SUM(units_granted),0) AS units FROM entitlement_grants WHERE order_id=%s AND benefit_key='credits'", (order_id,))
            units = int(cursor.fetchone()["units"])
            cursor.execute("SELECT COUNT(*) AS n FROM credit_ledger l JOIN entitlement_grants g ON g.id=l.grant_id WHERE g.order_id=%s AND l.action='GRANT'", (order_id,))
            ledger = int(cursor.fetchone()["n"])
            return {"payment_status": order["attempt"]["status"], "fulfillment_status": order["fulfillment_status"],
                    "verified_callback": callbacks > 0, "granted_credits": units, "grant_ledger_entries": ledger}

    @staticmethod
    def product_view(row):
        benefit = _json_object(row["benefit_json"])
        credits = _positive_units(benefit.get("credits"))
        price = _positive_units(int(row["price_fen"]))
        return {"id": row["id"], "name": row["name"], "credits": credits, "price_fen": price,
                "audience": benefit.get("audience", ""), "features": benefit.get("features", []),
                "billing_period": benefit.get("billing_period", "once")}

    @staticmethod
    def _active_subscription(rows, now=None):
        from .subscriptions import anniversary
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        for row in rows:
            snapshot = _json_object(row["product_snapshot"])
            benefit = _json_object(snapshot.get("benefit"))
            period = benefit.get("billing_period")
            if snapshot.get("name") not in {"Creator", "Pro"} or period not in {"month", "year"}:
                continue
            start = row["paid_at"]
            if not isinstance(start, datetime):
                continue
            end = anniversary(start, 12 if period == "year" else 1)
            if start <= now < end:
                return {"name": snapshot["name"], "billing_period": period,
                        "expires_at": end.replace(tzinfo=timezone.utc).isoformat()}
        return None

    def _subscription_locked(self, cursor, user_id):
        cursor.execute("SELECT * FROM user_subscription_overrides WHERE user_id=%s", (user_id,))
        override = cursor.fetchone()
        cursor.execute("""SELECT product_snapshot,paid_at FROM purchase_orders
            WHERE user_id=%s AND status='PAID' AND fulfillment_status='FULFILLED'
            ORDER BY paid_at DESC""", (user_id,))
        rows = cursor.fetchall()
        if override:
            # A later successful purchase supersedes an earlier manual assignment.
            newer = self._active_subscription([row for row in rows if row["paid_at"] and row["paid_at"] > override["updated_at"]])
            if newer:
                return newer
            if override["plan"] != "Free" and override["expires_at"] and override["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None):
                return {"name": override["plan"], "billing_period": "manual",
                        "expires_at": override["expires_at"].replace(tzinfo=timezone.utc).isoformat()}
            return None
        return self._active_subscription(rows)

    def get_subscription(self, user_id):
        with self._transaction() as cursor:
            return self._subscription_locked(cursor, _validate_user_id(user_id))

    def create_order(self, *, user_id: str, product_id: str, request_key: str, merchant_id: str, app_id: str, private_test: bool = False):
        user_id = _validate_user_id(user_id)
        request_hash = hashlib.sha256(product_id.encode()).hexdigest()
        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
            if cursor.fetchone() is None:
                raise CreditNotFoundError("User not found")
            cursor.execute("SELECT * FROM purchase_orders WHERE user_id=%s AND request_key=%s FOR UPDATE", (user_id, request_key))
            existing = cursor.fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise CreditConflictError("请求已用于其他充值档位")
                return self._order_locked(cursor, existing["id"], user_id)
            # One live checkout per account; a refresh or second tab resumes it.
            cursor.execute("SELECT id FROM purchase_orders WHERE user_id=%s AND status='PENDING' ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (user_id,))
            pending = cursor.fetchone()
            if pending:
                raise CreditConflictError("请先在充值记录中继续支付或关闭未完成订单")
            cursor.execute("SELECT * FROM products WHERE id=%s AND kind='CREDIT_PACK' AND status IN ('ACTIVE','DRAFT') AND currency='CNY' FOR UPDATE", (product_id,))
            product = cursor.fetchone()
            if product is None:
                raise CreditNotFoundError("充值档位不存在或已下架")
            test_product = product["sku"] == "forge-private-payment-test-v1"
            if private_test:
                if not test_product or product["status"] != "DRAFT" or int(product["price_fen"]) != 10 or int(_json_object(product["benefit_json"]).get("credits", 0)) != 1:
                    raise CreditNotFoundError("测试档位不可用")
            elif test_product or product["status"] != "ACTIVE":
                raise CreditNotFoundError("充值档位不存在或已下架")
            benefit = _json_object(product["benefit_json"])
            if product["name"] in {"Creator", "Pro"} and benefit.get("billing_period") in {"month", "year"}:
                # The user row is already locked: concurrent purchases cannot bypass this check.
                if self._subscription_locked(cursor, user_id):
                    raise CreditConflictError("当前订阅仍在有效期内，请勿重复购买；可购买资源包补充积分")
            view = self.product_view(product)
            order_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
            expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
            snapshot = {"kind": "CREDIT_PACK", "name": product["name"], "sku": product["sku"], "revision": product["revision"], "price_fen": view["price_fen"], "benefit": _json_object(product["benefit_json"])}
            cursor.execute("""INSERT INTO purchase_orders
                (id,order_no,user_id,product_id,product_snapshot,total_fen,payable_fen,request_key,request_hash,expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (order_id, order_id, user_id, product_id, _canonical_json(snapshot), view["price_fen"], view["price_fen"], request_key, request_hash, expires))
            cursor.execute("""INSERT INTO payment_attempts
                (id,order_id,channel,merchant_id,app_id,out_trade_no,expected_fen,expires_at)
                VALUES (%s,%s,'WECHAT_NATIVE',%s,%s,%s,%s,%s)""",
                (attempt_id, order_id, merchant_id, app_id, order_id, view["price_fen"], expires))
            return self._order_locked(cursor, order_id, user_id)

    def _order_locked(self, cursor, order_id, user_id=None):
        cursor.execute("SELECT * FROM purchase_orders WHERE id=%s", (order_id,))
        order = cursor.fetchone()
        if order is None or (user_id is not None and order["user_id"] != user_id):
            raise CreditNotFoundError("充值订单不存在")
        cursor.execute("SELECT * FROM payment_attempts WHERE order_id=%s ORDER BY created_at DESC LIMIT 1", (order_id,))
        attempt = cursor.fetchone()
        if not attempt:
            raise CreditStateError("Payment attempt missing")
        return {**order, "attempt": attempt}

    def get_order(self, order_id, user_id=None):
        with self._transaction() as cursor:
            return self._order_locked(cursor, order_id, user_id)

    def list_orders(self, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM purchase_orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (user_id,))
            return [self._order_locked(cursor, row["id"], user_id) for row in cursor.fetchall()]

    def list_pending_orders(self, limit=100):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self._transaction() as cursor:
            cursor.execute("""SELECT o.id FROM purchase_orders o JOIN payment_attempts p ON p.order_id=o.id
                WHERE o.status='PENDING' AND (p.next_query_at IS NULL OR p.next_query_at<=CURRENT_TIMESTAMP(3))
                ORDER BY COALESCE(p.last_queried_at,o.created_at),o.id LIMIT %s""", (limit,))
            return [self._order_locked(cursor, row["id"]) for row in cursor.fetchall()]

    def save_code_url(self, order_id, code_url):
        with self._transaction() as cursor:
            cursor.execute("UPDATE payment_attempts SET code_url=%s,status='PENDING' WHERE order_id=%s AND status IN ('CREATING','UNKNOWN')", (code_url, order_id))

    def mark_unknown(self, order_id):
        with self._transaction() as cursor:
            cursor.execute("UPDATE payment_attempts SET status='UNKNOWN' WHERE order_id=%s AND status='CREATING'", (order_id,))

    def claim_query(self, order_id):
        with self._transaction() as cursor:
            cursor.execute("""UPDATE payment_attempts SET last_queried_at=CURRENT_TIMESTAMP(3),
                next_query_at=DATE_ADD(CURRENT_TIMESTAMP(3), INTERVAL 5 SECOND)
                WHERE order_id=%s AND status IN ('CREATING','PENDING','UNKNOWN','CLOSING')
                AND (next_query_at IS NULL OR next_query_at<=CURRENT_TIMESTAMP(3))""", (order_id,))
            return cursor.rowcount > 0

    def close_order(self, order_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM purchase_orders WHERE id=%s AND status='PENDING' FOR UPDATE", (order_id,))
            if cursor.fetchone() is None:
                return
            cursor.execute("UPDATE payment_attempts SET status='CLOSED',closed_at=CURRENT_TIMESTAMP(3) WHERE order_id=%s AND status<>'SUCCESS'", (order_id,))
            cursor.execute("UPDATE purchase_orders SET status='CLOSED',closed_at=CURRENT_TIMESTAMP(3),lock_version=lock_version+1 WHERE id=%s", (order_id,))

    def confirm_payment(self, transaction: PaymentTransaction, *, notification_id=None, body_sha256=None):
        order_id = transaction.out_trade_no
        order = self.get_order(order_id)
        with self._transaction() as cursor:
            cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (order["user_id"],))
            cursor.execute("SELECT * FROM purchase_orders WHERE id=%s FOR UPDATE", (order_id,))
            order = cursor.fetchone()
            cursor.execute("SELECT * FROM payment_attempts WHERE order_id=%s FOR UPDATE", (order_id,))
            attempt = cursor.fetchone()
            assert_expected_payment(transaction, expected_out_trade_no=attempt["out_trade_no"], expected_total=int(order["payable_fen"]), expected_currency=order["currency"])
            if transaction.mchid != attempt["merchant_id"] or transaction.appid != attempt["app_id"]:
                raise CreditConflictError("Payment merchant does not match the saved order")
            if attempt["transaction_id"] and attempt["transaction_id"] != transaction.transaction_id:
                raise CreditConflictError("Order already has another transaction")
            if order["status"] not in ("PENDING", "PAID", "CLOSED"):
                raise CreditStateError("Refunded orders cannot be fulfilled again")
            if int(attempt["expected_fen"]) != transaction.total:
                raise CreditConflictError("Attempt amount mismatch")
            cursor.execute("""UPDATE payment_attempts SET status='SUCCESS',transaction_id=%s,
                paid_total_fen=%s,payer_total_fen=%s,paid_at=%s WHERE id=%s""",
                (transaction.transaction_id, transaction.total, transaction.payer_total,
                 datetime.fromisoformat(transaction.success_time).astimezone(timezone.utc).replace(tzinfo=None), attempt["id"]))
            cursor.execute("""UPDATE purchase_orders SET status='PAID',paid_attempt_id=%s,
                paid_at=%s,lock_version=lock_version+1 WHERE id=%s""",
                (attempt["id"], datetime.fromisoformat(transaction.success_time).astimezone(timezone.utc).replace(tzinfo=None), order_id))
            self._grant_order_locked(cursor, order_id=order_id)
            if notification_id:
                cursor.execute("SELECT * FROM payment_notifications WHERE channel='WECHAT_NATIVE' AND merchant_id=%s AND notification_id=%s FOR UPDATE", (transaction.mchid, notification_id))
                existing = cursor.fetchone()
                if existing:
                    if existing["body_sha256"] != body_sha256 or existing["payment_attempt_id"] != attempt["id"]:
                        raise CreditConflictError("Notification ID reused with different content")
                    cursor.execute("UPDATE payment_notifications SET receive_count=receive_count+1,last_received_at=CURRENT_TIMESTAMP(3) WHERE id=%s", (existing["id"],))
                else:
                    cursor.execute("""INSERT INTO payment_notifications
                        (id,channel,merchant_id,notification_id,event_type,payment_attempt_id,resource_no,body_sha256,status,processed_at)
                        VALUES (%s,'WECHAT_NATIVE',%s,%s,'TRANSACTION.SUCCESS',%s,%s,%s,'PROCESSED',CURRENT_TIMESTAMP(3))""",
                        (uuid.uuid4().hex, transaction.mchid, notification_id, attempt["id"], order_id, body_sha256))
