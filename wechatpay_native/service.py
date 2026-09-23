from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping

from .client import NativeOrder, WeChatPayClient
from .config import WeChatPayConfig
from .notifications import PaymentNotification, assert_expected_payment, parse_payment_notification


ClientFactory = Callable[[WeChatPayConfig], WeChatPayClient]


class NativePaymentService:
    """Business-facing facade for the complete Native payment lifecycle.

    Keep one service instance in the application's dependency container and call
    these methods from any business module. Amounts must come from trusted
    server-side order data and are always integer fen.
    """

    def __init__(
        self,
        config: WeChatPayConfig,
        *,
        client_factory: ClientFactory = WeChatPayClient,
    ) -> None:
        self.config = config
        self._client_factory = client_factory

    @classmethod
    def from_env(cls) -> "NativePaymentService":
        return cls(WeChatPayConfig.from_env())

    async def create_payment(
        self,
        *,
        out_trade_no: str,
        description: str,
        total_cents: int,
        time_expire: datetime | None = None,
        attach: str | None = None,
    ) -> NativeOrder:
        """Create a Native order and return its local order number and code_url."""
        async with self._client_factory(self.config) as client:
            return await client.create_native_order(
                out_trade_no=out_trade_no,
                description=description,
                total_cents=total_cents,
                time_expire=time_expire,
                attach=attach,
            )

    async def query_payment(self, out_trade_no: str) -> dict[str, Any]:
        """Query WeChat Pay using a merchant order number."""
        async with self._client_factory(self.config) as client:
            return await client.query_order(out_trade_no)

    async def close_payment(self, out_trade_no: str) -> None:
        """Close an unpaid merchant order."""
        async with self._client_factory(self.config) as client:
            await client.close_order(out_trade_no)

    def verify_payment_callback(
        self,
        *,
        headers: Mapping[str, str],
        body: bytes,
        expected_out_trade_no: str,
        expected_total_cents: int,
        expected_currency: str = "CNY",
    ) -> PaymentNotification:
        """Authenticate, decrypt, and match a callback to a local order.

        Only after this method returns may the caller atomically mark its local
        order paid. The caller must still deduplicate notification_id and
        transaction_id in its database transaction.
        """
        notification = parse_payment_notification(
            headers=headers,
            body=body,
            config=self.config,
        )
        assert_expected_payment(
            notification.transaction,
            expected_out_trade_no=expected_out_trade_no,
            expected_total=expected_total_cents,
            expected_currency=expected_currency,
        )
        return notification


async def create_native_payment(
    *,
    out_trade_no: str,
    description: str,
    total_cents: int,
    config: WeChatPayConfig | None = None,
    time_expire: datetime | None = None,
    attach: str | None = None,
) -> NativeOrder:
    """One-call convenience entry point for Native payment creation.

    If config is omitted, the standard WECHATPAY_* environment variables are
    loaded. Reuse NativePaymentService instead when making many calls.
    """
    service = NativePaymentService(config or WeChatPayConfig.from_env())
    return await service.create_payment(
        out_trade_no=out_trade_no,
        description=description,
        total_cents=total_cents,
        time_expire=time_expire,
        attach=attach,
    )
