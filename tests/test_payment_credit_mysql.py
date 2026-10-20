"""Opt-in integration checks using session-local MySQL TEMPORARY tables only.

Set CREDIT_MYSQL_TEST=1. No persistent tables/data or merchant APIs are changed.
"""
from __future__ import annotations

import os
import re
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from credit_system.errors import CreditConflictError, CreditNotFoundError, InsufficientCreditsError
from credit_system.payment_store import PaymentStore
from wechatpay_native.errors import PaymentValidationError
from wechatpay_native.notifications import PaymentTransaction

pytestmark = pytest.mark.skipif(os.getenv("CREDIT_MYSQL_TEST") != "1", reason="Requires MySQL; uses temporary tables only")


@pytest.fixture
def billing():
    import pymysql
    from pymysql.cursors import DictCursor
    from webgal_backend.config import settings  # Load local configuration, never print it.
    from credit_system.config import CreditDatabaseConfig

    connection = pymysql.connect(cursorclass=DictCursor, **CreditDatabaseConfig.from_env().connect_kwargs())
    tables = ["products", "purchase_orders", "payment_attempts", "payment_notifications",
              "entitlement_grants", "credit_reservations", "credit_allocations", "credit_ledger", "subscription_credit_schedules", "user_subscription_overrides"]
    with connection.cursor() as cursor:
        schemas = {}
        for table in tables:
            cursor.execute("SHOW CREATE TABLE " + table)
            ddl = cursor.fetchone()["Create Table"]
            ddl = ddl.replace("CREATE TABLE", "CREATE TEMPORARY TABLE", 1)
            ddl = "\n".join(line for line in ddl.splitlines() if "CONSTRAINT " not in line)
            ddl = re.sub(r",\n\) ENGINE", "\n) ENGINE", ddl)
            ddl = ddl.replace("`units_available` bigint unsigned", "`units_available` bigint")
            ddl = ddl.replace("`available_after` bigint unsigned", "`available_after` bigint")
            ddl = ddl.replace("enum('ORDER','PROMOTION','ADMIN')", "enum('ORDER','PROMOTION','ADMIN','CREDIT_LINE')")
            schemas[table] = ddl
        cursor.execute("CREATE TEMPORARY TABLE users (id varchar(191) PRIMARY KEY,is_tester tinyint(1) NOT NULL DEFAULT 0)")
        cursor.execute("CREATE TEMPORARY TABLE generation_jobs (id char(32) PRIMARY KEY, owner_user_id varchar(191))")
        for ddl in schemas.values():
            cursor.execute(ddl)
        cursor.execute("INSERT INTO users (id) VALUES ('test-user')")
        cursor.execute("INSERT INTO generation_jobs VALUES (%s,'test-user'),(%s,'test-user')", ("a"*32, "b"*32))
        cursor.execute("INSERT INTO generation_jobs VALUES (%s,'test-user')", ("d"*32,))
        cursor.execute("""INSERT INTO products (id,sku,name,kind,status,price_fen,benefit_json)
            VALUES (%s,'integration-test','测试充值','CREDIT_PACK','ACTIVE',1000,'{"credits":100}')""", ("c"*32,))
    connection.commit()

    class SessionConnection:
        def begin(self): connection.begin()
        def cursor(self): return connection.cursor()
        def commit(self): connection.commit()
        def rollback(self): connection.rollback()
        def close(self): pass  # Keep temp tables for the test, destroy at fixture teardown.

    try:
        yield PaymentStore(lambda: SessionConnection()), connection
    finally:
        connection.close()


def reserve(store, units, operation="first", job="a"*32):
    return store.reserve(user_id="test-user", job_id=job, operation_key=operation, units=units, pricing_snapshot={"hold":units})


def seed_balance(store, connection, available):
    store.ensure_signup_grant("test-user")
    # Set up an isolated fixture, never an application balance mutation.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE entitlement_grants SET units_available=%s,units_consumed=%s WHERE source='PROMOTION'", (available, 200-available))
    connection.commit()


@pytest.mark.parametrize("available,units,allowed", [(10,20,True),(0,15,True),(0,16,False),(10,25,True),(10,26,False)])
def test_exact_overdraft_boundary(billing, available, units, allowed):
    store, connection = billing
    seed_balance(store, connection, available)
    if not allowed:
        with pytest.raises(InsufficientCreditsError): reserve(store, units)
        assert store.get_balance("test-user").available == available
        return
    result = reserve(store, units)
    assert store.get_balance("test-user").available == available-units
    store.release(result.reservation_id)
    assert store.get_balance("test-user").available == available


