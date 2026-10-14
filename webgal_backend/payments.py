from __future__ import annotations

import hashlib
import io
import logging
import os
import asyncio
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from credit_system.config import CreditDatabaseConfig
from credit_system.errors import CreditConflictError, CreditNotFoundError, CreditStateError
from credit_system.payment_store import PaymentStore
from credit_system.store import _json_object
from wechatpay_native.errors import PaymentValidationError, SignatureVerificationError, WeChatPayAPIError, WeChatPayError
from wechatpay_native.notifications import MAX_NOTIFICATION_BYTES, parse_payment_notification, parse_successful_transaction
from wechatpay_native.service import NativePaymentService
from .auth import user_from_request
from .config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


def payment_enabled():
    return os.getenv("WECHATPAY_ENABLED", "false").lower() == "true"


@lru_cache(maxsize=1)
def get_payment_store():
    try:
        return PaymentStore.from_config(CreditDatabaseConfig.from_env())
    except Exception as exc:
        logger.exception("Payment database configuration unavailable")
        raise HTTPException(503, "充值服务尚未配置完成") from exc


@lru_cache(maxsize=1)
def get_payment_service():
    try:
        return NativePaymentService.from_env()
    except Exception as exc:
        logger.exception("WeChat Pay configuration unavailable")
        raise HTTPException(503, "充值服务尚未配置完成") from exc


def require_enabled():
    if not payment_enabled():
        raise HTTPException(503, "充值暂未开放")


def payment_user(request: Request):
    user = user_from_request(request, settings.workspace_root)
    if user.get("auth_type") != "sso":
        raise HTTPException(403, "请使用 NarrativeOS 账号登录后充值")
    if request.method == "POST":
        origin = request.headers.get("origin")
        frontend = urlsplit(os.getenv("WEBGAL_FRONTEND_URL", "http://127.0.0.1:3001"))
        allowed = {f"{frontend.scheme}://{frontend.netloc}", str(request.base_url).rstrip("/")}
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin not in allowed):
            raise HTTPException(403, "请从本站发起充值请求")
    return str(user["id"])


def order_view(order):
    attempt = order["attempt"]
    snapshot = _json_object(order["product_snapshot"])
    return {
        "id": order["id"], "name": snapshot["name"],
        "credits": int(_json_object(snapshot["benefit"])["credits"]) * int(order["quantity"]),
        "payable_fen": int(order["payable_fen"]), "status": order["status"],
        "fulfillment_status": order["fulfillment_status"],
        "payment_status": attempt["status"],
        "qr_ready": bool(attempt["code_url"]) and order["status"] == "PENDING",
        "expires_at": order["expires_at"].replace(tzinfo=timezone.utc).isoformat(),
        "billing_period": _json_object(snapshot["benefit"]).get("billing_period", "once"),
        "credit_delivery": _json_object(snapshot["benefit"]).get("credit_delivery", "once"),
    }


async def subscription_credit_worker():
    from credit_system.subscriptions import issue_due
    while True:
        if payment_enabled():
            try:
                issued = await run_in_threadpool(issue_due, get_payment_store())
                if issued:
                    logger.info("Issued %s due subscription credit months", issued)
            except Exception:
                logger.exception("Monthly subscription credit delivery failed; will retry")
        await asyncio.sleep(60)


