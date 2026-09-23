from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from .config import WeChatPayConfig
from .crypto import load_merchant_private_key, load_wechatpay_public_key, rsa_sha256_sign, verify_wechatpay_message
from .errors import PaymentValidationError, WeChatPayAPIError, WeChatPayError
from .notifications import OUT_TRADE_NO_RE, PaymentNotification, parse_payment_notification


API_ORIGIN = "https://api.mch.weixin.qq.com"
DESCRIPTION_MAX_LENGTH = 127


@dataclass(frozen=True, slots=True)
class NativeOrder:
    out_trade_no: str
    code_url: str


class WeChatPayClient:
    """Strict async client for ordinary-merchant Native payment."""

    def __init__(self, config: WeChatPayConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config
        self._merchant_private_key = load_merchant_private_key(config.merchant_private_key_path)
        self._wechatpay_public_key = load_wechatpay_public_key(config.wechatpay_public_key_path)
        self._http = httpx.AsyncClient(
            base_url=API_ORIGIN,
            timeout=config.request_timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "webgal-forge-wechatpay-native/1.0"},
        )

    async def __aenter__(self) -> "WeChatPayClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def _authorization(self, method: str, canonical_uri: str, body: bytes) -> str:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = (
            f"{method.upper()}\n{canonical_uri}\n{timestamp}\n{nonce}\n".encode("utf-8")
            + body
            + b"\n"
        )
        signature = rsa_sha256_sign(self._merchant_private_key, message)
        return (
            'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.config.mchid}",nonce_str="{nonce}",timestamp="{timestamp}",'
            f'serial_no="{self.config.merchant_serial_no}",signature="{signature}"'
        )

    async def _request(
        self,
        method: str,
        canonical_uri: str,
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any], httpx.Headers]:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": self._authorization(method, canonical_uri, body)}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = await self._http.request(method, canonical_uri, content=body or None, headers=headers)
        except httpx.HTTPError as exc:
            raise WeChatPayError("WeChat Pay network request failed; query the order before retrying") from exc

        verify_wechatpay_message(
            headers=response.headers,
            body=response.content,
            public_key=self._wechatpay_public_key,
            expected_public_key_id=self.config.wechatpay_public_key_id,
            max_clock_skew_seconds=self.config.signature_clock_skew_seconds,
        )
        try:
            data: dict[str, Any] = response.json() if response.content else {}
        except json.JSONDecodeError as exc:
            raise WeChatPayError("Authenticated WeChat Pay response is not valid JSON") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise WeChatPayAPIError(
                response.status_code,
                str(data.get("code", "UNKNOWN")),
                str(data.get("message", "WeChat Pay request failed")),
                response.headers.get("Request-ID"),
            )
        return response.status_code, data, response.headers

    async def create_native_order(
        self,
        *,
        out_trade_no: str,
        description: str,
        total_cents: int,
        time_expire: datetime | None = None,
        attach: str | None = None,
    ) -> NativeOrder:
        _validate_order(out_trade_no, description, total_cents, time_expire, attach)
        payload: dict[str, Any] = {
            "appid": self.config.appid,
            "mchid": self.config.mchid,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": self.config.notify_url,
            "amount": {"total": total_cents, "currency": "CNY"},
        }
        if time_expire is not None:
            payload["time_expire"] = time_expire.isoformat(timespec="seconds")
        if attach is not None:
            payload["attach"] = attach
        _, data, _ = await self._request("POST", "/v3/pay/transactions/native", payload)
        code_url = data.get("code_url")
        if not isinstance(code_url, str) or not code_url.startswith("weixin://"):
            raise WeChatPayError("Authenticated response did not contain a valid Native code_url")
        return NativeOrder(out_trade_no=out_trade_no, code_url=code_url)

    async def query_order(self, out_trade_no: str) -> dict[str, Any]:
        _validate_out_trade_no(out_trade_no)
        encoded = quote(out_trade_no, safe="")
        uri = f"/v3/pay/transactions/out-trade-no/{encoded}?mchid={self.config.mchid}"
        _, data, _ = await self._request("GET", uri)
        if data.get("appid") != self.config.appid or data.get("mchid") != self.config.mchid:
            raise PaymentValidationError("Queried order merchant identity mismatch")
        if data.get("out_trade_no") != out_trade_no:
            raise PaymentValidationError("Queried order number mismatch")
        return data

    async def close_order(self, out_trade_no: str) -> None:
        _validate_out_trade_no(out_trade_no)
        encoded = quote(out_trade_no, safe="")
        uri = f"/v3/pay/transactions/out-trade-no/{encoded}/close"
        await self._request("POST", uri, {"mchid": self.config.mchid})

    def parse_payment_notification(
        self,
        *,
        headers: Mapping[str, str],
        body: bytes,
        now: int | None = None,
    ) -> PaymentNotification:
        return parse_payment_notification(headers=headers, body=body, config=self.config, now=now)


def _validate_out_trade_no(value: str) -> None:
    if not OUT_TRADE_NO_RE.fullmatch(value):
        raise PaymentValidationError("out_trade_no must be 6-32 allowed ASCII characters")


def _validate_order(
    out_trade_no: str,
    description: str,
    total_cents: int,
    time_expire: datetime | None,
    attach: str | None,
) -> None:
    _validate_out_trade_no(out_trade_no)
    if not description or len(description) > DESCRIPTION_MAX_LENGTH:
        raise PaymentValidationError("description must be 1-127 characters")
    if isinstance(total_cents, bool) or not isinstance(total_cents, int) or total_cents <= 0:
        raise PaymentValidationError("total_cents must be a positive integer in fen")
    if total_cents > 100_000_000:
        raise PaymentValidationError("total_cents exceeds the module safety limit")
    if attach is not None and len(attach) > 128:
        raise PaymentValidationError("attach must be no longer than 128 characters")
    if time_expire is not None:
        if time_expire.tzinfo is None or time_expire.utcoffset() is None:
            raise PaymentValidationError("time_expire must include a timezone")
        seconds = (time_expire.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        if seconds < 60 or seconds > 7 * 24 * 60 * 60:
            raise PaymentValidationError("time_expire must be between 1 minute and 7 days from now")
