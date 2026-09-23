from __future__ import annotations

import base64
import binascii
import time
from pathlib import Path
from typing import Mapping

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .errors import ConfigurationError, SignatureVerificationError


def load_merchant_private_key(path: Path) -> rsa.RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise ConfigurationError("Unable to load merchant RSA private key PEM") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ConfigurationError("Merchant private key must be RSA with at least 2048 bits")
    return key


def load_wechatpay_public_key(path: Path) -> rsa.RSAPublicKey:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ConfigurationError("Unable to read WeChat Pay public key/certificate PEM") from exc
    # Some Windows editors/download tools add an UTF-8 BOM or surrounding blank
    # lines. They are not part of PEM and older cryptography builds reject them.
    data = data.lstrip(b"\xef\xbb\xbf \t\r\n").rstrip() + b"\n"
    try:
        key = serialization.load_pem_public_key(data)
    except ValueError:
        try:
            key = x509.load_pem_x509_certificate(data).public_key()
        except ValueError as exc:
            first_line = data.splitlines()[0].decode("ascii", errors="replace") if data else "<empty>"
            raise ConfigurationError(
                "微信支付公钥文件无法解析；请从商户平台的“微信支付公钥”页面下载 PEM，"
                "文件首行应为 -----BEGIN PUBLIC KEY-----（平台证书模式则为 "
                f"-----BEGIN CERTIFICATE-----）。当前首行：{first_line[:80]}"
            ) from exc
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise ConfigurationError("WeChat Pay public key must be RSA with at least 2048 bits")
    return key


def rsa_sha256_sign(private_key: rsa.RSAPrivateKey, message: bytes) -> str:
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def rsa_sha256_verify(public_key: rsa.RSAPublicKey, message: bytes, signature: str) -> None:
    if signature.startswith("WECHATPAY/SIGNTEST/"):
        raise SignatureVerificationError("Rejected WeChat Pay signature probe")
    try:
        decoded = base64.b64decode(signature, validate=True)
        public_key.verify(decoded, message, padding.PKCS1v15(), hashes.SHA256())
    except (binascii.Error, InvalidSignature, ValueError) as exc:
        raise SignatureVerificationError("Invalid WeChat Pay signature") from exc


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value.strip()
    raise SignatureVerificationError(f"Missing required signature header: {name}")


def verify_wechatpay_message(
    *,
    headers: Mapping[str, str],
    body: bytes,
    public_key: rsa.RSAPublicKey,
    expected_public_key_id: str,
    max_clock_skew_seconds: int,
    now: int | None = None,
) -> None:
    serial = _header(headers, "Wechatpay-Serial")
    timestamp_text = _header(headers, "Wechatpay-Timestamp")
    nonce = _header(headers, "Wechatpay-Nonce")
    signature = _header(headers, "Wechatpay-Signature")
    if serial != expected_public_key_id:
        raise SignatureVerificationError("Unexpected WeChat Pay public key ID")
    try:
        timestamp = int(timestamp_text)
    except ValueError as exc:
        raise SignatureVerificationError("Invalid WeChat Pay timestamp") from exc
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > max_clock_skew_seconds:
        raise SignatureVerificationError("Stale or future-dated WeChat Pay message")
    message = f"{timestamp_text}\n{nonce}\n".encode("utf-8") + body + b"\n"
    rsa_sha256_verify(public_key, message, signature)
