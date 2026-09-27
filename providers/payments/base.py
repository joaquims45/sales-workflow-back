"""PaymentProvider contract (ARCHITECTURE.md §39/§44/§45).

Sales Workflow's domain (Order, CheckoutService, agents) only ever talks to
this interface — never to a specific gateway's SDK. Nothing outside
providers/payments/ should know Mercado Pago (or any future provider)
exists.

No concrete provider lives here yet: MockPaymentProvider (the default) is
the next step, MercadoPagoPaymentProvider a later one. This module only
fixes the shape everything else will be built against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping, Protocol

if TYPE_CHECKING:
    from apps.orders.models import Order
    from apps.payments.models import Payment

# The only statuses that exist anywhere in Sales Workflow, regardless of
# provider (§46) — an adapter's job is to map onto these, never to leak its
# own vocabulary past providers/payments/.
NormalizedStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]


@dataclass
class CheckoutResult:
    """What starting a checkout gives back, normalized (§45)."""

    payment_id: str
    status: NormalizedStatus
    checkout_url: str
    provider: str
    external_reference: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookResult:
    """What processing an incoming webhook resolves to."""

    payment_id: str
    status: NormalizedStatus
    metadata: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    def create_checkout(self, order: "Order") -> CheckoutResult:
        """Starts a checkout attempt for an Order and returns its normalized result."""
        ...

    def get_payment_status(self, payment: "Payment") -> NormalizedStatus:
        """Polls the provider for a payment's current status."""
        ...

    def process_webhook(self, raw_payload: Any, headers: Mapping[str, str]) -> WebhookResult:
        """Validates and normalizes an incoming webhook payload."""
        ...


def get_payment_provider() -> PaymentProvider:
    from django.conf import settings

    provider_name = settings.PAYMENT_PROVIDER

    if provider_name == "mock":
        from .mock import MockPaymentProvider

        return MockPaymentProvider()

    if provider_name == "mercadopago":
        from .mercadopago import MercadoPagoPaymentProvider

        return MercadoPagoPaymentProvider()

    raise ValueError(f"Unknown PAYMENT_PROVIDER: {provider_name!r}")
