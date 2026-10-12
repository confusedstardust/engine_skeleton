from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .crypto import load_wechatpay_public_key, verify_wechatpay_message
from .errors import PaymentValidationError


OUT_TRADE_NO_RE = re.compile(r"^[0-9A-Za-z_\-|*]{6,32}$")
MAX_NOTIFICATION_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PaymentTransaction:
    appid: str
    mchid: str
    out_trade_no: str
    transaction_id: str
    trade_type: str
    trade_state: str
    total: int
    payer_total: int
    currency: str
    payer_currency: str
    success_time: str
    raw: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PaymentNotification:
    notification_id: str
    create_time: str
    event_type: str
    transaction: PaymentTransaction


def _as_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PaymentValidationError(f"{field} must be a JSON object")
    return value


def _required_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise PaymentValidationError(f"Missing or invalid {field}")
    return value


def _required_positive_int(data: Mapping[str, Any], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PaymentValidationError(f"Missing or invalid {field}")
    return value


def _required_nonnegative_int(data: Mapping[str, Any], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PaymentValidationError(f"Missing or invalid {field}")
    return value


def decrypt_notification_resource(resource: Mapping[str, Any], api_v3_key: bytes) -> dict[str, Any]:
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        raise PaymentValidationError("Unsupported notification encryption algorithm")
    if resource.get("original_type") != "transaction":
        raise PaymentValidationError("Unexpected notification resource type")
    nonce = _required_string(resource, "nonce").encode("utf-8")
    associated_data_value = resource.get("associated_data", "")
    if not isinstance(associated_data_value, str):
        raise PaymentValidationError("Invalid associated_data")
    try:
        ciphertext = base64.b64decode(_required_string(resource, "ciphertext"), validate=True)
        plaintext = AESGCM(api_v3_key).decrypt(
            nonce,
            ciphertext,
            associated_data_value.encode("utf-8"),
        )
        decoded = json.loads(plaintext)
    except (binascii.Error, InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaymentValidationError("Unable to authenticate/decrypt notification resource") from exc
    return _as_object(decoded, "decrypted resource")


def parse_payment_notification(
    *,
    headers: Mapping[str, str],
    body: bytes,
    config: Any,
    now: int | None = None,
) -> PaymentNotification:
    if not body or len(body) > MAX_NOTIFICATION_BYTES:
        raise PaymentValidationError("Notification body size is invalid")
    public_key = load_wechatpay_public_key(config.wechatpay_public_key_path)
    verify_wechatpay_message(
        headers=headers,
        body=body,
        public_key=public_key,
        expected_public_key_id=config.wechatpay_public_key_id,
        max_clock_skew_seconds=config.signature_clock_skew_seconds,
        now=now,
    )
    try:
        envelope = _as_object(json.loads(body), "notification")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaymentValidationError("Notification body is not valid UTF-8 JSON") from exc
    if envelope.get("event_type") != "TRANSACTION.SUCCESS":
        raise PaymentValidationError("Unexpected notification event_type")
    if envelope.get("resource_type") != "encrypt-resource":
        raise PaymentValidationError("Unexpected notification resource_type")

    decrypted = decrypt_notification_resource(_as_object(envelope.get("resource"), "resource"), config.api_v3_key)
    amount = _as_object(decrypted.get("amount"), "amount")
    transaction = PaymentTransaction(
        appid=_required_string(decrypted, "appid"),
        mchid=_required_string(decrypted, "mchid"),
        out_trade_no=_required_string(decrypted, "out_trade_no"),
        transaction_id=_required_string(decrypted, "transaction_id"),
        trade_type=_required_string(decrypted, "trade_type"),
        trade_state=_required_string(decrypted, "trade_state"),
        total=_required_positive_int(amount, "total"),
        payer_total=_required_nonnegative_int(amount, "payer_total"),
        currency=_required_string(amount, "currency"),
        payer_currency=_required_string(amount, "payer_currency"),
        success_time=_required_string(decrypted, "success_time"),
        raw=decrypted,
    )
    if transaction.appid != config.appid or transaction.mchid != config.mchid:
        raise PaymentValidationError("Payment merchant identity does not match configuration")
    if transaction.trade_state != "SUCCESS":
        raise PaymentValidationError("Payment is not successful")
    if transaction.trade_type != "NATIVE":
        raise PaymentValidationError("Payment is not a Native transaction")
    if transaction.currency != "CNY" or transaction.payer_currency != "CNY":
        raise PaymentValidationError("Unexpected payment currency")
    if transaction.payer_total > transaction.total:
        raise PaymentValidationError("payer_total exceeds order total")
    if not OUT_TRADE_NO_RE.fullmatch(transaction.out_trade_no):
        raise PaymentValidationError("Invalid out_trade_no in payment")
    return PaymentNotification(
        notification_id=_required_string(envelope, "id"),
        create_time=_required_string(envelope, "create_time"),
        event_type="TRANSACTION.SUCCESS",
        transaction=transaction,
    )


def assert_expected_payment(
    transaction: PaymentTransaction,
    *,
    expected_out_trade_no: str,
    expected_total: int,
    expected_currency: str = "CNY",
) -> None:
    """Mandatory business check before an order is marked paid."""
    if transaction.out_trade_no != expected_out_trade_no:
        raise PaymentValidationError("Payment order number does not match merchant order")
    # payer_total may be lower when a valid WeChat Pay coupon is used. The
    # merchant order is matched against total, not the user's post-coupon cash.
    if transaction.total != expected_total:
        raise PaymentValidationError("Payment amount does not match merchant order")
    if transaction.currency != expected_currency:
        raise PaymentValidationError("Payment currency does not match merchant order")
