from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

import webgal_backend.app as backend_app
import webgal_backend.payments as payments
from credit_system.errors import CreditNotFoundError
from wechatpay_native.errors import PaymentValidationError
from test_wechatpay_native import key_material, _notification


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WECHATPAY_ENABLED", "true")
    monkeypatch.setattr(payments, "user_from_request", lambda *_: {"id":"user-1", "auth_type":"sso"})
    return TestClient(backend_app.app)


def test_disabled_recharge_does_not_call_merchant(client, monkeypatch):
    monkeypatch.setenv("WECHATPAY_ENABLED", "false")
    monkeypatch.setattr(payments, "get_payment_service", lambda: pytest.fail("must not call merchant"))
    assert client.get("/payments/products").json() == {"enabled":False,"products":[]}
    assert client.post("/payments/orders", json={"product_id":"a"*32,"request_key":"request-key-123456"}).status_code == 503


def test_invite_user_cannot_recharge(client, monkeypatch):
    monkeypatch.setattr(payments, "user_from_request", lambda *_: {"id":"invite-user", "auth_type":"invite"})
    assert client.get("/payments/products").status_code == 403


def test_browser_cannot_submit_price_credits_or_cross_site_request(client):
    payload={"product_id":"a"*32,"request_key":"request-key-123456"}
    assert client.post("/payments/orders",json={**payload,"total_fen":1,"credits":100000}).status_code == 422
    assert client.post("/payments/orders",json=payload,headers={"Origin":"https://evil.example"}).status_code == 403


def test_foreign_order_is_hidden(client, monkeypatch):
    def get_order(*_): raise CreditNotFoundError("充值订单不存在")
    monkeypatch.setattr(payments, "get_payment_store", lambda: SimpleNamespace(get_order=get_order))
    assert client.get("/payments/orders/"+"a"*32).status_code == 404
    assert client.get("/payments/orders/"+"a"*32+"/qr").status_code == 404


def test_qr_is_generated_locally_and_never_publicly_cached(client, monkeypatch):
    order={"status":"PENDING","expires_at":datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=5),
           "attempt":{"code_url":"weixin://local-test-only"}}
    monkeypatch.setattr(payments,"get_payment_store",lambda:SimpleNamespace(get_order=lambda *_:order))
    response=client.get("/payments/orders/"+"a"*32+"/qr")
    assert response.status_code==200
    assert response.content.startswith(b"\x89PNG")
    assert response.headers["cache-control"]=="private, no-store"


def test_only_verified_callback_reaches_fulfillment(client, monkeypatch, key_material):
    config, _, private_key = key_material
    headers, body = _notification(config, private_key)
    calls=[]
    monkeypatch.setattr(payments, "get_payment_service", lambda: SimpleNamespace(config=config))
    monkeypatch.setattr(payments, "get_payment_store", lambda: SimpleNamespace(confirm_payment=lambda *a,**kw:calls.append((a,kw))))
    assert client.post("/payments/wechat/notify",content=body+b" ",headers=headers).status_code == 400
    assert calls == []
    assert client.post("/payments/wechat/notify",content=body,headers=headers).status_code == 204
    assert len(calls) == 1
    assert calls[0][0][0].transaction_id == "4200000000000000001"
    assert calls[0][1]["notification_id"] == "EV-TEST-0001"


def test_callback_amount_mismatch_is_rejected(client, monkeypatch, key_material):
    config, _, private_key = key_material
    headers, body = _notification(config, private_key)
    def confirm(*_,**__): raise PaymentValidationError("amount mismatch")
    monkeypatch.setattr(payments, "get_payment_service", lambda: SimpleNamespace(config=config))
    monkeypatch.setattr(payments, "get_payment_store", lambda: SimpleNamespace(confirm_payment=confirm))
    assert client.post("/payments/wechat/notify",content=body,headers=headers).status_code == 400


def test_oversized_callback_is_rejected_before_key_loading(client, monkeypatch):
    monkeypatch.setattr(payments,"get_payment_service",lambda:pytest.fail("must reject body first"))
    assert client.post("/payments/wechat/notify",content=b"x"*(1024*1024+1)).status_code==413


def test_signed_query_recovers_success_without_callback(client, monkeypatch):
    order={"id":"a"*32,"user_id":"user-1","product_snapshot":{"name":"充值","benefit":{"credits":100}},"quantity":1,
        "payable_fen":1000,"status":"PENDING","fulfillment_status":"PENDING","expires_at":datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=10),
        "attempt":{"out_trade_no":"a"*32,"code_url":"weixin://test","status":"PENDING"}}
    calls=[]
    def confirm(tx):
        calls.append(tx)
        order.update(status="PAID",fulfillment_status="FULFILLED")
    async def query(_):
        return {"appid":"wx123","mchid":"1900000001","out_trade_no":"a"*32,"transaction_id":"wx-1","trade_type":"NATIVE","trade_state":"SUCCESS",
                "amount":{"total":1000,"payer_total":1000,"currency":"CNY","payer_currency":"CNY"},"success_time":datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(payments,"get_payment_store",lambda:SimpleNamespace(get_order=lambda *_:order,claim_query=lambda *_:True,confirm_payment=confirm))
    monkeypatch.setattr(payments,"get_payment_service",lambda:SimpleNamespace(config=SimpleNamespace(appid="wx123",mchid="1900000001"),query_payment=query))
    response=client.get("/payments/orders/"+"a"*32)
    assert response.status_code == 200
    assert response.json()["fulfillment_status"] == "FULFILLED"
    assert len(calls)==1


def test_slow_payment_auth_does_not_block_other_requests(monkeypatch):
    import asyncio
    import threading
    import httpx
    from fastapi import FastAPI

    entered = threading.Event()
    release = threading.Event()

    def slow_auth(*_):
        entered.set()
        assert release.wait(5), "test did not release auth"
        return {"id": "user-1", "auth_type": "sso"}

    monkeypatch.setattr(payments, "user_from_request", slow_auth)
    monkeypatch.setenv("WECHATPAY_ENABLED", "false")
    app = FastAPI()
    app.include_router(payments.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            catalog = asyncio.create_task(client.get("/payments/products"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                response = await asyncio.wait_for(client.get("/ping"), 1)
                assert response.json() == {"ok": True}
            finally:
                release.set()
                response = await catalog
            assert response.status_code == 200

    asyncio.run(check())
