from __future__ import annotations

import base64
import asyncio
import json
import re
import time
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from wechatpay_native import (
    NativeOrder,
    NativePaymentService,
    PaymentValidationError,
    SignatureVerificationError,
    WeChatPayClient,
    WeChatPayConfig,
    assert_expected_payment,
)
from wechatpay_native.crypto import load_wechatpay_public_key


def _write_key_pair(tmp_path: Path, stem: str) -> tuple[Path, Path, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / f"{stem}_private.pem"
    public_path = tmp_path / f"{stem}_public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path, private_key


@pytest.fixture
def key_material(tmp_path: Path):
    merchant_private_path, _, merchant_private_key = _write_key_pair(tmp_path, "merchant")
    _, wechat_public_path, wechat_private_key = _write_key_pair(tmp_path, "wechat")
    config = WeChatPayConfig(
        mchid="1900000001",
        appid="wx1234567890abcdef",
        merchant_serial_no="ABCDEF123456",
        merchant_private_key_path=merchant_private_path,
        api_v3_key=b"0123456789abcdef0123456789abcdef",
        wechatpay_public_key_id="PUB_KEY_ID_3000000001",
        wechatpay_public_key_path=wechat_public_path,
        notify_url="https://pay.example.com/wechat/notify",
    )
    return config, merchant_private_key, wechat_private_key


def _signed_headers(private_key: rsa.RSAPrivateKey, body: bytes, *, serial: str, timestamp: int | None = None):
    timestamp_text = str(int(time.time()) if timestamp is None else timestamp)
    nonce = "test-nonce"
    message = f"{timestamp_text}\n{nonce}\n".encode() + body + b"\n"
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return {
        "Wechatpay-Serial": serial,
        "Wechatpay-Timestamp": timestamp_text,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Signature": base64.b64encode(signature).decode(),
    }


def test_native_order_signs_request_and_verifies_response(key_material):
    config, merchant_private_key, wechat_private_key = key_material

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        auth = request.headers["Authorization"]
        fields = dict(re.findall(r'(\w+)="([^"]+)"', auth))
        message = (
            f"POST\n/v3/pay/transactions/native\n{fields['timestamp']}\n{fields['nonce_str']}\n".encode()
            + body
            + b"\n"
        )
        merchant_private_key.public_key().verify(
            base64.b64decode(fields["signature"]), message, padding.PKCS1v15(), hashes.SHA256()
        )
        payload = json.loads(body)
        assert payload["amount"] == {"total": 1, "currency": "CNY"}
        response_body = b'{"code_url":"weixin://wxpay/bizpayurl/up?pr=test"}'
        headers = _signed_headers(
            wechat_private_key, response_body, serial=config.wechatpay_public_key_id
        )
        return httpx.Response(200, content=response_body, headers=headers)

    async def run():
        async with WeChatPayClient(config, transport=httpx.MockTransport(handler)) as client:
            return await client.create_native_order(
                out_trade_no="ORDER202609230001", description="test product", total_cents=1
            )

    order = asyncio.run(run())
    assert order.code_url.startswith("weixin://")


def test_tampered_api_response_is_rejected(key_material):
    config, _, wechat_private_key = key_material

    async def handler(_: httpx.Request) -> httpx.Response:
        signed_body = b'{"code_url":"weixin://original"}'
        headers = _signed_headers(
            wechat_private_key, signed_body, serial=config.wechatpay_public_key_id
        )
        return httpx.Response(200, content=b'{"code_url":"weixin://tampered"}', headers=headers)

    async def run():
        async with WeChatPayClient(config, transport=httpx.MockTransport(handler)) as client:
            await client.create_native_order(
                out_trade_no="ORDER202609230002", description="test product", total_cents=1
            )

    with pytest.raises(SignatureVerificationError):
        asyncio.run(run())


def _notification(config: WeChatPayConfig, wechat_private_key: rsa.RSAPrivateKey):
    transaction = {
        "appid": config.appid,
        "mchid": config.mchid,
        "out_trade_no": "ORDER202609230003",
        "transaction_id": "4200000000000000001",
        "trade_type": "NATIVE",
        "trade_state": "SUCCESS",
        "amount": {
            "total": 1,
            "payer_total": 1,
            "currency": "CNY",
            "payer_currency": "CNY",
        },
        "success_time": "2026-09-23T12:00:00+08:00",
    }
    nonce = "0123456789ab"
    associated_data = "transaction"
    ciphertext = AESGCM(config.api_v3_key).encrypt(
        nonce.encode(), json.dumps(transaction, separators=(",", ":")).encode(), associated_data.encode()
    )
    envelope = {
        "id": "EV-TEST-0001",
        "create_time": "2026-09-23T12:00:01+08:00",
        "event_type": "TRANSACTION.SUCCESS",
        "resource_type": "encrypt-resource",
        "summary": "payment success",
        "resource": {
            "original_type": "transaction",
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "associated_data": associated_data,
            "nonce": nonce,
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode()
    headers = _signed_headers(wechat_private_key, body, serial=config.wechatpay_public_key_id)
    return headers, body


def test_notification_is_verified_decrypted_and_amount_checked(key_material):
    config, _, wechat_private_key = key_material
    headers, body = _notification(config, wechat_private_key)
    client = WeChatPayClient(config, transport=httpx.MockTransport(lambda _: None))
    notification = client.parse_payment_notification(headers=headers, body=body)
    assert notification.transaction.transaction_id == "4200000000000000001"
    assert_expected_payment(
        notification.transaction,
        expected_out_trade_no="ORDER202609230003",
        expected_total=1,
    )
    with pytest.raises(PaymentValidationError):
        assert_expected_payment(
            notification.transaction,
            expected_out_trade_no="ORDER202609230003",
            expected_total=100,
        )


def test_tampered_callback_is_rejected_before_decryption(key_material):
    config, _, wechat_private_key = key_material
    headers, body = _notification(config, wechat_private_key)
    with pytest.raises(SignatureVerificationError):
        WeChatPayClient(config).parse_payment_notification(headers=headers, body=body + b" ")


def test_stale_callback_is_rejected(key_material):
    config, _, wechat_private_key = key_material
    headers, body = _notification(config, wechat_private_key)
    with pytest.raises(SignatureVerificationError):
        WeChatPayClient(config).parse_payment_notification(
            headers=headers, body=body, now=int(headers["Wechatpay-Timestamp"]) + 301
        )


def test_config_repr_does_not_expose_api_v3_key(key_material):
    config, _, _ = key_material
    assert config.api_v3_key.decode() not in repr(config)


def test_wechatpay_public_key_loader_accepts_utf8_bom(tmp_path: Path):
    _, public_path, private_key = _write_key_pair(tmp_path, "wechat_bom")
    public_path.write_bytes(b"\xef\xbb\xbf\r\n" + public_path.read_bytes())
    loaded = load_wechatpay_public_key(public_path)
    assert loaded.public_numbers() == private_key.public_key().public_numbers()


def test_business_facade_creates_queries_and_closes_payment(key_material):
    config, _, _ = key_material
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, received_config):
            assert received_config is config

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def create_native_order(self, **kwargs):
            calls.append(("create", kwargs))
            return NativeOrder(kwargs["out_trade_no"], "weixin://test")

        async def query_order(self, out_trade_no):
            calls.append(("query", out_trade_no))
            return {"out_trade_no": out_trade_no, "trade_state": "NOTPAY"}

        async def close_order(self, out_trade_no):
            calls.append(("close", out_trade_no))

    async def run():
        service = NativePaymentService(config, client_factory=FakeClient)
        order = await service.create_payment(
            out_trade_no="ORDER202609230010",
            description="test",
            total_cents=1,
        )
        status = await service.query_payment(order.out_trade_no)
        await service.close_payment(order.out_trade_no)
        return order, status

    order, status = asyncio.run(run())
    assert order.code_url == "weixin://test"
    assert status["trade_state"] == "NOTPAY"
    assert [name for name, _ in calls] == ["create", "query", "close"]