async def database_call(method, *args, **kwargs):
    try:
        return await run_in_threadpool(method, *args, **kwargs)
    except CreditNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (CreditConflictError, CreditStateError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PaymentValidationError as exc:
        raise HTTPException(400, "支付信息与充值订单不一致") from exc
    except Exception as exc:
        logger.exception("Payment database operation failed")
        raise HTTPException(503, "充值服务暂时不可用，请稍后重试") from exc


@router.get("/products")
async def products(request: Request):
    await run_in_threadpool(payment_user, request)
    if not payment_enabled():
        return {"enabled": False, "products": []}
    try:
        get_payment_service()
        store = get_payment_store()
    except Exception as exc:
        logger.exception("Payment configuration unavailable")
        raise HTTPException(503, "充值服务尚未配置完成") from exc
    return {"enabled": True, "products": await database_call(store.list_products)}


@router.get("/subscription")
async def subscription(request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    return {"subscription": await database_call(get_payment_store().get_subscription, user_id)}


class CreateOrder(BaseModel):
    model_config = {"extra": "forbid"}
    product_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")


@router.post("/orders")
async def create_order(payload: CreateOrder, request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    return await _create_order_for_user(payload, user_id)


async def _create_order_for_user(payload: CreateOrder, user_id: str, *, private_test=False):
    require_enabled()
    service = get_payment_service()
    store = get_payment_store()
    options = {"private_test": True} if private_test else {}
    order = await database_call(store.create_order, user_id=user_id, product_id=payload.product_id,
                                request_key=payload.request_key, merchant_id=service.config.mchid, app_id=service.config.appid, **options)
    attempt = order["attempt"]
    if order["status"] == "PENDING" and not attempt["code_url"]:
        if order["expires_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(409, "订单已超时，请在充值记录中关闭后重试")
        try:
            native = await service.create_payment(out_trade_no=attempt["out_trade_no"],
                description=f"NarrativeOS · {_json_object(order['product_snapshot'])['name']}"[:127],
                total_cents=int(order["payable_fen"]), time_expire=order["expires_at"].replace(tzinfo=timezone.utc))
            await database_call(store.save_code_url, order["id"], native.code_url)
        except WeChatPayError:
            logger.exception("Native order creation uncertain: order_id=%s", order["id"])
            await database_call(store.mark_unknown, order["id"])
            # Keep the durable order visible; never manufacture a fresh payment attempt.
        order = await database_call(store.get_order, order["id"], user_id)
    return order_view(order)


@router.get("/orders")
async def orders(request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    require_enabled()
    return [order_view(order) for order in await database_call(get_payment_store().list_orders, user_id)]


async def synchronize_order(order):
    """Signed query recovers missed callbacks and determines when closing is safe."""
    store, service = get_payment_store(), get_payment_service()
    if order["status"] != "PENDING" or not await database_call(store.claim_query, order["id"]):
        return order
    try:
        result = await service.query_payment(order["attempt"]["out_trade_no"])
        state = result.get("trade_state")
        if state == "SUCCESS":
            transaction = parse_successful_transaction(result, config=service.config)
            await database_call(store.confirm_payment, transaction)
        elif state in ("CLOSED", "REVOKED", "PAYERROR"):
            await database_call(store.close_order, order["id"])
        elif state == "NOTPAY" and order["expires_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
            await service.close_payment(order["attempt"]["out_trade_no"])
            await database_call(store.close_order, order["id"])
    except WeChatPayAPIError as exc:
        if exc.code == "ORDER_NOT_EXIST" and order["expires_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
            await database_call(store.close_order, order["id"])
        else:
            logger.warning("Payment query failed: order_id=%s code=%s", order["id"], exc.code)
    except WeChatPayError:
        logger.exception("Payment query unavailable: order_id=%s", order["id"])
    return await database_call(store.get_order, order["id"])


@router.get("/orders/{order_id}")
async def order_status(order_id: str, request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    require_enabled()
    order = await database_call(get_payment_store().get_order, order_id, user_id)
    return order_view(await synchronize_order(order))


@router.post("/orders/{order_id}/close")
async def close_order(order_id: str, request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    require_enabled()
    store, service = get_payment_store(), get_payment_service()
    order = await database_call(store.get_order, order_id, user_id)
    if order["status"] != "PENDING":
        return order_view(order)
    try:
        result = await service.query_payment(order["attempt"]["out_trade_no"])
        if result.get("trade_state") == "SUCCESS":
            await database_call(store.confirm_payment, parse_successful_transaction(result, config=service.config))
            return order_view(await database_call(store.get_order, order_id, user_id))
        await service.close_payment(order["attempt"]["out_trade_no"])
    except WeChatPayAPIError as exc:
        if exc.code != "ORDER_NOT_EXIST":
            raise HTTPException(503, "关闭订单失败，请刷新支付状态后重试") from exc
        # A creation request may still be in flight. Wait until its expiry before
        # treating ORDER_NOT_EXIST as final, otherwise a late QR could still pay.
        if order["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(409, "订单创建状态待确认，请稍后刷新；到期后可关闭") from exc
    except WeChatPayError as exc:
        raise HTTPException(503, "支付状态待确认，请稍后重试") from exc
    await database_call(store.close_order, order_id)
    return order_view(await database_call(store.get_order, order_id, user_id))


@router.get("/orders/{order_id}/qr")
async def order_qr(order_id: str, request: Request):
    user_id = await run_in_threadpool(payment_user, request)
    require_enabled()
    order = await database_call(get_payment_store().get_order, order_id, user_id)
    if order["status"] != "PENDING" or not order["attempt"]["code_url"] or order["expires_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(409, "支付二维码不可用，请刷新订单")
    def render():
        import qrcode
        image = qrcode.make(order["attempt"]["code_url"])
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    return Response(await run_in_threadpool(render), media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.post("/wechat/notify")
async def wechat_notify(request: Request):
    require_enabled()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_NOTIFICATION_BYTES:
            raise HTTPException(413, "Notification too large")
    try:
        notification = await run_in_threadpool(parse_payment_notification, headers=request.headers,
                                               body=bytes(body), config=get_payment_service().config)
        await database_call(get_payment_store().confirm_payment, notification.transaction,
            notification_id=notification.notification_id, body_sha256=hashlib.sha256(body).hexdigest())
    except (PaymentValidationError, SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid payment notification") from exc
    return Response(status_code=204)


async def private_test_user(request: Request):
    try:
        user_id = await run_in_threadpool(payment_user, request)
    except HTTPException:
        raise HTTPException(404, "页面不存在")
    if not await database_call(get_payment_store().is_payment_tester, user_id):
        raise HTTPException(404, "页面不存在")
    return user_id


class PrivateTestOrder(BaseModel):
    model_config = {"extra": "forbid"}
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")


@router.get("/test/products")
async def private_test_products(request: Request):
    await private_test_user(request)
    require_enabled()
    get_payment_service()
    product = await database_call(get_payment_store().private_test_product)
    return {"product": product}


@router.post("/test/orders")
async def private_test_order(payload: PrivateTestOrder, request: Request):
    user_id = await private_test_user(request)
    product = await database_call(get_payment_store().private_test_product)
    return await _create_order_for_user(CreateOrder(product_id=product["id"], request_key=payload.request_key), user_id, private_test=True)


@router.get("/test/orders/{order_id}/verification")
async def private_test_verification(order_id: str, request: Request):
    user_id = await private_test_user(request)
    return await database_call(get_payment_store().private_test_evidence, order_id, user_id)
