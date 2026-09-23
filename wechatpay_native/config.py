from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ConfigurationError


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _validate_pem_path(value: str, name: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"{name} must point to an existing PEM file")
    return path


def _validate_notify_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ConfigurationError("WECHATPAY_NOTIFY_URL must be a public HTTPS URL without credentials")
    if parsed.fragment:
        raise ConfigurationError("WECHATPAY_NOTIFY_URL must not contain a fragment")
    return value


@dataclass(frozen=True, slots=True)
class WeChatPayConfig:
    mchid: str
    appid: str
    merchant_serial_no: str
    merchant_private_key_path: Path
    api_v3_key: bytes = field(repr=False)
    wechatpay_public_key_id: str
    wechatpay_public_key_path: Path
    notify_url: str
    request_timeout_seconds: float = 10.0
    signature_clock_skew_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.mchid.isdigit() or not (8 <= len(self.mchid) <= 32):
            raise ConfigurationError("mchid must be an 8-32 digit merchant ID")
        if not self.appid or len(self.appid) > 32:
            raise ConfigurationError("appid must be present and no longer than 32 characters")
        if not self.merchant_serial_no or len(self.merchant_serial_no) > 64:
            raise ConfigurationError("merchant_serial_no is invalid")
        if len(self.api_v3_key) != 32:
            raise ConfigurationError("APIv3 key must be exactly 32 bytes")
        if not self.wechatpay_public_key_id.startswith("PUB_KEY_ID_"):
            raise ConfigurationError("Use the recommended WeChat Pay public-key mode (PUB_KEY_ID_...)")
        if not (0 < self.request_timeout_seconds <= 60):
            raise ConfigurationError("request_timeout_seconds must be in (0, 60]")
        if not (60 <= self.signature_clock_skew_seconds <= 600):
            raise ConfigurationError("signature_clock_skew_seconds must be between 60 and 600")
        _validate_notify_url(self.notify_url)

    @classmethod
    def from_env(cls) -> "WeChatPayConfig":
        """Load secrets by reference; private key material is never accepted inline."""
        api_v3_key = _required_env("WECHATPAY_API_V3_KEY").encode("utf-8")
        return cls(
            mchid=_required_env("WECHATPAY_MCH_ID"),
            appid=_required_env("WECHATPAY_APP_ID"),
            merchant_serial_no=_required_env("WECHATPAY_MERCHANT_SERIAL_NO"),
            merchant_private_key_path=_validate_pem_path(
                _required_env("WECHATPAY_MERCHANT_PRIVATE_KEY_PATH"),
                "WECHATPAY_MERCHANT_PRIVATE_KEY_PATH",
            ),
            api_v3_key=api_v3_key,
            wechatpay_public_key_id=_required_env("WECHATPAY_PUBLIC_KEY_ID"),
            wechatpay_public_key_path=_validate_pem_path(
                _required_env("WECHATPAY_PUBLIC_KEY_PATH"),
                "WECHATPAY_PUBLIC_KEY_PATH",
            ),
            notify_url=_validate_notify_url(_required_env("WECHATPAY_NOTIFY_URL")),
            request_timeout_seconds=float(os.getenv("WECHATPAY_TIMEOUT_SECONDS", "10")),
            signature_clock_skew_seconds=int(os.getenv("WECHATPAY_SIGNATURE_SKEW_SECONDS", "300")),
        )