def test_shared_debt_budget_across_jobs_and_partial_settlement(billing):
    store, connection = billing
    seed_balance(store, connection, 10)
    result = reserve(store, 20)
    assert reserve(store, 20).created is False
    second = reserve(store, 5, "second", "b"*32)
    assert store.get_balance("test-user").available == -15
    with pytest.raises(InsufficientCreditsError): reserve(store, 1, "third", "d"*32)
    store.capture(result.reservation_id, units=12)
    store.capture(result.reservation_id, units=12)  # Duplicate settlement.
    assert store.get_balance("test-user").available == -7
    store.release(second.reservation_id)
    assert store.get_balance("test-user").available == -2
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM entitlement_grants WHERE units_granted<>units_available+CAST(units_reserved AS SIGNED)+CAST(units_consumed AS SIGNED)+CAST(units_revoked AS SIGNED)")
        assert cursor.fetchone()["n"] == 0


def make_order(store, key="request-key-123456"):
    return store.create_order(user_id="test-user", product_id="c"*32, request_key=key, merchant_id="1900000001", app_id="wx123")


def transaction_for(order):
    return PaymentTransaction(appid="wx123", mchid="1900000001", out_trade_no=order["id"], transaction_id="wx-transaction-1",
        trade_type="NATIVE", trade_state="SUCCESS", total=1000, payer_total=900, currency="CNY", payer_currency="CNY",
        success_time=datetime.now(timezone.utc).isoformat(), raw={})


def test_paid_recharge_offsets_debt_and_duplicate_notify_query_do_not_double_grant(billing):
    store, connection = billing
    seed_balance(store, connection, 10)
    reserved = reserve(store, 20)
    store.capture(reserved.reservation_id)
    order = make_order(store)
    assert make_order(store)["id"] == order["id"]
    with pytest.raises(CreditConflictError): make_order(store, "another-key-123456")
    with pytest.raises(CreditNotFoundError): store.get_order(order["id"], "another-user")
    tx = transaction_for(order)
    store.confirm_payment(tx, notification_id="notification-1", body_sha256="d"*64)
    store.confirm_payment(tx, notification_id="notification-1", body_sha256="d"*64)
    store.confirm_payment(tx)  # Active query after successful callback.
    assert store.get_balance("test-user").available == 90
    assert store.get_order(order["id"])["fulfillment_status"] == "FULFILLED"
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM entitlement_grants WHERE source='ORDER'")
        assert cursor.fetchone()["n"] == 1
        cursor.execute("SELECT receive_count FROM payment_notifications")
        assert cursor.fetchone()["receive_count"] == 2


def test_tampered_amount_and_conflicting_transaction_roll_back(billing):
    store, connection = billing
    order = make_order(store)
    tx = transaction_for(order)
    with pytest.raises(PaymentValidationError): store.confirm_payment(replace(tx, total=1))
    assert store.get_order(order["id"])["status"] == "PENDING"
    assert store.get_balance("test-user").available == 0
    store.confirm_payment(tx, notification_id="n1", body_sha256="d"*64)
    with pytest.raises(CreditConflictError): store.confirm_payment(replace(tx, transaction_id="different"))
    with pytest.raises(CreditConflictError): store.confirm_payment(tx, notification_id="n1", body_sha256="e"*64)
    assert store.get_balance("test-user").available == 100


def test_closed_order_can_recover_authentic_late_payment(billing):
    store, _ = billing
    order = make_order(store)
    store.close_order(order["id"])
    store.confirm_payment(transaction_for(order))
    assert store.get_order(order["id"])["fulfillment_status"] == "FULFILLED"
    assert store.get_balance("test-user").available == 100


def test_fulfillment_failure_rolls_back_payment_order_and_grant_together(billing, monkeypatch):
    store, _ = billing
    order = make_order(store)
    def fail_ledger(*args, **kwargs):
        raise RuntimeError("Injected ledger failure")
    with monkeypatch.context() as patch:
        patch.setattr(store,"_insert_ledger",fail_ledger)
        with pytest.raises(RuntimeError,match="Injected ledger failure"):
            store.confirm_payment(transaction_for(order))
    current=store.get_order(order["id"])
    assert current["status"]=="PENDING"
    assert current["attempt"]["transaction_id"] is None
    assert store.get_balance("test-user").available==0
    store.confirm_payment(transaction_for(order))
    assert store.get_balance("test-user").available==100


