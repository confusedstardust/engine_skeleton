from __future__ import annotations


class WeChatPayError(Exception):
    """Base exception for the Native payment module."""


class ConfigurationError(WeChatPayError):
    """Configuration is missing, unsafe, or internally inconsistent."""


class SignatureVerificationError(WeChatPayError):
    """A WeChat Pay response or callback could not be authenticated."""


class PaymentValidationError(WeChatPayError):
    """An authenticated payment does not match the merchant order."""


class WeChatPayAPIError(WeChatPayError):
    def __init__(
        self,
        status_code: int,
        code: str = "UNKNOWN",
        message: str = "WeChat Pay request failed",
        request_id: str | None = None,
    ) -> None:
        super().__init__(f"WeChat Pay API error {status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id