def test_annual_purchase_delivers_monthly_with_recovery_and_no_duplicates(billing, monkeypatch):
    from credit_system.subscriptions import issue_for_user, anniversary
    store, connection = billing
    with connection.cursor() as cursor:
        cursor.execute("""UPDATE products SET benefit_json='{"credits":100,"billing_period":"year",
            "credit_delivery":"monthly","subscription_months":12}' WHERE id=%s""", ("c"*32,))
    connection.commit()
    order = make_order(store)
    store.confirm_payment(transaction_for(order))
    store.confirm_payment(transaction_for(order))
    assert store.get_balance("test-user").available == 100  # Never issue 1200 upfront.
    start = datetime(2030,1,31,9,30)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE subscription_credit_schedules SET starts_at=%s,next_issue_at=%s WHERE order_id=%s",
                       (start,anniversary(start,1),order["id"]))
    connection.commit()
    assert anniversary(start,1) == datetime(2030,2,28,9,30)
    assert anniversary(start,2) == datetime(2030,3,31,9,30)
    assert issue_for_user(store,"test-user",now=datetime(2030,2,28,9,29)) == 0
    assert issue_for_user(store,"test-user",now=anniversary(start,1)) == 1
    assert issue_for_user(store,"test-user",now=anniversary(start,1)) == 0
    with monkeypatch.context() as patch:
        def fail(*args,**kwargs): raise RuntimeError("monthly ledger failure")
        patch.setattr(store,"_insert_ledger",fail)
        with pytest.raises(RuntimeError): issue_for_user(store,"test-user",now=anniversary(start,2))
    assert issue_for_user(store,"test-user",now=anniversary(start,2)) == 1
    with connection.cursor() as cursor:
        cursor.execute("UPDATE purchase_orders SET status='REFUNDED' WHERE id=%s", (order["id"],))
    connection.commit()
    assert issue_for_user(store,"test-user",now=anniversary(start,3)) == 0
    with connection.cursor() as cursor:
        cursor.execute("UPDATE purchase_orders SET status='PAID' WHERE id=%s", (order["id"],))
    connection.commit()
    assert issue_for_user(store,"test-user",now=anniversary(start,20)) == 9  # Catch up remaining months.
    assert issue_for_user(store,"test-user",now=anniversary(start,21)) == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n,SUM(units_granted) AS units FROM entitlement_grants WHERE order_id=%s",(order["id"],))
        assert cursor.fetchone() == {"n":12,"units":1200}
        cursor.execute("SELECT issued_cycles,next_issue_at FROM subscription_credit_schedules WHERE order_id=%s",(order["id"],))
        assert cursor.fetchone() == {"issued_cycles":12,"next_issue_at":None}


def test_subscription_blocks_repeat_but_allows_resource_pack(billing):
    import json
    store, connection = billing
    with connection.cursor() as cursor:
        cursor.execute("UPDATE products SET name='Creator',benefit_json=%s WHERE id=%s",
                       (json.dumps({"credits": 600, "billing_period": "month"}), "c"*32))
    connection.commit()
    args = dict(user_id="test-user", product_id="c"*32, merchant_id="merchant", app_id="app")
    first = store.create_order(**args, request_key="first-subscription")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE purchase_orders SET status='PAID',fulfillment_status='FULFILLED',paid_at=UTC_TIMESTAMP() WHERE id=%s", (first["id"],))
        cursor.execute("""INSERT INTO products (id,sku,name,kind,status,price_fen,benefit_json)
            VALUES (%s,'resource-test','体验积分包','CREDIT_PACK','ACTIVE',1690,%s)""",
            ("e"*32, json.dumps({"credits": 100, "billing_period": "once"})))
    connection.commit()
    assert store.get_subscription("test-user")["name"] == "Creator"
    with pytest.raises(CreditConflictError, match="当前订阅"):
        store.create_order(**args, request_key="second-subscription")
    resource = store.create_order(**{**args, "product_id": "e"*32}, request_key="resource-allowed")
    assert resource["status"] == "PENDING"
    store.close_order(resource["id"])
    with connection.cursor() as cursor:
        cursor.execute("UPDATE purchase_orders SET paid_at=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 MONTH) WHERE id=%s", (first["id"],))
    connection.commit()
    assert store.get_subscription("test-user") is None
    assert store.create_order(**args, request_key="after-expiry")["status"] == "PENDING"


def test_manual_subscription_overrides_access_and_expiry(billing):
    store, connection = billing
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO user_subscription_overrides
            (user_id,plan,expires_at,actor_user_id,reason) VALUES
            ('test-user','School',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 MONTH),'admin','test authorization')""")
    connection.commit()
    assert store.get_subscription('test-user')['name'] == 'School'
    with connection.cursor() as cursor:
        cursor.execute("UPDATE products SET name='Creator',benefit_json='{\"credits\":600,\"billing_period\":\"month\"}' WHERE id=%s", ('c'*32,))
    connection.commit()
    with pytest.raises(CreditConflictError):
        store.create_order(user_id='test-user',product_id='c'*32,request_key='manual-block',merchant_id='merchant',app_id='app')
    with connection.cursor() as cursor:
        cursor.execute("UPDATE user_subscription_overrides SET plan='Free',expires_at=NULL WHERE user_id='test-user'")
    connection.commit()
    assert store.get_subscription('test-user') is None


def test_admin_subscription_save_audit_and_revision(billing, monkeypatch):
    from types import SimpleNamespace
    from datetime import timedelta
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import webgal_backend.platform_admin as admin
    import webgal_backend.payments as payments
    store, connection = billing
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE users ADD email varchar(191), ADD nickname varchar(191), ADD created_at datetime DEFAULT CURRENT_TIMESTAMP")
        cursor.execute("CREATE TEMPORARY TABLE platform_admin_audit (id varchar(32),actor_user_id varchar(191),resource_type varchar(20),resource_id varchar(191),action varchar(50),before_json json,after_json json)")
    connection.commit()
    monkeypatch.setattr(admin, 'database_transaction', store.transaction)
    monkeypatch.setattr(admin, 'require_admin', lambda _: {'id':'admin'})
    monkeypatch.setattr(payments, 'get_payment_store', lambda: store)
    app = FastAPI(); app.include_router(admin.router)
    client = TestClient(app)
    payload = {'plan':'Pro', 'expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(), 'reason':'Support adjustment', 'expected_revision':0}
    response = client.patch('/admin/users/test-user/subscription', json=payload, headers={'x-forge-admin-action':'1'})
    assert response.status_code == 200, response.text
    assert response.json()['subscription']['name'] == 'Pro'
    assert response.json()['revision'] == 1
    assert store.get_subscription('test-user')['name'] == 'Pro'
    assert client.patch('/admin/users/test-user/subscription',json=payload,headers={'x-forge-admin-action':'1'}).status_code == 409
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS n FROM platform_admin_audit')
        assert cursor.fetchone()['n'] == 1


def test_private_test_product_hidden_and_normal_checkout_rejected(billing):
    import json
    store,connection=billing
    with connection.cursor() as cursor:
        cursor.execute("UPDATE products SET sku='forge-private-payment-test-v1',status='DRAFT',price_fen=10,benefit_json=%s WHERE id=%s",(json.dumps({'credits':1,'billing_period':'once'}),'c'*32))
    connection.commit()
    assert store.list_products()==[]
    assert store.private_test_product()['price_fen']==10
    args=dict(user_id='test-user',product_id='c'*32,merchant_id='merchant',app_id='app')
    with pytest.raises(CreditNotFoundError):
        store.create_order(**args,request_key='normal-cannot-test')
    order=store.create_order(**args,request_key='private-owner-test',private_test=True)
    assert order['payable_fen']==10
    report=store.private_test_evidence(order['id'],'test-user')
    assert report['granted_credits']==0 and report['verified_callback'] is False


def test_tester_database_role_revocation(billing):
    store,connection=billing
    assert store.is_payment_tester('test-user') is False
    with connection.cursor() as cursor:
        cursor.execute("UPDATE users SET is_tester=1 WHERE id='test-user'")
    connection.commit()
    assert store.is_payment_tester('test-user') is True
    with connection.cursor() as cursor:
        cursor.execute("UPDATE users SET is_tester=0 WHERE id='test-user'")
    connection.commit()
    assert store.is_payment_tester('test-user') is False
    assert store.is_payment_tester('missing-user') is False
